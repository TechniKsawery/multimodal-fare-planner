"""Okresowo sprawdza, czy zmieniły się strony/PDF-y źródłowe cenników
używane w fares/data/*.json (pole "_zrodlo"/"_zrodlo_*"), i SYGNALIZUJE różnicę względem
poprzedniego stanu — NIE interpretuje automatycznie co się zmieniło, tylko flaguje
"sprawdź ręcznie" (patrz pamięć projektu: automatyczna interpretacja zmian cenników musi
iść przez człowieka).

Działa na zasadzie migawek (snapshotów): dla każdego źródła liczy sha256 treści (dla stron
HTML — po normalizacji, patrz _normalize_for_hash — nie surowych bajtów, żeby nie łapać
szumu typu nonce/cache-busting w <script>; PDF-y hashowane bez zmian) i zapisuje je w
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
"""

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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
cookies. Gołe żądanie z tym UA i bez żadnych cookies przechodzi od razu (200 OK)."""
URL_RE = re.compile(r"https?://[^\s,)\"']+")

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

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_hash(content: bytes, url: str) -> bytes:
    """Przed hashowaniem stron HTML (NIE PDF-ów) usuwa <script>/<style>/komentarze i
    normalizuje biały znak.

    Zweryfikowane na żywo przez Remote Control: bahn.de serwuje niedeterministyczną treść
    (prawdopodobnie nonce/cache-busting w <script>) — 6 monitorowanych stron bahn.de wyszło
    jako "zmienione" w dwóch przebiegach ~20 minut od siebie, czego realnie nie wyjaśniały
    zmiany cen. Założenie (zgodne z tym, jak działają te strony cenowe): sama CENA jest w
    statycznym tekście HTML, nie generowana przez JS po stronie klienta, więc usunięcie
    <script>/<style> nie powinno ukryć realnej zmiany ceny — tylko szum. PDF-y (binarne,
    bez tego problemu w PKP/VRR/ZTM) zostają hashowane bez zmian, rozpoznawane po
    rozszerzeniu URL-a, nie po Content-Type (niektóre mocki/serwery go nie podają)."""
    if url.lower().endswith(".pdf"):
        return content
    try:
        text = content.decode("utf-8", errors="replace")
    except (UnicodeDecodeError, LookupError):
        return content
    text = _SCRIPT_STYLE_RE.sub("", text)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.encode("utf-8")


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
    error: Optional[str] = None
    previous_sha256: Optional[str] = None
    new_sha256: Optional[str] = None
    size_bytes: Optional[int] = None


def discover_sources() -> List[Source]:
    """Wyciąga wszystkie URL-e z pól zaczynających się od "_zrodlo" w fares/data/*.json."""
    sources = []
    for path in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for field, value in data.items():
            if not field.startswith("_zrodlo") or not isinstance(value, str):
                continue
            for url in URL_RE.findall(value):
                sources.append(
                    Source(data_file=path.name, field=field, url=url.rstrip(".,)"))
                )
    return sources


def _snapshot_path(source: Source) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", source.url).strip("_")[:120]
    return SNAPSHOT_DIR / f"{source.data_file}__{slug}.json"


def _fetch_with_retry(url: str, timeout: int) -> requests.Response:
    """GET z `RETRY_ATTEMPTS` próbami i narastającym odstępem — patrz komentarz przy
    RETRY_BACKOFF_SECONDS. Podnosi wyjątek z OSTATNIEJ próby, jeśli żadna się nie powiodła."""
    last_exc: Optional[requests.RequestException] = None
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
    snap_file = _snapshot_path(source)
    previous = (
        json.loads(snap_file.read_text(encoding="utf-8"))
        if snap_file.exists()
        else None
    )

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


def render_markdown(results: List[CheckResult]) -> str:
    changed = [r for r in results if r.changed]
    errors = [r for r in results if r.error]
    first = [r for r in results if r.first_check]
    lines = ["# Raport: sprawdzenie źródeł cenników\n"]
    if changed:
        lines.append(
            f"## ⚠️ Wykryto zmianę w {len(changed)} źródle/źródłach — sprawdź ręcznie\n"
        )
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
    if first:
        lines.append(
            f"\n## Pierwsze sprawdzenie (brak punktu odniesienia) — {len(first)}\n"
        )
        for r in first:
            lines.append(f"- {r.source.data_file}: {r.source.url}\n")
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    """Konsola Windows domyślnie używa kodowania strony (np. cp1250), które nie ogarnia
    znaków w raporcie (⚠️, polskie znaki w pewnych kombinacjach) — bez tego `print(report)`
    wywala się UnicodeEncodeError (zweryfikowane na żywo 2026-10-03). `reconfigure` jest
    no-opem na Linuksie/macOS (tam stdout już jest UTF-8), więc wołamy to bezwarunkowo."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass  # stdout przekierowany na coś bez reconfigure (np. w testach) — nic nie robimy


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
