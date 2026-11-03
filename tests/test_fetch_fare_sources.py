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
    _write_source_file(isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf")
    sources = ffs.discover_sources()
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/pkp.pdf"
    assert sources[0].data_file == "pkp_intercity.json"


def test_first_check_has_no_previous_snapshot_and_is_not_flagged_changed(
    isolated_data_dir, monkeypatch
):
    _write_source_file(isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf")
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"wersja 1"))

    [source] = ffs.discover_sources()
    result = ffs.check_source(source)

    assert result.first_check is True
    assert result.changed is False
    assert result.error is None


def test_unchanged_content_between_runs_is_not_flagged(isolated_data_dir, monkeypatch):
    _write_source_file(isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf")
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"ta sama zawartosc"))
    [source] = ffs.discover_sources()

    ffs.check_source(source)  # pierwszy przebieg: zapisuje snapshot
    result = ffs.check_source(source)  # drugi przebieg: ta sama treść

    assert result.changed is False
    assert result.first_check is False


def test_changed_content_between_runs_is_flagged(isolated_data_dir, monkeypatch):
    _write_source_file(isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf")
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
    _write_source_file(isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf")
    [source] = ffs.discover_sources()

    def raise_error(*a, **k):
        raise ffs.requests.ConnectionError("brak dostepu do hosta")

    monkeypatch.setattr(ffs.requests, "get", raise_error)
    result = ffs.check_source(source)

    assert result.error == "brak dostepu do hosta"
    assert result.changed is False


def test_retry_po_jednej_nieudanej_probie_udaje_sie_na_kolejnej(isolated_data_dir, monkeypatch):
    """Retry ma przeżyć pojedynczy gubiony connect/read bez wpisywania źródła do raportu
    jako błąd."""
    _write_source_file(isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf")
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
    _write_source_file(isolated_data_dir, "pkp_intercity.json", "https://example.com/pkp.pdf")
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
    _write_source_file(isolated_data_dir, "vrr_eezy.json", "https://example.com/vrr.pdf")
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
    _write_source_file(isolated_data_dir, "bahncard.json", "https://example.com/bahncard")
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


def test_check_source_wykrywa_realna_zmiane_w_tekscie_poza_script(isolated_data_dir, monkeypatch):
    """Normalizacja nie może ukrywać realnych zmian — to jest sedno przewagi tego projektu
    (dokładność cen/zniżek), więc zmiana w tekście widocznym (nie w <script>/<style>) musi
    nadal być wykrywana."""
    _write_source_file(isolated_data_dir, "bahncard.json", "https://example.com/bahncard")
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


def _write_zrodlo(data_dir: Path, name: str, text: str) -> None:
    (data_dir / name).write_text(json.dumps({"_zrodlo": text}), encoding="utf-8")


def test_url_z_przecinkami_w_sciezce_nie_jest_ucinany(isolated_data_dir):
    """Regresja: mpk_krakow.json ma adres krakow.pl/aktualnosci/283607,26,komunikat,...html;
    stary URL_RE ucinał go na pierwszym przecinku (".../283607") i watcher dostawał 404."""
    url = "https://krakow.pl/aktualnosci/283607,26,komunikat,dla_uczniow_podstawowek.html"
    _write_zrodlo(
        isolated_data_dir, "mpk_krakow.json", f"Komunikat ({url} ). Wymagana legitymacja."
    )
    [source] = ffs.discover_sources()
    assert source.url == url


def test_przecinek_konczacy_zdanie_nadal_oddziela_adresy(isolated_data_dir):
    _write_zrodlo(
        isolated_data_dir,
        "bahncard.json",
        "https://www.bahn.de/a/vergleich, https://www.bahn.de/b/c, a potem https://x.pl/d.",
    )
    assert [s.url for s in ffs.discover_sources()] == [
        "https://www.bahn.de/a/vergleich",
        "https://www.bahn.de/b/c",
        "https://x.pl/d",
    ]


def test_url_pdf_ze_spacjami_w_sciezce_nie_jest_ucinany(isolated_data_dir):
    """Regresja: pkp_spi_pl_de.json ma ".../Przepisy i taryfy/Cennik_SPI_...pdf" (spacje, nie
    %20); stary URL_RE kończył na spacji i sprawdzał ucięte ".../Przepisy"."""
    url = "https://www.intercity.pl/pl/dokumenty/Przepisy i taryfy/Cennik_SPI_Polska-Niemcy_od_19.08.2026.pdf"
    _write_zrodlo(isolated_data_dir, "pkp_spi_pl_de.json", url)
    [source] = ffs.discover_sources()
    assert source.url == url


def test_url_ze_spacja_nie_pochlania_opisu_ani_kolejnego_adresu(isolated_data_dir):
    _write_zrodlo(
        isolated_data_dir,
        "x.json",
        "Zob. https://a.pl/strona oficjalny cennik w pliku cennik.pdf oraz "
        "https://b.pl/dir name/plik.pdf (PDF, 2026).",
    )
    assert [s.url for s in ffs.discover_sources()] == [
        "https://a.pl/strona",
        "https://b.pl/dir name/plik.pdf",
    ]


def test_real_data_mpk_krakow_i_pkp_spi_maja_pelne_adresy():
    urls = {(s.data_file, s.url) for s in ffs.discover_sources()}
    assert (
        "mpk_krakow.json",
        "https://krakow.pl/aktualnosci/283607,26,komunikat,dla_uczniow_podstawowek_komunikacja_bezplatna_caly_rok.html",
    ) in urls
    assert (
        "pkp_spi_pl_de.json",
        "https://www.intercity.pl/pl/dokumenty/Przepisy i taryfy/Cennik_SPI_Polska-Niemcy_od_19.08.2026.pdf",
    ) in urls
    assert not any(
        u
        in (
            "https://krakow.pl/aktualnosci/283607",
            "https://www.intercity.pl/pl/dokumenty/Przepisy",
        )
        for _, u in urls
    )


_STRONA_A = """<!DOCTYPE html><html><head><meta name="csrf-token" content="Zm9vYmFyMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="><title>Cennik</title>
<script nonce="aaa111">window.t=1760443200;var s="2026-10-14T10:00:00Z";</script>
<style nonce="aaa111">.a{color:red}</style></head>
<body><!-- render 1760443200123 -->
<form><input type="hidden" name="token" value="deadbeefdeadbeefdeadbeefdeadbeef"></form>
<p data-req="9f1c2b3a-1111-2222-3333-444455556666">Bilet normalny:   4,60 zł</p>
<p>Obowiązuje od 2026-09-01.</p><div>Aktualizacja: 2026-10-14 10:00:05</div>
<noscript>Włącz JavaScript</noscript></body></html>""".encode()

_STRONA_B = """<!DOCTYPE html>
<html><head><title>Cennik</title><meta name="csrf-token" content="QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCMTIz">
<script nonce="zzz999">window.t=1760529600;var s="2026-10-15T11:11:11Z";</script></head>
<body><!-- render 1760529600999 -->

<p data-req="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee">Bilet&nbsp;normalny: 4,60&nbsp;zł</p>
<p>Obowiązuje   od 2026-09-01.</p>
<div>Aktualizacja: 2026-10-15 11:11:11</div>
<form><input type="hidden" name="token" value="cafebabecafebabecafebabecafebabe"></form>
</body></html>""".encode()


def test_normalize_dwie_wersje_tej_samej_strony_z_roznym_szumem_daja_ten_sam_hash():
    url = "https://example.com/cennik"
    assert ffs._normalize_for_hash(_STRONA_A, url) == ffs._normalize_for_hash(_STRONA_B, url)


def test_normalize_zachowuje_widoczna_tresc_i_daty_bez_godziny():
    out = ffs._normalize_for_hash(_STRONA_A, "https://example.com/cennik").decode()
    assert "Bilet normalny: 4,60 zł" in out
    assert "2026-09-01" in out
    assert "Cennik" in out  # <title> jest widoczny w karcie przeglądarki
    for szum in ("nonce", "csrf", "1760443200", "deadbeef", "9f1c2b3a", "10:00:05"):
        assert szum not in out


def test_normalize_wykrywa_zmiane_ceny_mimo_szumu():
    zmieniona = _STRONA_B.replace(b"4,60", b"4,80")
    url = "https://example.com/cennik"
    assert ffs._normalize_for_hash(_STRONA_A, url) != ffs._normalize_for_hash(zmieniona, url)


def test_normalize_pdf_po_rozszerzeniu_z_query_i_po_sygnaturze():
    tresc = b"%PDF-1.7 <script>x</script>  2026-10-14T10:00:00Z"
    assert ffs._normalize_for_hash(tresc, "https://example.com/c.pdf?v=2") == tresc
    assert ffs._normalize_for_hash(tresc, "https://example.com/pobierz") == tresc


def test_check_source_ignoruje_szum_miedzy_przebiegami(isolated_data_dir, monkeypatch):
    _write_source_file(isolated_data_dir, "bahncard.json", "https://example.com/cennik")
    [source] = ffs.discover_sources()
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(_STRONA_A))
    ffs.check_source(source)
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(_STRONA_B))
    assert ffs.check_source(source).changed is False


def test_zrodla_tylko_recznie_nie_sa_pobierane_i_nie_daja_bledu(isolated_data_dir, monkeypatch):
    url = next(iter(ffs.MANUAL_ONLY_SOURCES))
    _write_source_file(isolated_data_dir, "pkp_intercity.json", url)
    [source] = ffs.discover_sources()

    def nie_wolac(*a, **k):
        raise AssertionError("źródło 'tylko ręcznie' nie powinno być pobierane")

    monkeypatch.setattr(ffs.requests, "get", nie_wolac)
    result = ffs.check_source(source)

    assert result.error is None
    assert result.changed is False
    assert result.manual_only
    assert not (isolated_data_dir / ".snapshots").exists()
    assert "Tylko ręcznie" in ffs.render_markdown([result])
    assert url in ffs.render_markdown([result])


def test_main_zrodla_tylko_recznie_nie_zmieniaja_kodu_wyjscia(
    isolated_data_dir, monkeypatch, capsys
):
    _write_source_file(isolated_data_dir, "pkp_intercity.json", next(iter(ffs.MANUAL_ONLY_SOURCES)))
    monkeypatch.setattr(sys, "argv", ["fetch_fare_sources.py"])
    monkeypatch.setattr(ffs.requests, "get", lambda *a, **k: FakeResponse(b"", status=403))
    assert ffs.main() == 0


def test_dwa_pdfy_intercity_z_pkp_intercity_json_sa_tylko_recznie():
    zrodla = [s for s in ffs.discover_sources() if s.data_file == "pkp_intercity.json"]
    assert len(zrodla) == 2
    assert all(s.url in ffs.MANUAL_ONLY_SOURCES for s in zrodla)
    intercity = [u for u in ffs.MANUAL_ONLY_SOURCES if "intercity.pl" in u]
    assert len(intercity) == 5
    assert all(u.startswith("https://www.intercity.pl/") for u in intercity)
    assert "https://global.api.flixbus.com/search/service/v4/search" in ffs.MANUAL_ONLY_SOURCES
