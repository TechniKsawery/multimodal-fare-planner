"""Ekran wyniku: statusy cen (oficjalna taryfa / szacunek / brak ceny), źródło i data weryfikacji.

Testuje wyłącznie prezentację (ui_helpers.py) - wyceny nie są ruszane. Statusy wynikają z pól, które
model już ma; nigdy nie mogą być mocniejsze niż dane (zob. leg_price_status)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import i18n
from i18n import LANGUAGES, t
from routing import motis_client, search_service
from routing.model import Itinerary, Leg, LegMode, PricedLeg
from routing.scoring import pick_recommendations
from ui_helpers import (
    PRICE_ESTIMATE,
    PRICE_NO_PRICE,
    PRICE_OFFICIAL,
    cheapest_variant_cards,
    format_verified_date,
    is_price_confirmed,
    itinerary_price_status,
    itinerary_verification,
    leg_price_status,
    leg_source,
    source_host,
    status_cell,
)

ROOT = Path(__file__).resolve().parent.parent


def _leg(mode=LegMode.RAIL, a="A", b="B"):
    return Leg(
        mode=mode,
        origin_name=a,
        destination_name=b,
        depart=datetime(2026, 10, 18, 6, tzinfo=UTC),
        arrive=datetime(2026, 10, 18, 8, tzinfo=UTC),
        carrier_name="PKP Intercity",
    )


def _priced(price_type="oficjalna_taryfa", amount=40.0, mode=LegMode.RAIL, **breakdown):
    return PricedLeg(_leg(mode), amount, "PLN", price_type, breakdown=breakdown)


def _itinerary(*legs, high=None):
    return Itinerary(
        variant_name="Test",
        legs=list(legs),
        total_price_pln=sum(p.amount for p in legs if p.price_known),
        total_duration_min=120.0,
        num_transfers=0,
        total_price_pln_high=high,
    )


# --- status odcinka ------------------------------------------------------------------------------


def test_oficjalna_taryfa_to_oficjalna():
    assert leg_price_status(_priced()) == PRICE_OFFICIAL


def test_oficjalna_taryfa_z_jawnym_niepotwierdzeniem_nie_jest_oficjalna():
    assert leg_price_status(_priced(price_verified=False)) == PRICE_ESTIMATE


def test_szacunek_nawet_z_flaga_potwierdzenia_nie_udaje_oficjalnej():
    # np. pasmo POLREGIO: kwota z tabeli, ale dystans szacowany (price_type "szacunek")
    assert leg_price_status(_priced("szacunek", price_verified=True)) == PRICE_ESTIMATE


def test_przedzial_cen_to_szacunek_nawet_gdy_potwierdzony():
    p = _priced(zakres_cen={"od": 1, "do": 2})
    assert leg_price_status(p) == PRICE_ESTIMATE


def test_wartosc_zastepcza_i_cena_nieznana_to_brak_ceny():
    assert leg_price_status(_priced("szacunek", wartosc_zastepcza=True)) == PRICE_NO_PRICE
    assert leg_price_status(_priced("szacunek", 0.0, cena_nieznana=True)) == PRICE_NO_PRICE


def test_odcinek_pieszy_nie_ma_statusu():
    assert leg_price_status(_priced(amount=0.0, mode=LegMode.WALK)) is None
    assert status_cell(None) == ""


# --- status całego wariantu ----------------------------------------------------------------------


def test_wariant_najslabszy_status_wygrywa():
    off, est = _priced(), _priced("szacunek")
    assert itinerary_price_status(_itinerary(off, off)) == PRICE_OFFICIAL
    assert itinerary_price_status(_itinerary(off, est)) == PRICE_ESTIMATE
    assert itinerary_price_status(_itinerary(off, _priced("szacunek", wartosc_zastepcza=True))) == PRICE_NO_PRICE


def test_wariant_z_gorna_granica_to_szacunek():
    assert itinerary_price_status(_itinerary(_priced(), high=80.0)) == PRICE_ESTIMATE


def test_cena_czesciowa_lub_brak_to_brak_ceny():
    unknown = _priced("szacunek", 0.0, cena_nieznana=True)
    assert itinerary_price_status(_itinerary(_priced(), unknown)) == PRICE_NO_PRICE
    assert itinerary_price_status(_itinerary(unknown)) == PRICE_NO_PRICE


def test_odcinek_pieszy_nie_obniza_statusu():
    walk = _priced(amount=0.0, mode=LegMode.WALK)
    assert itinerary_price_status(_itinerary(_priced(), walk)) == PRICE_OFFICIAL


# --- źródło i data weryfikacji -------------------------------------------------------------------


def test_zrodlo_i_data_tylko_gdy_podane_w_breakdown():
    assert leg_source(_priced()) == (None, None)
    p = _priced(zrodlo_url="https://www.intercity.pl/cennik", data_weryfikacji="2026-10-10")
    assert leg_source(p) == ("https://www.intercity.pl/cennik", "2026-10-10")
    # data_odczytu (KD, bilet graniczny) i "zrodlo" będące adresem (ZTM Lublin, ZVON)
    q = _priced(zrodlo="https://zdtm.lublin.eu/x", data_odczytu="2026-10-13")
    assert leg_source(q) == ("https://zdtm.lublin.eu/x", "2026-10-13")


def test_kod_zrodla_nie_adres_nie_jest_pokazywany():
    # np. "api_flixbus_live", "fallback_km" - wewnętrzne kody, nie źródła dla użytkownika
    assert leg_source(_priced("szacunek", zrodlo="api_flixbus_live")) == (None, None)


def test_host_i_format_daty():
    assert source_host("https://www.intercity.pl/a/b") == "intercity.pl"
    assert format_verified_date("2026-10-10") == "10.10.2026"
    assert format_verified_date(None) == t("source.none")
    assert format_verified_date("nie-data") == "nie-data"


def test_weryfikacja_wariantu_najstarsza_data_i_pokrycie():
    a = _priced(zrodlo_url="https://a.example/x", data_weryfikacji="2026-10-12")
    b = _priced(zrodlo_url="https://www.b.example/y", data_weryfikacji="2026-10-05")
    c = _priced()  # bez źródła
    walk = _priced(amount=0.0, mode=LegMode.WALK)
    hosts, oldest, covered, priced = itinerary_verification(_itinerary(a, b, c, walk))
    assert hosts == ["a.example", "b.example"]
    assert oldest == "2026-10-05"
    assert (covered, priced) == (2, 3)


# --- ekran w każdym języku -----------------------------------------------------------------------


def _wariant():
    ok = _priced(zrodlo_url="https://www.intercity.pl/cennik", data_weryfikacji="2026-10-10")
    fallback = _priced("szacunek", 60.0, price_verified=False, wartosc_zastepcza=True)
    return _itinerary(ok, fallback)


@pytest.fixture
def mocked_backend(monkeypatch):
    monkeypatch.setattr(
        motis_client, "geocode_suggestions", lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text}]
    )
    monkeypatch.setattr(motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")

    def fake_search(request):
        it = _wariant()
        return search_service.SearchResult(
            request=request, built=[it], skipped=[], recommendations=pick_recommendations([it])
        )

    monkeypatch.setattr(search_service, "search", fake_search)


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_ekran_wyniku_pokazuje_status_zrodlo_i_date(mocked_backend, monkeypatch, lang):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.button[0].click().run()
    assert not at.exception, at.exception

    captions = [c.value for c in at.caption]
    # wariant ma odcinek z wartością zastępczą -> status łączny "brak ceny" + jego wyjaśnienie
    assert t("badge.explain_no_price", lang=lang) in captions
    assert f"{t('col.source', lang=lang)}: intercity.pl • {t('col.verified', lang=lang)}: 10.10.2026" in captions
    assert t("source.coverage", lang=lang, n=1, total=2) in captions
    assert at.metric[1].label == t("metric.price", lang=lang)

    rows = at.dataframe[0].value
    status_col = list(rows[t("col.price_status", lang=lang)])
    assert status_col[0].endswith(t("badge.official", lang=lang))
    assert status_col[1].endswith(t("badge.no_price", lang=lang))
    assert list(rows[t("col.verified", lang=lang)])[0] == "10.10.2026"
    assert list(rows[t("col.verified", lang=lang)])[1] == t("source.none", lang=lang)
    # status ceny tylko w osobnej kolumnie: kwota bez typu ceny w nawiasie
    assert not any("oficjalna_taryfa" in v or "(" in v.split(" — ")[0] for v in rows[t("col.price", lang=lang)])


# --- karty wariantów: najtańsza potwierdzona / najtańsza wg szacunku -------------------------------


def _named(name, *legs, high=None):
    it = _itinerary(*legs, high=high)
    it.variant_name = name
    return it


def _szacunek(amount):
    return _priced("szacunek", amount, price_verified=False)


def _brak():
    return _priced("szacunek", 0.0, cena_nieznana=True)


def test_ta_sama_najtansza_to_jedna_karta():
    a = _named("A", _priced(amount=30.0))
    b = _named("B", _priced(amount=50.0))
    assert cheapest_variant_cards([b, a]) == (a, None)


def test_tansza_niepotwierdzona_daje_dwie_karty():
    potw = _named("potw", _priced(amount=80.0))
    szac = _named("szac", _szacunek(40.0))
    assert cheapest_variant_cards([potw, szac]) == (potw, szac)


def test_brak_ceny_i_cena_czesciowa_nie_wygrywaja():
    brak = _named("brak", _brak())
    czesc = _named("czesc", _priced(amount=10.0), _brak())
    pelny = _named("pelny", _szacunek(70.0))
    assert cheapest_variant_cards([brak, czesc, pelny]) == (None, pelny)
    assert cheapest_variant_cards([brak, czesc]) == (None, None)


def test_przedzial_cen_nie_jest_potwierdzony_ale_liczy_sie_jako_szacunek():
    zakres = _named("zakres", _priced(amount=20.0), high=35.0)
    assert not is_price_confirmed(zakres)
    assert cheapest_variant_cards([zakres]) == (None, zakres)


def test_odcinek_pieszy_nie_blokuje_potwierdzenia():
    it = _named("z pieszym", _priced(amount=25.0), _priced(amount=0.0, mode=LegMode.WALK, price_verified=False))
    assert is_price_confirmed(it)


def test_remis_ceny_rozstrzyga_krotszy_czas():
    wolny = _named("wolny", _priced(amount=30.0))
    szybki = _named("szybki", _priced(amount=30.0))
    szybki.total_duration_min = 60.0
    assert cheapest_variant_cards([wolny, szybki])[0] is szybki


@pytest.fixture
def two_variants_backend(mocked_backend, monkeypatch):
    potw = _named("Potwierdzony", _priced(amount=80.0))
    szac = _named("Szacunkowy", _szacunek(40.0))

    def fake_search(request):
        built = [potw, szac]
        return search_service.SearchResult(
            request=request, built=built, skipped=[], recommendations=pick_recommendations(built)
        )

    monkeypatch.setattr(search_service, "search", fake_search)


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_ekran_wyniku_ma_dwie_karty_wariantow(two_variants_backend, monkeypatch, lang):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert t("cards.confirmed", lang=lang) in text
    assert t("cards.estimate", lang=lang) in text
    assert f":orange-badge[{t('cards.estimate_tag', lang=lang)}]" in text
