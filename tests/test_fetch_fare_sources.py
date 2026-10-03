import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_fare_sources as ffs  # noqa: E402


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200, cookies=None):
        self.content = content
        self.status_code = status
        self.cookies = cookies if cookies is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ffs.requests.HTTPError(f"status {self.status_code}")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Żaden test nie powinien naprawdę czekać na backoff retry (RETRY_BACKOFF_SECONDS)."""
    monkeypatch.setattr(ffs, "_sleep", lambda seconds: None)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(ffs, "DATA_DIR", data_dir)
    monkeypatch.setattr(ffs, "SNAPSHOT_DIR", data_dir / ".snapshots")
    return data_dir


def _write_source_file(data_dir: Path, name: str, url: str) -> None:
    (data_dir / name).write_text(
        json.dumps({"_zrodlo": f"Oficjalny cennik — {url} (sprawdzone 2026-10-03)."}),
        encoding="utf-8",
    )


def test_discover_sources_extracts_urls_from_zrodlo_fields(isolated_data_dir):
    _write_source_file(
        isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf"
    )
    sources = ffs.discover_sources()
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/pkp.pdf"
    assert sources[0].data_file == "pkp_intercity.json"


def test_first_check_has_no_previous_snapshot_and_is_not_flagged_changed(
    isolated_data_dir, monkeypatch
):
    _write_source_file(
        isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf"
    )
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"wersja 1"))

    [source] = ffs.discover_sources()
    result = ffs.check_source(source)

    assert result.first_check is True
    assert result.changed is False
    assert result.error is None


def test_unchanged_content_between_runs_is_not_flagged(isolated_data_dir, monkeypatch):
    _write_source_file(
        isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf"
    )
    monkeypatch.setattr(
        ffs.requests, "get", lambda *a, **k: FakeResponse(b"ta sama zawartosc")
    )
    [source] = ffs.discover_sources()

    ffs.check_source(source)  # pierwszy przebieg: zapisuje snapshot
    result = ffs.check_source(source)  # drugi przebieg: ta sama treść

    assert result.changed is False
    assert result.first_check is False


def test_changed_content_between_runs_is_flagged(isolated_data_dir, monkeypatch):
    _write_source_file(
        isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf"
    )
    [source] = ffs.discover_sources()

    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"wersja 1"))
    ffs.check_source(source)

    monkeypatch.setattr(
        ffs.requests,
        "get",
        lambda *a, **k: FakeResponse(b"wersja 2 (cena sie zmienila)"),
    )
    result = ffs.check_source(source)

    assert result.changed is True
    assert result.previous_sha256 != result.new_sha256


def test_fetch_error_is_reported_without_crashing(isolated_data_dir, monkeypatch):
    _write_source_file(
        isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf"
    )
    [source] = ffs.discover_sources()

    def raise_error(*a, **k):
        raise ffs.requests.ConnectionError("brak dostepu do hosta")

    monkeypatch.setattr(ffs.requests, "get", raise_error)
    result = ffs.check_source(source)

    assert result.error == "brak dostepu do hosta"
    assert result.changed is False


def test_retry_po_jednej_nieudanej_probie_udaje_sie_na_kolejnej(
    isolated_data_dir, monkeypatch
):
    """Retry ma przeżyć pojedynczy gubiony connect/read bez wpisywania źródła do raportu
    jako błąd."""
    _write_source_file(
        isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf"
    )
    [source] = ffs.discover_sources()

    calls = {"n": 0}

    def flaky_get(*a, **k):
        calls["n"] += 1
        if calls["n"] < ffs.RETRY_ATTEMPTS:
            raise ffs.requests.ConnectionError("connection reset (mock)")
        return FakeResponse(b"tresc pdf")

    monkeypatch.setattr(ffs.requests, "get", flaky_get)
    result = ffs.check_source(source)

    assert result.error is None
    assert result.first_check is True
    assert calls["n"] == ffs.RETRY_ATTEMPTS


def test_retry_wyczerpany_zglasza_blad_z_ostatniej_proby(isolated_data_dir, monkeypatch):
    _write_source_file(
        isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf"
    )
    [source] = ffs.discover_sources()

    calls = {"n": 0}

    def always_fails(*a, **k):
        calls["n"] += 1
        raise ffs.requests.ConnectionError(f"proba {calls['n']} nieudana")

    monkeypatch.setattr(ffs.requests, "get", always_fails)
    result = ffs.check_source(source)

    assert result.error == f"proba {ffs.RETRY_ATTEMPTS} nieudana"
    assert calls["n"] == ffs.RETRY_ATTEMPTS


def test_fetch_with_retry_wysyla_realistyczny_user_agent(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return FakeResponse(b"tresc pdf")

    monkeypatch.setattr(ffs.requests, "get", fake_get)
    ffs._fetch_with_retry("https://example.com/cennik.pdf", timeout=30)

    assert "Chrome" in captured["headers"]["User-Agent"]


def test_main_exit_codes(isolated_data_dir, monkeypatch, capsys):
    _write_source_file(
        isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf"
    )
    monkeypatch.setattr(sys, "argv", ["fetch_fare_sources.py"])

    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"v1"))
    assert ffs.main() == 0  # pierwsze sprawdzenie, brak zmiany do zaraportowania

    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"v2"))
    assert ffs.main() == 1  # zmiana wykryta


def test_ensure_utf8_stdout_nie_wywala_sie_bez_reconfigure(monkeypatch):
    """Windows: konsola domyślnie w cp1250 nie ogarnia ⚠️/polskich znaków w raporcie —
    zweryfikowane na żywo jako realny crash (`UnicodeEncodeError`) przed tym fixem.
    `reconfigure` może nie istnieć (np. stdout przekierowany w testach/CI) — to nie powinno
    wywalać main()."""

    class StdoutBezReconfigure:
        pass  # brak metody reconfigure - symuluje stdout, który jej nie ma

    monkeypatch.setattr(ffs.sys, "stdout", StdoutBezReconfigure())
    ffs._ensure_utf8_stdout()  # nie powinno podnieść wyjątku


def test_normalize_for_hash_usuwa_script_i_komentarze_z_html():
    html = b"""<html><head><script>var nonce="abc123";</script></head>
    <body><!-- cache-bust: xyz --><p>Cena: 29.99 EUR</p><style>.x{color:red}</style></body></html>"""
    normalized = ffs._normalize_for_hash(html, "https://bahn.de/oferta")
    assert b"nonce" not in normalized
    assert b"cache-bust" not in normalized
    assert b"color:red" not in normalized
    assert b"29.99 EUR" in normalized


def test_normalize_for_hash_ignoruje_pdf():
    content = b"<script>to jest binarna zawartosc pdf, nie html</script>"
    assert ffs._normalize_for_hash(content, "https://example.com/cennik.pdf") == content


def test_check_source_ignoruje_zmiane_tylko_w_script_na_stronie_html(
    isolated_data_dir, monkeypatch
):
    """To jest regresja na żywo złapany false-positive: bahn.de wyszło jako "zmienione" w
    dwóch przebiegach ~20 min od siebie, mimo że cena najpewniej się nie zmieniła — podejrzenie
    paść na niedeterministyczną treść w <script> (nonce/cache-busting)."""
    _write_source_file(
        isolated_data_dir, "bahncard.json", "https://example.com/bahncard"
    )
    [source] = ffs.discover_sources()

    monkeypatch.setattr(
        ffs.requests,
        "get",
        lambda *a, **k: FakeResponse(
            b'<html><script>var nonce="aaa";</script><body>Cena: 25%</body></html>'
        ),
    )
    ffs.check_source(source)

    monkeypatch.setattr(
        ffs.requests,
        "get",
        lambda *a, **k: FakeResponse(
            b'<html><script>var nonce="bbb-inny-token";</script><body>Cena: 25%</body></html>'
        ),
    )
    result = ffs.check_source(source)

    assert result.changed is False


def test_check_source_wykrywa_realna_zmiane_w_tekscie_poza_script(
    isolated_data_dir, monkeypatch
):
    """Normalizacja nie może ukrywać realnych zmian — to jest sedno przewagi tego projektu
    (dokładność cen/zniżek), więc zmiana w tekście widocznym (nie w <script>/<style>) musi
    nadal być wykrywana."""
    _write_source_file(
        isolated_data_dir, "bahncard.json", "https://example.com/bahncard"
    )
    [source] = ffs.discover_sources()

    monkeypatch.setattr(
        ffs.requests,
        "get",
        lambda *a, **k: FakeResponse(
            b'<html><script>var nonce="aaa";</script><body>Cena: 25%</body></html>'
        ),
    )
    ffs.check_source(source)

    monkeypatch.setattr(
        ffs.requests,
        "get",
        lambda *a, **k: FakeResponse(
            b'<html><script>var nonce="bbb";</script><body>Cena: 30%</body></html>'
        ),
    )
    result = ffs.check_source(source)

    assert result.changed is True


def test_real_fares_data_has_discoverable_sources():
    """Sanity check na prawdziwych danych repo — gwarantuje, że przyszłe zmiany formatu
    fares/data/*.json (np. zmiana nazwy pola _zrodlo) nie wyłączą cichutko całego pipeline'u.
    """
    sources = ffs.discover_sources()
    assert len(sources) >= 5
    files_covered = {s.data_file for s in sources}
    assert "pkp_intercity.json" in files_covered
    assert "vrr_eezy.json" in files_covered
