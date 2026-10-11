"""Okresowo sprawdza, czy zmieniły się strony/pliki źródłowe spoza fares/data/*.json
(ten zakres ma już scripts/fetch_fare_sources.py): atrakcje, karty miejskie i feedy
GTFS/OSM. Działa na tej samej zasadzie migawek (sha256 po normalizacji dla HTML,
nagłówki HEAD dla dużych plików GTFS/OSM) co fetch_fare_sources.py — patrz jego
docstring po szczegóły normalizacji i retry. NIE interpretuje zmiany, tylko
flaguje "sprawdź ręcznie".

Trzy kategorie źródeł:
1. Atrakcje (attractions/data/attractions.json, pole "official_url" per pozycja)
   — zmiana strony może znaczyć nową cenę albo że atrakcja już nie istnieje.
2. Karty miejskie (attractions/data/city_cards.json, pole "official_url" per karta)
   — zmiana może znaczyć nową cenę LUB że karta już nie jest sprzedawana (patrz
   pamięć projektu: karta bez potwierdzonego istnienia nie wchodzi do rekomendacji).
3. Feedy GTFS/OSM (scripts/fetch_data.py, słowniki GTFS/OSM) — to pliki
   dziesiątek/setek MB, więc sprawdzamy tylko nagłówki HEAD (ETag/Last-Modified/
   Content-Length), nie pobieramy całej treści.

Snapshoty trzymane są w attractions/data/.snapshots/ (atrakcje, karty) i
scripts/.gtfs_snapshots/ (feedy), commitowane do repo tak jak w fetch_fare_sources.py.

Użycie:
    python scripts/watch_other_sources.py                      # sprawdza wszystko
    python scripts/watch_other_sources.py --summary report.md  # też zapisuje raport

Kod wyjścia: 0 = brak zmian, 1 = wykryto zmianę w >=1 źródle, 2 = błąd pobierania
>=1 źródła bez wykrytej zmiany w resztach (patrz fetch_fare_sources.py::main).
"""

import argparse
import hashlib
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_fare_sources as ffs  # noqa: E402  (reużywamy retry/normalizację/hash)

ROOT = Path(__file__).resolve().parent.parent
ATTRACTIONS_DATA_DIR = ROOT / "attractions" / "data"
ATTRACTIONS_SNAPSHOT_DIR = ATTRACTIONS_DATA_DIR / ".snapshots"
GTFS_SNAPSHOT_DIR = ROOT / "scripts" / ".gtfs_snapshots"

ATTRACTION_FILES = {
    "attractions.json": "atrakcje",
    "city_cards.json": "karty",
}
"""Nazwa pliku -> nazwa klucza z listą pozycji w JSON-ie (patrz schemat obu plików)."""


@dataclass
class ContentSource:
    category: str  # "atrakcja" | "karta miejska"
    data_file: str
    item_id: str
    item_name: str
    url: str


@dataclass
class FeedSource:
    key: str  # np. "gtfs/pl/polish_trains.zip"
    url: str
    kind: str  # "GTFS" | "OSM"


def discover_attraction_sources(data_dir: Path | None = None) -> list[ContentSource]:
    """Wyciąga "official_url" z każdej pozycji w attractions.json i city_cards.json."""
    if data_dir is None:
        data_dir = ATTRACTIONS_DATA_DIR
    sources = []
    for filename, list_key in ATTRACTION_FILES.items():
        path = data_dir / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        category = "karta miejska" if list_key == "karty" else "atrakcja"
        for item in data.get(list_key, []):
            url = item.get("official_url")
            if url:
                sources.append(
                    ContentSource(
                        category=category,
                        data_file=filename,
                        item_id=item.get("id", "?"),
                        item_name=item.get("name", "?"),
                        url=url,
                    )
                )
            # Strony, z których pochodzą ceny ulgowe/karty (source_url zagnieżdżone w polach
            # cenowych), mogą być inne niż official_url (np. osobny cennik) — też je śledzimy.
            seen = {url}
            for extra in sorted(_nested_source_urls(item) - seen):
                digest = hashlib.sha1(extra.encode("utf-8")).hexdigest()[:8]
                sources.append(
                    ContentSource(
                        category=category,
                        data_file=filename,
                        item_id=f"{item.get('id', '?')}__{digest}",
                        item_name=f"{item.get('name', '?')} (źródło ceny)",
                        url=extra,
                    )
                )
    return sources


def _nested_source_urls(node) -> set[str]:
    """Zbiera wartości pól "source_url"/"existence_source_url" (http/https) z całego drzewa."""
    urls: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("source_url", "existence_source_url") and isinstance(value, str):
                if value.startswith(("http://", "https://")):
                    urls.add(value)
            else:
                urls |= _nested_source_urls(value)
    elif isinstance(node, list):
        for value in node:
            urls |= _nested_source_urls(value)
    return urls


def discover_feed_sources() -> list[FeedSource]:
    """Wyciąga URL-e GTFS/OSM ze scripts/fetch_data.py (GTFS i OSM)."""
    fetch_data = importlib.import_module("fetch_data")
    sources = []
    for key, url in fetch_data.GTFS.items():
        sources.append(FeedSource(key=key, url=url, kind="GTFS"))
    for key, url in fetch_data.OSM.items():
        sources.append(FeedSource(key=key, url=url, kind="OSM"))
    return sources


def _content_snapshot_path(source: ContentSource) -> Path:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{source.data_file}_{source.item_id}").strip("_")[:120]
    return ATTRACTIONS_SNAPSHOT_DIR / f"{slug}.json"


@dataclass
class ContentCheckResult:
    source: ContentSource
    changed: bool = False
    first_check: bool = False
    error: str | None = None
    previous_sha256: str | None = None
    new_sha256: str | None = None


