"""Okresowo sprawdza, czy zmieniły się strony/PDF-y źródłowe cenników
używane w fares/data/*.json (pole "_zrodlo"/"_zrodlo_*"), i SYGNALIZUJE różnicę względem
poprzedniego stanu — NIE interpretuje automatycznie co się zmieniło, tylko flaguje
"sprawdź ręcznie" (patrz pamięć projektu: automatyczna interpretacja zmian cenników musi
iść przez człowieka).

Działa na zasadzie migawek (snapshotów): dla każdego źródła liczy sha256 treści (dla stron
HTML — po normalizacji, patrz _normalize_for_hash — nie surowych bajtów, żeby nie łapać
szumu typu nonce/cache-busting w <script>; PDF-y hashowane bez zmian; normalizacja zostawia tylko tekst widoczny dla użytkownika) i zapisuje je w
fares/data/.snapshots/<plik>__<url-slug>.json. Przy następnym uruchomieniu
porównuje nowy hash ze starym. Snapshoty są commitowane do repo, więc stan przechowuje
się między uruchomieniami (patrz .github/workflows/watch_fare_sources.yml — GitHub Actions,
NIE sesja Claude Code, bo kontener sesji ma zablokowany dostęp do większości tych hostów
przez politykę sieciową organizacji).

Użycie:
    python scripts/fetch_fare_sources.py            # sprawdza wszystkie źródła
    python scripts/fetch_fare_sources.py --summary report.md   # też zapisuje raport Markdown

Kod wyjścia: 0 = brak zmian (albo pierwsze sprawdzenie), 1 = wykryto zmianę w >=1 źródle,
2 = błąd pobierania >=1 źródła (sieć/404/itp., bez wykrytej zmiany w resztach).
Źródła z MANUAL_ONLY_SOURCES nie są pobierane (tylko wypisane w raporcie) i nie wpływają na kod wyjścia.
"""

import argparse
import contextlib
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "fares" / "data"
SNAPSHOT_DIR = DATA_DIR / ".snapshots"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
"""Realistyczny UA przeglądarki Chrome — zweryfikowane na żywo 2026-10-03: intercity.pl
blokuje (connection reset / timeout) żądania z niestandardowym UA skryptu (np.
"multimodal-fare-planner-fare-watcher/1.0"), niezależnie od innych nagłówków czy
cookies. Gołe żądanie z tym UA i bez żadnych cookies przechodziło wtedy od razu (200 OK). Później intercity.pl zaczął
zwracać 403 — tych źródeł nie obchodzimy, tylko oznaczamy w MANUAL_ONLY_SOURCES."""
URL_RE = re.compile(r"https?://(?:[^\s,()<>\"']|,(?=[^\s,()<>\"']))+")
"""Pojedynczy "token" URL-a: przecinek jest częścią adresu, gdy bezpośrednio po nim jest
kolejny znak adresu (np. krakow.pl/aktualnosci/283607,26,komunikat,...html), a kończy go
dopiero przecinek przed spacją/końcem (zdanie "... /vergleich, https://...").
Spacje w adresie obsługuje `extract_urls` (patrz niżej)."""

_URL_TRAILING_PUNCT = ".,;:"
_URL_STOP_CHARS = set(",;:()<>\"'")
_URL_MAX_EXTRA_WORDS = 5
"""Ile słów po spacji `extract_urls` maksymalnie dokleja do adresu (ścieżki typu
".../Przepisy i taryfy/Cennik.pdf" mają 1-2 spacje)."""

_URL_CONTINUATION_EXTENSIONS = (".pdf",)


