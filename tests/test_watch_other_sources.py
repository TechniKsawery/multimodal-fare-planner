import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import watch_other_sources as wos  # noqa: E402


class FakeResponse:
    def __init__(self, content: bytes = b"", status: int = 200, headers: dict | None = None):
        self.content = content
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise wos.requests.HTTPError(f"status {self.status_code}")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(wos.ffs, "_sleep", lambda seconds: None)


@pytest.fixture
def isolated_attractions_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "attractions_data"
    data_dir.mkdir()
    monkeypatch.setattr(wos, "ATTRACTIONS_DATA_DIR", data_dir)
    monkeypatch.setattr(wos, "ATTRACTIONS_SNAPSHOT_DIR", data_dir / ".snapshots")
    return data_dir


@pytest.fixture
def isolated_gtfs_snapshot_dir(tmp_path, monkeypatch):
    snap_dir = tmp_path / "gtfs_snapshots"
    monkeypatch.setattr(wos, "GTFS_SNAPSHOT_DIR", snap_dir)
    return snap_dir


def _write_attractions(data_dir: Path, items: list[dict]) -> None:
    (data_dir / "attractions.json").write_text(
        json.dumps({"_zrodlo": "test", "atrakcje": items}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_city_cards(data_dir: Path, items: list[dict]) -> None:
    (data_dir / "city_cards.json").write_text(
        json.dumps({"_zrodlo": "test", "karty": items}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_discover_attraction_sources_extracts_official_url(isolated_attractions_dir):
    _write_attractions(
        isolated_attractions_dir,
        [{"id": "a1", "name": "Atrakcja 1", "official_url": "https://example.com/a1"}],
    )
    sources = wos.discover_attraction_sources()
    assert len(sources) == 1
    assert sources[0].category == "atrakcja"
    assert sources[0].url == "https://example.com/a1"


def test_discover_attraction_sources_skips_items_without_url(isolated_attractions_dir):
    _write_attractions(isolated_attractions_dir, [{"id": "a1", "name": "Bez URL"}])
    assert wos.discover_attraction_sources() == []


def test_discover_city_card_sources_extracts_official_url(isolated_attractions_dir):
    _write_city_cards(
        isolated_attractions_dir,
        [{"id": "c1", "name": "Karta 1", "official_url": "https://example.com/c1"}],
    )
    [source] = wos.discover_attraction_sources()
    assert source.category == "karta miejska"
    assert source.data_file == "city_cards.json"


def test_check_content_source_first_check(isolated_attractions_dir, monkeypatch):
    _write_attractions(
        isolated_attractions_dir,
        [{"id": "a1", "name": "A1", "official_url": "https://example.com/a1"}],
    )
    monkeypatch.setattr(wos.requests, "get", lambda *a, **k: FakeResponse(b"v1"))
    [source] = wos.discover_attraction_sources()
    result = wos.check_content_source(source)

    assert result.first_check is True
    assert result.changed is False


def test_check_content_source_detects_change(isolated_attractions_dir, monkeypatch):
    _write_attractions(
        isolated_attractions_dir,
        [{"id": "a1", "name": "A1", "official_url": "https://example.com/a1"}],
    )
    [source] = wos.discover_attraction_sources()

    monkeypatch.setattr(wos.requests, "get", lambda *a, **k: FakeResponse(b"cena: 10 EUR"))
    wos.check_content_source(source)

    monkeypatch.setattr(wos.requests, "get", lambda *a, **k: FakeResponse(b"cena: 15 EUR"))
    result = wos.check_content_source(source)

    assert result.changed is True


def test_check_content_source_reports_error_without_crashing(isolated_attractions_dir, monkeypatch):
    _write_attractions(
        isolated_attractions_dir,
        [{"id": "a1", "name": "A1", "official_url": "https://example.com/a1"}],
    )
    [source] = wos.discover_attraction_sources()

    def raise_error(*a, **k):
        raise wos.requests.ConnectionError("brak dostepu")

    monkeypatch.setattr(wos.requests, "get", raise_error)
    result = wos.check_content_source(source)

    assert result.error == "brak dostepu"
    assert result.changed is False


def test_discover_feed_sources_includes_gtfs_and_osm():
    sources = wos.discover_feed_sources()
    kinds = {s.kind for s in sources}
    keys = {s.key for s in sources}
    assert "GTFS" in kinds
    assert "OSM" in kinds
    assert "gtfs/pl/polish_trains.zip" in keys


def test_check_feed_source_first_check_uses_head(isolated_gtfs_snapshot_dir, monkeypatch):
    captured = {}

    def fake_head(url, **kwargs):
        captured["url"] = url
        return FakeResponse(headers={"ETag": "abc", "Content-Length": "123"})

    monkeypatch.setattr(wos.requests, "head", fake_head)
    source = wos.FeedSource(key="gtfs/pl/test.zip", url="https://example.com/test.zip", kind="GTFS")
    result = wos.check_feed_source(source)

    assert captured["url"] == "https://example.com/test.zip"
    assert result.first_check is True
    assert result.changed is False


def test_check_feed_source_detects_header_change(isolated_gtfs_snapshot_dir, monkeypatch):
    source = wos.FeedSource(key="gtfs/pl/test.zip", url="https://example.com/test.zip", kind="GTFS")

    monkeypatch.setattr(
        wos.requests, "head", lambda *a, **k: FakeResponse(headers={"ETag": "v1"})
    )
    wos.check_feed_source(source)

    monkeypatch.setattr(
        wos.requests, "head", lambda *a, **k: FakeResponse(headers={"ETag": "v2"})
    )
    result = wos.check_feed_source(source)

    assert result.changed is True


def test_check_feed_source_unchanged_headers_not_flagged(isolated_gtfs_snapshot_dir, monkeypatch):
    source = wos.FeedSource(key="gtfs/pl/test.zip", url="https://example.com/test.zip", kind="GTFS")
    monkeypatch.setattr(
        wos.requests, "head", lambda *a, **k: FakeResponse(headers={"ETag": "v1"})
    )
    wos.check_feed_source(source)
    result = wos.check_feed_source(source)

    assert result.changed is False
    assert result.first_check is False


def test_main_exit_codes(isolated_attractions_dir, isolated_gtfs_snapshot_dir, monkeypatch):
    _write_attractions(
        isolated_attractions_dir,
        [{"id": "a1", "name": "A1", "official_url": "https://example.com/a1"}],
    )
    monkeypatch.setattr(sys, "argv", ["watch_other_sources.py"])
    monkeypatch.setattr(wos.requests, "get", lambda *a, **k: FakeResponse(b"v1"))
    monkeypatch.setattr(wos.requests, "head", lambda *a, **k: FakeResponse(headers={"ETag": "v1"}))

    assert wos.main() == 0  # pierwsze sprawdzenie wszystkiego, brak zmiany do zaraportowania

    monkeypatch.setattr(wos.requests, "get", lambda *a, **k: FakeResponse(b"v2 zmiana"))
    assert wos.main() == 1  # zmiana wykryta w atrakcji


def test_real_attractions_data_has_discoverable_sources():
    """Sanity check na prawdziwych danych repo, jak w test_fetch_fare_sources.py — gwarantuje,
    że zmiana formatu attractions/data/*.json nie wyłączy cichutko tego watchera."""
    sources = wos.discover_attraction_sources()
    assert len(sources) >= 5
    categories = {s.category for s in sources}
    assert "atrakcja" in categories
    assert "karta miejska" in categories
