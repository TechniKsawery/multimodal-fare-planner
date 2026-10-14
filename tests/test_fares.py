from datetime import date

import pytest

from fares import PriceType, _flixbus_api, estimate_price
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
        Carrier.PKP_INTERCITY,
        "A",
        "B",
        distance_km=100,
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
        Carrier.DB,
        "Berlin Hbf",
        "Gelsenkirchen Hbf",
        distance_km=550,
        discounts=DiscountProfile(bahncard="25"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(148 * 0.75)


@pytest.mark.parametrize(
    "km,lo,hi", [(190, 42.30, 114.20), (285, 80, 100), (373, 106, 127), (570, 99.90, 185.10)]
)
def test_db_flexpreis_miesci_sie_w_realnych_przedzialach(km, lo, hi):
    seg = Segment(Carrier.DB, "A", "B", distance_km=km)
    assert lo <= estimate_price(seg).amount <= hi


# --- FlixBus: realna cena z API (zmockowana), z fallbackiem do PLN/km -----------------------


def test_flixbus_bez_travel_date_spada_od_razu_do_fallbacku_km():
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600)
    result = estimate_price(seg)
    assert result.price_type is PriceType.ESTIMATE
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.amount == pytest.approx(600 * 0.27)


def test_flixbus_uzywa_najtanszego_wyniku_z_api(monkeypatch):
    monkeypatch.setattr(
        _flixbus_api, "find_city_id", lambda city, **kw: {"Lublin": "1", "Berlin": "2"}[city]
    )
    monkeypatch.setattr(
        _flixbus_api,
        "fetch_cheapest_trip",
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
    seg = Segment(
        Carrier.FLIXBUS, "Lublin", "Gelsenkirchen", distance_km=1000, travel_date="2026-11-15"
    )
    result = estimate_price(seg)
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.amount == pytest.approx(1000 * 0.27)


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
        Carrier.VRR,
        "Gelsenkirchen Hbf",
        "Essen Hbf",
        distance_km=10,
        discounts=DiscountProfile(vrr_dziecko=True),
    )
    cena_normalna = estimate_price(normalny).amount
    result = estimate_price(dziecko)
    assert result.amount == pytest.approx(cena_normalna * 0.5, abs=0.01)
    assert result.price_type is PriceType.OFFICIAL