def extract_urls(text: str) -> list[str]:
    """Wyciąga adresy http(s) z tekstu pola "_zrodlo*".

    Poza `URL_RE` (przecinek wewnątrz adresu zostaje) łapie adresy PDF, które w danych mają
    SPACJE w ścieżce (np. ".../Przepisy i taryfy/Cennik_SPI.pdf" — bez tego watcher sprawdzał
    ucięte ".../Przepisy"). Doklejamy kolejne słowa tylko wtedy, gdy łącznie kończą się na
    ".pdf", żadne nie jest znakiem zdania/początkiem innego adresu, a wśród doklejonych jest
    ukośnik (czyli to dalszy ciąg ścieżki, nie zwykłe słowa opisu typu "w pliku cennik.pdf")."""
    urls = []
    for match in URL_RE.finditer(text):
        url = match.group().rstrip(_URL_TRAILING_PUNCT)
        if not url.lower().endswith(_URL_CONTINUATION_EXTENSIONS) and url == match.group():
            words = text[match.end() :].split(" ")
            # words[0] == "" gdy po adresie jest spacja (jedna), wtedy zaczynamy od words[1]
            candidate_words = words[1:] if words and words[0] == "" else []
            extra: list[str] = []
            for word in candidate_words[:_URL_MAX_EXTRA_WORDS]:
                if (
                    not word
                    or "\n" in word
                    or word.lower().startswith(("http://", "https://"))
                    or _URL_STOP_CHARS & set(word.rstrip(_URL_TRAILING_PUNCT))
                ):
                    break
                extra.append(word)
                joined = url + " " + " ".join(extra)
                if joined.lower().endswith(_URL_CONTINUATION_EXTENSIONS) and any(
                    "/" in w for w in extra
                ):
                    url = joined
                    break
        urls.append(url)
    return urls


BROWSER_LIKE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/pdf,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Site": "none",
}

RETRY_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 2
"""Niektóre źródła bywają po prostu wolne albo gubią pierwsze połączenie (timeout/connection
reset) bez realnej zmiany treści — zanim zgłosimy błąd, próbujemy ponownie z narastającym
odstępem, zamiast od razu wpisywać je do raportu jako "błąd pobierania"."""

_sleep = time.sleep  # nazwa modułowa, żeby testy mogły podmienić bez prawdziwego czekania