def check_content_source(source: ContentSource, timeout: int = 120) -> ContentCheckResult:
    snap_file = _content_snapshot_path(source)
    previous = json.loads(snap_file.read_text(encoding="utf-8")) if snap_file.exists() else None

    try:
        response = ffs._fetch_with_retry(source.url, timeout)
    except requests.RequestException as exc:
        return ContentCheckResult(
            source=source,
            error=str(exc),
            previous_sha256=previous["sha256"] if previous else None,
        )

    normalized = ffs._normalize_for_hash(response.content, source.url)
    import hashlib

    digest = hashlib.sha256(normalized).hexdigest()
    result = ContentCheckResult(
        source=source,
        first_check=previous is None,
        changed=previous is not None and previous["sha256"] != digest,
        previous_sha256=previous["sha256"] if previous else None,
        new_sha256=digest,
    )

    ATTRACTIONS_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_file.write_text(
        json.dumps(
            {
                "url": source.url,
                "data_file": source.data_file,
                "item_id": source.item_id,
                "sha256": digest,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def _feed_snapshot_path(source: FeedSource) -> Path:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", source.key).strip("_")[:120]
    return GTFS_SNAPSHOT_DIR / f"{slug}.json"


@dataclass
class FeedCheckResult:
    source: FeedSource
    changed: bool = False
    first_check: bool = False
    error: str | None = None
    previous_fingerprint: dict | None = None
    new_fingerprint: dict | None = None


def check_feed_source(source: FeedSource, timeout: int = 60) -> FeedCheckResult:
    """Sprawdza TYLKO nagłówki HEAD (ETag/Last-Modified/Content-Length) — pliki GTFS/OSM
    mają dziesiątki do setek MB, pobieranie całej treści co tydzień byłoby marnotrawstwem
    transferu i czasu CI. Brak zmiany w tych nagłówkach to silny sygnał braku zmiany danych;
    ich obecność jest różna między serwerami, więc fingerprint zapisuje to, co akurat jest."""
    snap_file = _feed_snapshot_path(source)
    previous = json.loads(snap_file.read_text(encoding="utf-8")) if snap_file.exists() else None

    try:
        response = requests.head(
            source.url, headers=ffs.BROWSER_LIKE_HEADERS, timeout=timeout, allow_redirects=True
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return FeedCheckResult(
            source=source,
            error=str(exc),
            previous_fingerprint=previous,
        )

    fingerprint = {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "content_length": response.headers.get("Content-Length"),
    }
    result = FeedCheckResult(
        source=source,
        first_check=previous is None,
        changed=previous is not None and previous != fingerprint,
        previous_fingerprint=previous,
        new_fingerprint=fingerprint,
    )

    GTFS_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_file.write_text(json.dumps(fingerprint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def render_markdown(
    content_results: list[ContentCheckResult], feed_results: list[FeedCheckResult]
) -> str:
    lines = ["# Raport: sprawdzenie atrakcji, kart miejskich i feedów GTFS/OSM\n"]

    changed_content = [r for r in content_results if r.changed]
    error_content = [r for r in content_results if r.error]
    first_content = [r for r in content_results if r.first_check]
    changed_feeds = [r for r in feed_results if r.changed]
    error_feeds = [r for r in feed_results if r.error]
    first_feeds = [r for r in feed_results if r.first_check]

    total_changed = len(changed_content) + len(changed_feeds)
    if total_changed:
        lines.append(f"## ⚠️ Wykryto zmianę w {total_changed} źródle/źródłach — sprawdź ręcznie\n")
        for r in changed_content:
            lines.append(
                f"- **{r.source.category}** {r.source.item_name} ({r.source.data_file}#{r.source.item_id}): "
                f"{r.source.url}\n"
                f"  - poprzedni sha256: `{r.previous_sha256}` -> nowy: `{r.new_sha256}`\n"
            )
        for r in changed_feeds:
            lines.append(
                f"- **feed {r.source.kind}** {r.source.key}: {r.source.url}\n"
                f"  - poprzednie nagłówki: `{r.previous_fingerprint}` -> nowe: `{r.new_fingerprint}`\n"
            )
    else:
        lines.append("Brak wykrytych zmian w monitorowanych źródłach.\n")

    total_errors = len(error_content) + len(error_feeds)
    if total_errors:
        lines.append(f"\n## Błędy pobierania ({total_errors})\n")
        for r in error_content:
            lines.append(
                f"- {r.source.category} {r.source.item_name} ({r.source.url}): {r.error}\n"
            )
        for r in error_feeds:
            lines.append(f"- feed {r.source.kind} {r.source.key} ({r.source.url}): {r.error}\n")

    total_first = len(first_content) + len(first_feeds)
    if total_first:
        lines.append(f"\n## Pierwsze sprawdzenie (brak punktu odniesienia) — {total_first}\n")
        for r in first_content:
            lines.append(f"- {r.source.category} {r.source.item_name}: {r.source.url}\n")
        for r in first_feeds:
            lines.append(f"- feed {r.source.kind} {r.source.key}: {r.source.url}\n")

    return "\n".join(lines)


def main() -> int:
    ffs._ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", help="zapisz raport Markdown do podanego pliku")
    args = parser.parse_args()

    content_sources = discover_attraction_sources()
    feed_sources = discover_feed_sources()

    content_results = [check_content_source(s) for s in content_sources]
    feed_results = [check_feed_source(s) for s in feed_sources]

    report = render_markdown(content_results, feed_results)
    print(report)
    if args.summary:
        Path(args.summary).write_text(report, encoding="utf-8")

    all_changed = any(r.changed for r in content_results) or any(r.changed for r in feed_results)
    all_errors = any(r.error for r in content_results) or any(r.error for r in feed_results)
    if all_changed:
        return 1
    if all_errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