def test_vrr_kindertarif_dziala_tez_na_sufit_cenowy():
    dziecko = Segment(
        Carrier.VRR,
        "Gelsenkirchen Hbf",
        "Bonn Hbf",
        distance_km=200,
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
        Carrier.ZTM_LUBLIN,
        "Ogród Saski",
        "Dworzec Lublin",
        ride_duration_min=8,
        discounts=DiscountProfile(ztm_lublin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 1.70


def test_ztm_lublin_bilet_bezplatny_uczen_podstawowki():
    seg = Segment(
        Carrier.ZTM_LUBLIN,
        "Ogród Saski",
        "Dworzec Lublin",
        ride_duration_min=8,
        discounts=DiscountProfile(ztm_lublin_bezplatny=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_ztm_lublin_bezplatny_ma_priorytet_nad_ulgowym():
    seg = Segment(
        Carrier.ZTM_LUBLIN,
        "Ogród Saski",
        "Dworzec Lublin",
        ride_duration_min=8,
        discounts=DiscountProfile(ztm_lublin_bezplatny=True, ztm_lublin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_ztm_lublin_dobiera_dluzszy_bilet():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=35)
    result = estimate_price(seg)
    assert result.amount == 4.60  # bilet 40-minutowy


def test_ztm_lublin_przekroczenie_najdluzszego_biletu_to_szacunek():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=2000)
    result = estimate_price(seg)
    assert result.amount == 14.20  # ekstrapolacja na bazie biletu 24-godzinnego
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
        "bc25_standard",
        "bc50_standard",
        "my_bc25_19_26",
        "my_bc50_19_26",
    }
    assert results[0].variant_key in {"my_bc25_19_26", "my_bc50_19_26"}


def test_bahncard_jugend_darmowa_w_trakcie_promocji():
    results = suggest_bahncard(550, journeys_per_year=2, age=15, reference_date=date(2026, 10, 15))
    jugend = next(r for r in results if r.variant_key == "jugend_bc25_6_18")
    assert jugend.cena_karty == 0.0
    assert jugend.rekomendowana is True


def test_bahncard_jugend_placi_standardowa_cene_po_koncu_promocji():
    results = suggest_bahncard(550, journeys_per_year=2, age=15, reference_date=date(2026, 12, 13))
    jugend = next(r for r in results if r.variant_key == "jugend_bc25_6_18")
    assert jugend.cena_karty == 7.90


def test_bahncard_jugend_placi_standardowa_cene_przed_poczatkiem_promocji():
    results = suggest_bahncard(550, journeys_per_year=2, age=15, reference_date=date(2026, 10, 6))
    jugend = next(r for r in results if r.variant_key == "jugend_bc25_6_18")
    assert jugend.cena_karty == 7.90


def test_bahncard_nieprawidlowa_odleglosc_podnosi_blad():
    with pytest.raises(ValueError):
        suggest_bahncard(0, journeys_per_year=2)


def test_bahncard_juz_posiadana_ta_sama_karta_nie_jest_sugerowana():
    # bug zgłoszony przez usera: miał już wybraną BahnCard 25 w formularzu, a mimo to
    # dostawał sugestię kupna (darmowej w promocji) Jugend BahnCard 25 — czyli karty
    # o dokładnie takim samym rabacie (25%), którą już posiada. Jugend BC25 (25%, tak samo
    # jak posiadana) nie powinna się już pojawić — jedyny sensowny upgrade to BC50 (50%).
    results = suggest_bahncard(
        550,
        journeys_per_year=2,
        age=15,
        reference_date=date(2026, 9, 27),
        existing_bahncard="25",
    )
    assert "jugend_bc25_6_18" not in {r.variant_key for r in results}
    assert {r.variant_key for r in results} == {"bc50_standard"}


def test_bahncard_juz_posiadana_karta_pokazuje_tylko_realny_upgrade():
    # user ma BahnCard 25 (25%) — jedyna sensowna sugestia to karta z LEPSZYM rabatem (50%),
    # a oszczędność musi być liczona względem ceny, którą user już płaci z BC25, nie od zera.
    results = suggest_bahncard(550, journeys_per_year=2, age=None, existing_bahncard="25")
    assert {r.variant_key for r in results} == {"bc50_standard"}
    bc50 = results[0]
    current_price = 148 * 0.75  # cena, którą user już płaci z posiadaną BC25
    assert bc50.cena_biletu_bez_karty == pytest.approx(current_price, abs=0.01)
    assert bc50.cena_biletu_z_karta == pytest.approx(148 * 0.5, abs=0.01)


def test_bahncard_juz_posiadana_najlepsza_karta_brak_sugestii():
    # user ma BahnCard 50 — żadna inna karta nie da lepszego rabatu, więc lista jest pusta
    # (zamiast mylącej sugestii kupna czegoś gorszego lub tego samego).
    results = suggest_bahncard(550, journeys_per_year=2, age=None, existing_bahncard="50")
    assert results == []


def _flixbus_search_payload(results: dict) -> dict:
    """Kształt odpowiedzi /search/service/v4/search (trips[0].results)."""
    return {"trips": [{"results": results}]}


class _FakeFlixbusResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_flixbus_pomija_przejazdy_z_cena_zero_z_api(monkeypatch):
    # Regresja: live API zwróciło przejazd z ceną 0 (08:15) obok realnych ofert po 16,99 EUR;
    # wcześniej min() wybierał 0,00 EUR i cała trasa była błędnie tania.
    payload = _flixbus_search_payload(
        {
            "direct:a": {"price": {"total": 17.99, "currency": "EUR"}},
            "direct:zero": {"price": {"total": 0, "currency": "EUR"}},
            "direct:b": {"price": {"total": 16.99, "currency": "EUR"}},
        }
    )
    monkeypatch.setattr(
        _flixbus_api.requests, "get", lambda *a, **kw: _FakeFlixbusResponse(payload)
    )
    trip = _flixbus_api.fetch_cheapest_trip("1", "2", "2026-10-09")
    assert trip["price"]["total"] == 16.99


def test_flixbus_gdy_wszystkie_przejazdy_maja_cene_zero_rzuca_blad_i_spada_do_fallbacku(
    monkeypatch,
):
    payload = _flixbus_search_payload({"direct:zero": {"price": {"total": 0, "currency": "EUR"}}})
    monkeypatch.setattr(
        _flixbus_api.requests, "get", lambda *a, **kw: _FakeFlixbusResponse(payload)
    )
    with pytest.raises(_flixbus_api.FlixbusApiError):
        _flixbus_api.fetch_cheapest_trip("1", "2", "2026-10-09")

    monkeypatch.setattr(_flixbus_api, "find_city_id", lambda city, **kw: "1")
    monkeypatch.setattr(
        _flixbus_api,
        "fetch_cheapest_trip",
        lambda *a, **kw: (_ for _ in ()).throw(_flixbus_api.FlixbusApiError("cena 0")),
    )
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600, travel_date="2026-10-09")
    result = estimate_price(seg)
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.amount > 0


# --- Ulgi transportu miejskiego: Warszawa, Kraków, Poznań, Wrocław, Berlin --------------------


def test_ztm_warszawa_bilet_20_minutowy_normalny():
    seg = Segment(Carrier.ZTM_WARSZAWA, "Centrum", "Plac Zamkowy", ride_duration_min=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "PLN"
    assert result.amount == 3.40


def test_ztm_warszawa_bilet_20_minutowy_ulgowy():
    seg = Segment(
        Carrier.ZTM_WARSZAWA,
        "Centrum",
        "Plac Zamkowy",
        ride_duration_min=10,
        discounts=DiscountProfile(ztm_warszawa_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 1.70


def test_ztm_warszawa_bilet_bezplatny_uczen_podstawowki():
    seg = Segment(
        Carrier.ZTM_WARSZAWA,
        "Centrum",
        "Plac Zamkowy",
        ride_duration_min=10,
        discounts=DiscountProfile(ztm_warszawa_bezplatny=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_ztm_warszawa_bilet_90_minutowy():
    seg = Segment(Carrier.ZTM_WARSZAWA, "A", "B", ride_duration_min=80)
    result = estimate_price(seg)
    assert result.amount == 7.00


def test_ztm_warszawa_bez_czasu_jazdy_podnosi_blad():
    seg = Segment(Carrier.ZTM_WARSZAWA, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_mpk_krakow_bilet_15_minutowy_normalny():
    seg = Segment(Carrier.MPK_KRAKOW, "Rynek", "Wawel", ride_duration_min=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == 4.00


def test_mpk_krakow_bilet_60_minutowy_ulgowy():
    seg = Segment(
        Carrier.MPK_KRAKOW,
        "Rynek",
        "Nowa Huta",
        ride_duration_min=45,
        discounts=DiscountProfile(mpk_krakow_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 4.00  # bilet 60-minutowy ulgowy (8 PLN / 2), cennik od 2.03.2026


def test_mpk_krakow_bilet_bezplatny_uczen_podstawowki():
    seg = Segment(
        Carrier.MPK_KRAKOW,
        "Rynek",
        "Nowa Huta",
        ride_duration_min=45,
        discounts=DiscountProfile(mpk_krakow_bezplatny=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_mpk_krakow_przekroczenie_najdluzszego_biletu_to_szacunek():
    seg = Segment(Carrier.MPK_KRAKOW, "A", "B", ride_duration_min=120)
    result = estimate_price(seg)
    assert result.price_type is PriceType.ESTIMATE
    assert result.amount == 9.00


def test_ztm_poznan_bilet_15_minutowy_normalny():
    seg = Segment(Carrier.ZTM_POZNAN, "Stary Rynek", "Katedra", ride_duration_min=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == 5.00  # cennik od 1.09.2025


def test_ztm_poznan_bilet_bezplatny_senior_70_plus():
    seg = Segment(
        Carrier.ZTM_POZNAN,
        "A",
        "B",
        ride_duration_min=10,
        discounts=DiscountProfile(ztm_poznan_bezplatny=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_ztm_poznan_bezplatny_ma_priorytet_nad_ulgowym():
    seg = Segment(
        Carrier.ZTM_POZNAN,
        "A",
        "B",
        ride_duration_min=10,
        discounts=DiscountProfile(ztm_poznan_bezplatny=True, ztm_poznan_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_ztm_poznan_bilet_90_minutowy_ulgowy():
    seg = Segment(
        Carrier.ZTM_POZNAN,
        "A",
        "B",
        ride_duration_min=90,
        discounts=DiscountProfile(ztm_poznan_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 4.50


def test_mpk_wroclaw_bilet_30_minutowy_normalny():
    seg = Segment(Carrier.MPK_WROCLAW, "Rynek", "Dworzec Główny", ride_duration_min=25)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == 4.00


def test_mpk_wroclaw_bilet_60_minutowy_ulgowy():
    seg = Segment(
        Carrier.MPK_WROCLAW,
        "A",
        "B",
        ride_duration_min=50,
        discounts=DiscountProfile(mpk_wroclaw_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 2.60


def test_mpk_wroclaw_bilet_bezplatny_uczen():
    seg = Segment(
        Carrier.MPK_WROCLAW,
        "A",
        "B",
        ride_duration_min=50,
        discounts=DiscountProfile(mpk_wroclaw_bezplatny=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_mpk_wroclaw_bezplatny_ma_priorytet_nad_ulgowym():
    seg = Segment(
        Carrier.MPK_WROCLAW,
        "A",
        "B",
        ride_duration_min=50,
        discounts=DiscountProfile(mpk_wroclaw_bezplatny=True, mpk_wroclaw_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_bvg_berlin_kurzstrecke_normalny():
    seg = Segment(Carrier.BVG_BERLIN, "Alexanderplatz", "Hackescher Markt", ride_duration_min=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == 2.80  # cennik VBB od 1.01.2026


def test_bvg_berlin_strefa_ab_ulgowy():
    seg = Segment(
        Carrier.BVG_BERLIN,
        "Alexanderplatz",
        "Potsdam Hbf",
        ride_duration_min=60,
        discounts=DiscountProfile(bvg_berlin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 2.50


def test_bvg_berlin_schwerbehindert_bezplatny():
    seg = Segment(
        Carrier.BVG_BERLIN,
        "Alexanderplatz",
        "Potsdam Hbf",
        ride_duration_min=60,
        discounts=DiscountProfile(bvg_berlin_schwerbehindert=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_bvg_berlin_schwerbehindert_ma_priorytet_nad_ulgowym():
    seg = Segment(
        Carrier.BVG_BERLIN,
        "Alexanderplatz",
        "Potsdam Hbf",
        ride_duration_min=60,
        discounts=DiscountProfile(bvg_berlin_schwerbehindert=True, bvg_berlin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0


def test_bvg_berlin_bez_czasu_jazdy_podnosi_blad():
    seg = Segment(Carrier.BVG_BERLIN, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_hvv_einzelkarte_normalny():
    seg = Segment(Carrier.HVV, "Hauptbahnhof", "Landungsbrücken")
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == 4.10  # Tarifstand 01.01.2026, najniższa strefa


def test_hvv_einzelkarte_dziecko():
    seg = Segment(
        Carrier.HVV, "A", "B", discounts=DiscountProfile(hvv_dziecko=True),
    )
    result = estimate_price(seg)
    assert result.amount == 1.50


def test_mvv_einzelfahrkarte_zone_m_normalny():
    seg = Segment(Carrier.MVV, "Marienplatz", "Hauptbahnhof")
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == 4.20  # ceny od 01.01.2026, Zone M


def test_mvv_einzelfahrkarte_zone_m_dziecko():
    seg = Segment(
        Carrier.MVV, "A", "B", discounts=DiscountProfile(mvv_dziecko=True),
    )
    result = estimate_price(seg)
    assert result.amount == 2.00


def test_vrs_koln_estimate_official_preisstufe_1b():
    """VRS/Köln: tabela Einzelticket na vrs.de (Stand 01.06.2026, sprawdzona w przeglądarce
    2026-10-11) podaje Preisstufe 1b = 4,00 EUR (dziecko 1,80 EUR)."""
    seg = Segment(Carrier.VRS_KOLN, "Dom/Hauptbahnhof", "Neumarkt")
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == 4.00  # Preisstufe 1b, vrs.de Einzelticket


def test_vrs_koln_dziecko_tansze_niz_normalny():
    seg_normalny = Segment(Carrier.VRS_KOLN, "A", "B")
    seg_dziecko = Segment(
        Carrier.VRS_KOLN, "A", "B", discounts=DiscountProfile(vrs_koln_dziecko=True),
    )
    assert estimate_price(seg_dziecko).amount < estimate_price(seg_normalny).amount


def test_hvv_schwerbehinderte_bezplatnie():
    seg = Segment(
        Carrier.HVV, "A", "B", discounts=DiscountProfile(schwerbehinderte_wertmarke_de=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0
    assert result.price_type is PriceType.OFFICIAL


def test_mvv_schwerbehinderte_bezplatnie():
    seg = Segment(
        Carrier.MVV, "A", "B", discounts=DiscountProfile(schwerbehinderte_wertmarke_de=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0
    assert result.price_type is PriceType.OFFICIAL


def test_vrs_koln_schwerbehinderte_bezplatnie():
    seg = Segment(
        Carrier.VRS_KOLN, "A", "B", discounts=DiscountProfile(schwerbehinderte_wertmarke_de=True),
    )
    result = estimate_price(seg)
    assert result.amount == 0.0
    assert result.price_type is PriceType.OFFICIAL


# --- DB: opcjonalne nieoficjalne źródło cen (db-vendo-client), domyślnie wyłączone -----------

def _db_seg(**kw):
    return Segment(Carrier.DB, "Berlin Hbf", "Essen Hbf", distance_km=500, travel_date="2026-11-15", **kw)


def test_db_nieoficjalne_domyslnie_wylaczone(monkeypatch):
    from fares import _db_vendo_api

    monkeypatch.delenv("UNOFFICIAL_PRICES", raising=False)
    monkeypatch.setattr(_db_vendo_api, "fetch_cheapest", lambda *a, **k: pytest.fail("nie wolno wołać"))
    assert "zrodlo" not in estimate_price(_db_seg()).breakdown


def test_db_nieoficjalne_wlaczone_uzywa_ceny_i_etykietuje(monkeypatch, tmp_path):
    from fares import _db_vendo_api

    monkeypatch.setenv("UNOFFICIAL_PRICES", "1")
    monkeypatch.setenv("UNOFFICIAL_PRICES_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        _db_vendo_api, "fetch_cheapest", lambda *a, **k: {"amount": 29.9, "currency": "EUR"}
    )
    result = estimate_price(_db_seg())
    assert result.amount == 29.9
    assert result.price_type is PriceType.ESTIMATE
    assert result.breakdown["zrodlo"] == "nieoficjalne_db_vendo"
    assert "NIEOFICJALNEGO" in result.notes


def test_db_nieoficjalne_blad_wraca_do_tabeli(monkeypatch):
    from fares import _db_vendo_api

    monkeypatch.setenv("UNOFFICIAL_PRICES", "1")

    def boom(*a, **k):
        raise _db_vendo_api.DbVendoError("zablokowane")

    monkeypatch.setattr(_db_vendo_api, "fetch_cheapest", boom)
    result = estimate_price(_db_seg())
    assert "flexpreis_gorna_granica" in result.breakdown and "zrodlo" not in result.breakdown


def test_unofficial_limit_zapytan_i_cache(monkeypatch, tmp_path):
    from fares import _unofficial

    monkeypatch.setenv("UNOFFICIAL_PRICES_PER_MINUTE", "2")
    monkeypatch.setenv("UNOFFICIAL_PRICES_CACHE_DIR", str(tmp_path))
    _unofficial._calls.clear()
    assert _unofficial.allow_request("x") and _unofficial.allow_request("x")
    assert not _unofficial.allow_request("x")
    _unofficial.cache_set("x", "k", {"a": 1})
    assert _unofficial.cache_get("x", "k") == {"a": 1}


# --- Informacja w UI: kto jedzie bezpłatnie / dlaczego cena 0 -----------------------------------


def test_explain_ticket_bezplatny_i_ulgowy_i_normalny():
    from fares.eligibility_info import explain_ticket

    assert "bezpłatny" in explain_ticket({"typ_biletu": "bezpłatny (100%)"})
    assert "ulgowy" in explain_ticket({"typ_biletu": "ulgowy (50%)"})
    assert explain_ticket({"typ_biletu": "normalny"}) is None
    assert explain_ticket({}) is None


def test_eligibility_info_miasta_z_bezplatnym_maja_zrodlo():
    from fares.eligibility_info import ELIGIBILITY

    for carrier, (miasto, bezplatne, _ulgowe, zrodlo) in ELIGIBILITY.items():
        assert bezplatne and zrodlo.startswith("https://"), miasto
    # Poznań: uczniowie TYLKO ulgowo (potwierdzone w fares/data/ztm_poznan.json)
    assert not any("uczniowie" in t for t in ELIGIBILITY[__import__("fares.model").model.Carrier.ZTM_POZNAN][1])


# --- Dzieci poniżej 6 lat jadą bezpłatnie: HVV/MVV/VRS (źródła w fares/data/*.json) -------------

@pytest.mark.parametrize("carrier,dziecko_flag", [
    (Carrier.HVV, "hvv_dziecko"), (Carrier.MVV, "mvv_dziecko"), (Carrier.VRS_KOLN, "vrs_koln_dziecko"),
])
def test_dziecko_ponizej_6_lat_bezplatnie_granice_wieku(carrier, dziecko_flag):
    def cena(age, **kw):
        return estimate_price(Segment(carrier, "A", "B", discounts=DiscountProfile(age=age, **kw)))

    for age in (0, 4, 5):
        r = cena(age)
        assert r.amount == 0.0 and r.price_type is PriceType.OFFICIAL
        assert r.breakdown["typ_biletu"].startswith("bezpłatny")
    # 6 lat = już płaci (taryfa dziecięca przy zaznaczonym checkboxie, normalna bez)
    assert cena(6).amount > 0
    assert 0 < cena(6, **{dziecko_flag: True}).amount < cena(6).amount
    # brak wieku: bez zmian
    assert cena(None).amount > 0
    # reguła ma źródło i datę
    from fares._data_loading import load
    plik = {Carrier.HVV: "hvv.json", Carrier.MVV: "mvv.json", Carrier.VRS_KOLN: "vrs_koln.json"}[carrier]
    regula = load(plik)["dzieci_ponizej_6_lat_bezplatnie"]
    assert regula["zrodlo_url"].startswith("https://") and regula["data_weryfikacji"]


# --- DB krajowe: BahnCard 25/50/100 przy cenie krajowej, brak ulg wiekowych ---
def _db_segment(bahncard=None, age=None, km=250):
    from fares.model import Carrier, DiscountProfile, Segment

    return Segment(
        carrier=Carrier.DB,
        origin="A",
        destination="B",
        distance_km=km,
        discounts=DiscountProfile(bahncard=bahncard, age=age),
    )


def test_db_bahncard_mnozniki_przy_cenie_krajowej():
    from fares import db

    base = db.estimate(_db_segment()).amount
    assert base == 97
    assert db.estimate(_db_segment("25")).amount == round(97 * 0.75, 2)
    assert db.estimate(_db_segment("50")).amount == 48.5
    assert db.estimate(_db_segment("100")).amount == 0.0


def test_db_bahncard_100_oznaczony_jako_niepotwierdzony():
    from fares import db

    bc100 = db.estimate(_db_segment("100"))
    assert bc100.breakdown["mnoznik_potwierdzony"] is False
    assert "NIEPOTWIERDZONY" in bc100.notes
    for bc in (None, "25", "50"):
        est = db.estimate(_db_segment(bc))
        assert est.breakdown["mnoznik_potwierdzony"] is True


def test_db_krajowe_nie_czyta_wieku():
    from fares import db

    assert {db.estimate(_db_segment(age=a)).amount for a in (None, 3, 10, 70)} == {97}


def test_api_schema_ma_child_with_guardian():
    from api.schemas import DiscountProfileIn
    from fares.model import DiscountProfile

    p = DiscountProfileIn(child_with_guardian=True)
    assert DiscountProfile(**p.model_dump()).child_with_guardian is True