_WHITESPACE_RE = re.compile(r"\s+")
_NOISE_PATTERNS = (
    # data+czas ISO (2026-10-14T12:34:56Z, 2026-10-14 12:34:56.789+02:00) — sama data bez
    # godziny ("obowiązuje od 2026-09-01") zostaje, bo to realna treść cennika
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"),
    # godzina z sekundami (14:32:11) — zegar/„ostatnia aktualizacja”
    re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"),
    # unix timestamp (sekundy lub milisekundy)
    re.compile(r"\b1\d{9}(?:\d{3})?\b"),
    # UUID
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    # długie tokeny hex (hash/nonce/csrf), min. 24 znaki
    re.compile(r"\b[0-9a-fA-F]{24,}\b"),
    # długie tokeny base64/urlsafe zawierające cyfrę i literę, min. 28 znaków
    re.compile(r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{28,}\b"),
)
_INVISIBLE_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head"})
_KEEP_IN_HEAD = frozenset({"title"})


class _VisibleTextParser(HTMLParser):
    """Zbiera tylko tekst widoczny dla użytkownika: pomija <script>/<style>/<noscript>/
    <template>/<svg> oraz <head> (poza <title>); komentarze, atrybuty (nonce, data-*,
    ukryte pola z tokenami, href z parametrami sesji) i same znaczniki w ogóle nie trafiają
    do wyniku. `convert_charrefs=True` zamienia &nbsp; i inne encje na znaki."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._head_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        elif tag in _INVISIBLE_TAGS - {"head"}:
            self._skip_depth += 1
        elif tag == "head":
            self._head_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in _INVISIBLE_TAGS - {"head"}:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "head":
            self._head_depth = max(0, self._head_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._head_depth and not self._in_title:
            return
        self.chunks.append(data)


def _is_pdf(content: bytes, url: str) -> bool:
    """PDF rozpoznajemy po rozszerzeniu ścieżki URL-a (ignorując ?query/#fragment) albo po
    sygnaturze %PDF — nie po Content-Type (niektóre mocki/serwery go nie podają)."""
    return urlsplit(url).path.lower().endswith(".pdf") or content.lstrip()[:5] == b"%PDF-"


def _normalize_for_hash(content: bytes, url: str) -> bytes:
    """Przed hashowaniem stron HTML (NIE PDF-ów) zostawia wyłącznie tekst widoczny dla
    użytkownika, bez szumu, który zmienia się między pobraniami tej samej treści.

    Kroki: (1) wyciągnięcie tekstu z HTML (bez skryptów, styli, komentarzy, <head>,
    atrybutów — a więc bez nonce, tokenów CSRF i parametrów cache-busting), (2) usunięcie
    z tekstu znaczników czasu (data+godzina, godzina z sekundami, unix timestamp) i długich
    tokenów (UUID, hex, base64), (3) zwinięcie białych znaków.

    Zweryfikowane na żywo przez Remote Control: bahn.de serwuje niedeterministyczną treść
    (nonce/cache-busting) — 6 monitorowanych stron bahn.de wyszło jako "zmienione" w dwóch
    przebiegach ~20 minut od siebie, czego realnie nie wyjaśniały zmiany cen. Założenie
    (zgodne z tym, jak działają te strony cenowe): CENA jest w statycznym tekście HTML, nie
    generowana przez JS po stronie klienta, więc to nie ukrywa realnej zmiany ceny. Kompromis:
    zmiana samego adresu linku (href) bez zmiany widocznego tekstu nie jest już wykrywana.
    PDF-y (binarne) zostają hashowane bez zmian."""
    if _is_pdf(content, url):
        return content
    text = content.decode("utf-8", errors="replace")
    parser = _VisibleTextParser()
    parser.feed(text)
    parser.close()
    visible = " ".join(parser.chunks)
    for pattern in _NOISE_PATTERNS:
        visible = pattern.sub(" ", visible)
    return _WHITESPACE_RE.sub(" ", visible).strip().encode("utf-8")


# Źródła, których NIE pobieramy automatycznie — sprawdza je człowiek ręcznie. Wartość to
# powód (trafia do raportu). Nie obchodzimy blokad serwera (bez podszywania się, rotacji
# nagłówków itp.): jeśli host odrzuca boty, źródło zostaje na liście ręcznej.
MANUAL_ONLY_SOURCES: dict[str, str] = {
    # intercity.pl odpowiada 403 na żądania botów/skryptów (stan 2026-10). Te dwa PDF-y
    # (cennik usług przewozowych i tabele ulg ustawowych) sprawdzamy ręcznie w przeglądarce
    # — po zmianie adresu/daty obowiązywania w nazwie pliku (np. "od_23.07.2026") albo
    # okresowo. Nie próbujemy ich pobierać, żeby nie generować fałszywego "błędu pobierania".
    "https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Cennik_uslug_przewozowych_PKP_Intercity_tekst_ujednolicony_obowiazuje_od_23.07.2026_r.pdf": (
        "intercity.pl zwraca 403 dla botów — sprawdzać ręcznie"
    ),
    "https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Ulgi%20ustawowe/Tabele_ulg_ustawowych_11-02-2026.pdf": (
        "intercity.pl zwraca 403 dla botów — sprawdzać ręcznie"
    ),
}


@dataclass
class Source:
    data_file: str
    field: str
    url: str


@dataclass
class CheckResult:
    source: Source
    changed: bool = False
    first_check: bool = False
    error: str | None = None
    previous_sha256: str | None = None
    new_sha256: str | None = None
    size_bytes: int | None = None
    manual_only: str | None = None


def discover_sources() -> list[Source]:
    """Wyciąga wszystkie URL-e z pól zaczynających się od "_zrodlo" w fares/data/*.json."""
    sources = []
    for path in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for field, value in data.items():
            if not field.startswith("_zrodlo") or not isinstance(value, str):
                continue
            for url in extract_urls(value):
                sources.append(Source(data_file=path.name, field=field, url=url))
    return sources


def _snapshot_path(source: Source) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", source.url).strip("_")[:120]
    return SNAPSHOT_DIR / f"{source.data_file}__{slug}.json"


def _fetch_with_retry(url: str, timeout: int) -> requests.Response:
    """GET z `RETRY_ATTEMPTS` próbami i narastającym odstępem — patrz komentarz przy
    RETRY_BACKOFF_SECONDS. Podnosi wyjątek z OSTATNIEJ próby, jeśli żadna się nie powiodła."""
    last_exc: requests.RequestException | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.get(url, headers=BROWSER_LIKE_HEADERS, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS - 1:
                _sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_exc


def check_source(source: Source, timeout: int = 120) -> CheckResult:
    if source.url in MANUAL_ONLY_SOURCES:
        return CheckResult(source=source, manual_only=MANUAL_ONLY_SOURCES[source.url])

    snap_file = _snapshot_path(source)
    previous = json.loads(snap_file.read_text(encoding="utf-8")) if snap_file.exists() else None

    try:
        response = _fetch_with_retry(source.url, timeout)
    except requests.RequestException as exc:
        return CheckResult(
            source=source,
            error=str(exc),
            previous_sha256=previous["sha256"] if previous else None,
        )

    normalized = _normalize_for_hash(response.content, source.url)
    digest = hashlib.sha256(normalized).hexdigest()
    result = CheckResult(
        source=source,
        first_check=previous is None,
        changed=previous is not None and previous["sha256"] != digest,
        previous_sha256=previous["sha256"] if previous else None,
        new_sha256=digest,
        size_bytes=len(response.content),
    )

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_file.write_text(
        json.dumps(
            {
                "url": source.url,
                "data_file": source.data_file,
                "field": source.field,
                "sha256": digest,
                "size_bytes": len(response.content),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def render_markdown(results: list[CheckResult]) -> str:
    changed = [r for r in results if r.changed]
    errors = [r for r in results if r.error]
    first = [r for r in results if r.first_check]
    manual = [r for r in results if r.manual_only]
    lines = ["# Raport: sprawdzenie źródeł cenników\n"]
    if changed:
        lines.append(f"## ⚠️ Wykryto zmianę w {len(changed)} źródle/źródłach — sprawdź ręcznie\n")
        for r in changed:
            lines.append(
                f"- **{r.source.data_file}** ({r.source.field}): {r.source.url}\n"
                f"  - poprzedni sha256: `{r.previous_sha256}`\n"
                f"  - nowy sha256: `{r.new_sha256}` ({r.size_bytes} B)\n"
            )
    else:
        lines.append("Brak wykrytych zmian w monitorowanych źródłach.\n")
    if errors:
        lines.append(f"\n## Błędy pobierania ({len(errors)})\n")
        for r in errors:
            lines.append(f"- {r.source.data_file} ({r.source.url}): {r.error}\n")
    if manual:
        lines.append(f"\n## Tylko ręcznie — nie pobierane automatycznie ({len(manual)})\n")
        for r in manual:
            lines.append(f"- {r.source.data_file}: {r.source.url} — {r.manual_only}\n")
    if first:
        lines.append(f"\n## Pierwsze sprawdzenie (brak punktu odniesienia) — {len(first)}\n")
        for r in first:
            lines.append(f"- {r.source.data_file}: {r.source.url}\n")
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    """Konsola Windows domyślnie używa kodowania strony (np. cp1250), które nie ogarnia
    znaków w raporcie (⚠️, polskie znaki w pewnych kombinacjach) — bez tego `print(report)`
    wywala się UnicodeEncodeError (zweryfikowane na żywo 2026-10-03). `reconfigure` jest
    no-opem na Linuksie/macOS (tam stdout już jest UTF-8), więc wołamy to bezwarunkowo."""
    with contextlib.suppress(AttributeError, OSError):
        # stdout przekierowany na coś bez reconfigure (np. w testach) — nic nie robimy
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", help="zapisz raport Markdown do podanego pliku")
    args = parser.parse_args()

    sources = discover_sources()
    if not sources:
        print("Brak źródeł z polem _zrodlo w fares/data/*.json — nic do sprawdzenia.")
        return 0

    results = [check_source(s) for s in sources]
    report = render_markdown(results)
    print(report)
    if args.summary:
        Path(args.summary).write_text(report, encoding="utf-8")

    if any(r.changed for r in results):
        return 1
    if any(r.error for r in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
