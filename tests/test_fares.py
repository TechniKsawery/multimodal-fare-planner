from datetime import date

import pytest

from fares import PriceType, estimate_price
from fares import _flixbus_api, flixbus
from fares.cards import suggest_bahncard
from fares.model import Carrier, DiscountProfile, Segment


def test_pkp_bez_ulgi():
    seg = Segment(Carrier.PKP_INTERCITY, "Lublin", "Warszawa Wschodnia", distance_km=170)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == 50
    assert result.currency == "PLN"


def test_pkp_z_ulga_studencka_51():
    seg = Segment(
        Carrier.PKP_INTERCITY,
        "Lublin",
        "Warszawa Wschodnia",
        distance_km=170,
        discounts=DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(50 * 0.49, abs=0.01)


def test_pkp_nieznana_ulga():
    seg = Segment(
        Carrier.PKP_INTERCITY, "A", "B", distance_km=100,
        discounts=DiscountProfile(pkp_ulga_kod="nieistniejaca"),
    )
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_db_flexpreis_bez_bahncard():
    seg = Segment(Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550)
    result = estimate_price(seg)
    assert result.amount == 148
    assert result.currency == "EUR"
    assert result.price_type is PriceType.ESTIMATE


def test_db_flexpreis_z_bahncard25():
    seg = Segment(
        Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550,
        discounts=DiscountProfile(bahncard="25"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(148 * 0.75)


@pytest.mark.parametrize("km,lo,hi", [(190, 42.30, 114.20), (285, 80, 100), (373, 106, 127), (570, 99.90, 185.10)])
def test_db_flexpreis_miesci_sie_w_realnych_przedzialach(km, lo, hi):
    seg = Segment(Carrier.DB, "A", "B", distance_km=km)
    assert lo <= estimate_price(seg).amount <= hi


# --- FlixBus: realna cena z API (zmockowana), z fallbackiem do PLN/km -----------------------

def test_flixbus_bez_travel_date_spada_od_razu_do_fallbacku_km():
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600)
    result = estimate_price(seg)
    assert result.price_type is PriceType.ESTIMATE
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.amount == pytest.approx(600 * 0.35)


def test_flixbus_uzywa_najtanszego_wyniku_z_api(monkeypatch):
    monkeypatch.setattr(_flixbus_api, "find_city_id", lambda city, **kw: {"Lublin": "1", "Berlin": "2"}[city])
    monkeypatch.setattr(
        _flixbus_api, "fetch_cheapest_trip",
        lambda *a, **kw: {"price": {"total": 89.99, "currency": "EUR"}, "transfer_count": 0},
    )
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600, travel_date="2026-11-15")
    result = estimate_price(seg)
    assert result.price_type is PriceType.ESTIMATE
    assert result.amount == 89.99
    assert result.currency == "EUR"
    assert result.breakdown["zrodlo"] == "api_flixbus_live"


def test_flixbus_spada_do_fallbacku_km_gdy_api_rzuca_blad(monkeypatch):
    def boom(*a, **kw):
        raise _flixbus_api.FlixbusApiError("brak połączenia dla tej relacji/daty")

    monkeypatch.setattr(_flixbus_api, "find_city_id", boom)
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Gelsenkirchen", distance_km=1000, travel_date="2026-11-15")
    result = estimate_price(seg)
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.amount == pytest.approx(1000 * 0.35)


def test_flixbus_bez_distance_km_i_bez_travel_date_rzuca_blad():
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin")
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_vrr_grundpreis_plus_km():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == pytest.approx(1.73 + 0.29 * 10, abs=0.01)


def test_vrr_sufit_cenowy_ograniczajacy_dlugi_dystans():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Bonn Hbf", distance_km=200)
    result = estimate_price(seg)
    assert result.amount == 19.80  # sufit preisstufe C


def test_vrr_bez_dystansu_podnosi_blad():
    seg = Segment(Carrier.VRR, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_flixbus_api_find_city_id_cache_uzywa_pamieci_procesu(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            calls.append(1)
            return [{"id": 42, "name": "Lublin"}]

    monkeypatch.setattr(_flixbus_api.requests, "get", lambda *a, **kw: FakeResponse())
    _flixbus_api._city_id_cache.clear()
    assert _flixbus_api.find_city_id("Lublin") == "42"
    assert _flixbus_api.find_city_id("Lublin") == "42"
    assert len(calls) == 1  # drugie wywołanie z cache, bez nowego zapytania


def test_vrr_kindertarif_50_procent_rabatu():
    normalny = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10)
    dziecko = Segment(
        Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10,
        discounts=DiscountProfile(vrr_dziecko=True),
    )
    cena_normalna = estimate_price(normalny).amount
    result = estimate_price(dziecko)
    assert result.amount == pytest.approx(cena_normalna * 0.5, abs=0.01)
    assert result.price_type is PriceType.OFFICIAL


def test_vrr_kindertarif_dziala_tez_na_sufit_cenowy():
    dziecko = Segment(
        Carrier.VRR, "Gelsenkirchen Hbf", "Bonn Hbf", distance_km=200,
        discounts=DiscountProfile(vrr_dziecko=True),
    )
    assert estimate_price(dziecko).amount == pytest.approx(19.80 * 0.5, abs=0.01)


def test_ztm_lublin_krotki_przejazd_bilet_15_minutowy():
    seg = Segment(Carrier.ZTM_LUBLIN, "Ogród Saski", "Dworzec Lublin", ride_duration_min=8)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "PLN"
    assert result.amount == 3.40


def test_ztm_lublin_ulgowy():
    seg = Segment(
        Carrier.ZTM_LUBLIN, "Ogród Saski", "Dworzec Lublin", ride_duration_min=8,
        discounts=DiscountProfile(ztm_lublin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 1.70


def test_ztm_lublin_dobiera_dluzszy_bilet():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=35)
    result = estimate_price(seg)
    assert result.amount == 4.60  # bilet 40-minutowy


def test_ztm_lublin_przekroczenie_najdluzszego_biletu_to_szacunek():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=120)
    result = estimate_price(seg)
    assert result.amount == 5.20  # ekstrapolacja na bazie biletu 90-minutowego
    assert result.price_type is PriceType.ESTIMATE


def test_ztm_lublin_bez_czasu_jazdy_podnosi_blad():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)


# --- BahnCard: sugestia opłacalności karty ------------------------------------------------

def test_bahncard_bez_wieku_widzi_tylko_warianty_standardowe():
    results = suggest_bahncard(550, journeys_per_year=2, age=None)
    assert {r.variant_key for r in results} == {"bc25_standard", "bc50_standard"}


def test_bahncard_25_standard_oplaca_sie_na_dlugiej_trasie_dwa_razy_w_roku():
    results = suggest_bahncard(550, journeys_per_year=2, age=None)
    top = results[0]
    assert top.variant_key == "bc25_standard"
    assert top.rekomendowana is True
    # 2 x 148 EUR bez karty vs 2 x 148 x 0.75 + 62.90 z kartą
    assert top.oszczednosc_rocznie == pytest.approx(2 * 148 - (2 * 148 * 0.75 + 62.90), abs=0.01)
    # realna cena biletu (jednego przejazdu) pokazana obok samej oszczędności
    assert top.cena_biletu_bez_karty == 148
    assert top.cena_biletu_z_karta == pytest.approx(148 * 0.75, abs=0.01)


def test_bahncard_50_standard_nie_oplaca_sie_przy_jednej_podrozy_ale_podaje_prog():
    results = suggest_bahncard(550, journeys_per_year=1, age=None)
    bc50 = next(r for r in results if r.variant_key == "bc50_standard")
    assert bc50.rekomendowana is False
    assert bc50.journeys_needed_to_break_even is not None
    assert bc50.journeys_needed_to_break_even > 1


def test_bahncard_mloda_osoba_19_26_widzi_tansze_warianty_my_bahncard():
    results = suggest_bahncard(550, journeys_per_year=2, age=22)
    assert {r.variant_key for r in results} == {
        "bc25_standard", "bc50_standard", "my_bc25_19_26", "my_bc50_19_26",
    }
    assert results[0].variant_key in {"my_bc25_19_26", "my_bc50_19_26"}


def test_bahncard_jugend_darmowa_w_trakcie_promocji():
    results = suggest_bahncard(550, journeys_per_year=2, age=15, reference_date=date(2026, 9, 27))
    jugend = next(r for r in results if r.variant_key == "jugend_bc25_6_18")
    assert jugend.cena_karty == 0.0
    assert jugend.rekomendowana is True


def test_bahncard_jugend_placi_standardowa_cene_po_koncu_promocji():
    results = suggest_bahncard(550, journeys_per_year=2, age=15, reference_date=date(2026, 10, 15))
    jugend = next(r for r in results if r.variant_key == "jugend_bc25_6_18")
    assert jugend.cena_karty == 7.90


def test_bahncard_nieprawidlowa_odleglosc_podnosi_blad():
    with pytest.raises(ValueError):
        suggest_bahncard(0, journeys_per_year=2)
