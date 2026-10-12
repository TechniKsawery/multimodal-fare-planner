"""Regresje z testu na żywo PR #97: wartość zastępcza 4,00 i ceny niepotwierdzone.

1) 4,00 EUR "oficjalna_taryfa" dla BER -> Potsdamer Platz / Lichtenberg to bilet BVG AB z
   fares/data/bvg_berlin.json (udokumentowany), ale BER leży w strefie C — potrzebny ABC.
2) Wartość zastępcza LOCAL_BUS_FLAT_PLN (4,00 PLN) i inne ceny niepotwierdzone nie mogą wygrać
   rankingu "Najtańsza" z wariantem o potwierdzonej cenie.
3) demo.py dopisuje "cena niepotwierdzona" tak samo jak UI.

Współrzędne są przybliżone (do ok. 0,01°) — wystarczą do rozróżnienia miejsc, nie są danymi
cenowymi."""

from datetime import datetime, timedelta

import pytest

import demo
from fares import _flixbus_api, estimate_price
from fares._data_loading import load
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing, scoring
from routing.model import Itinerary, Leg, LegMode, PricedLeg

FLUGHAFEN_BER = (52.3644, 13.5108)
POTSDAMER_PLATZ = (52.5096, 13.3759)
BERLIN_LICHTENBERG = (52.5103, 13.4964)
BERLIN_ALEXANDERPLATZ = (52.5219, 13.4132)
SZCZECIN_GLOWNY = (53.4285, 14.5528)
ANGERMUENDE = (53.0136, 13.9947)
ZGORZELEC = (51.1500, 15.0200)
GOERLITZ = (51.1468, 14.9757)


def _leg(
    mode,
    origin,
    destination,
    origin_xy=None,
    destination_xy=None,
    *,
    carrier="",
    minutes=30,
    motis_mode=None,
):
    depart = datetime(2026, 10, 20, 8, 0)
    extra = {"motis_mode": motis_mode} if motis_mode else {}
    distance_km = 10.0
    if origin_xy and destination_xy:
        extra.update(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
        distance_km = motis_client.haversine_km(*origin_xy, *destination_xy)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name=carrier,
        distance_km=distance_km,
        extra=extra,
    )


# --- 1) Skąd 4,00 EUR i strefa C (BER) ------------------------------------------------------


def test_4_eur_to_udokumentowany_bilet_ab_z_cennika_vbb_nie_wartosc_zastepcza():
    tabela = load("bvg_berlin.json")
    assert "vbb.de" in tabela["_zrodlo"] and "Zweryfikowano" in tabela["_zrodlo"]
    ab = next(b for b in tabela["bilety_czasowe"] if b["strefa"] == "AB")
    assert ab["normalny"] == 4.00
    leg = _leg(
        LegMode.RAIL,
        "S+U Alexanderplatz",
        "S+U Potsdamer Platz",
        BERLIN_ALEXANDERPLATZ,
        POTSDAMER_PLATZ,
        carrier="S-Bahn Berlin GmbH",
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert (priced.amount, priced.currency, priced.price_type) == (4.00, "EUR", "oficjalna_taryfa")
    assert priced.breakdown["strefa"] == "AB"


def test_ber_potsdamer_platz_kolej_to_bilet_abc_nie_ab():
    leg = _leg(
        LegMode.RAIL,
        "Flughafen BER",
        "S+U Potsdamer Platz",
        FLUGHAFEN_BER,
        POTSDAMER_PLATZ,
        carrier="DB Regio AG",
        minutes=35,
        motis_mode="REGIONAL_RAIL",
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.BVG_BERLIN
    assert (priced.amount, priced.currency, priced.price_type) == (5.00, "EUR", "oficjalna_taryfa")
    assert priced.breakdown["strefa"] == "ABC"
    assert "strefie C" in priced.notes


def test_ber_lichtenberg_s_bahn_jako_bus_to_bilet_abc():
    # MOTIS: SUBURBAN (S-Bahn) -> LegMode.BUS (routing/motis_client.py::itinerary_to_legs).
    leg = _leg(
        LegMode.BUS,
        "Flughafen BER",
        "S+U Lichtenberg",
        FLUGHAFEN_BER,
        BERLIN_LICHTENBERG,
        carrier="S-Bahn Berlin GmbH",
        minutes=40,
        motis_mode="SUBURBAN",
    )
    priced = pricing.price_bus_leg(leg)
    assert (priced.amount, priced.currency, priced.price_type) == (5.00, "EUR", "oficjalna_taryfa")
    assert priced.breakdown["strefa"] == "ABC"


def test_ber_bez_wspolrzednych_rozpoznany_po_nazwie():
    leg = _leg(
        LegMode.BUS,
        "Flughafen BER Terminal 1-2",
        "Berlin Alexanderplatz",
        carrier="BVG",
        minutes=45,
    )
    assert pricing._bvg_tariff_zone(leg) == "ABC"
    assert (
        pricing._bvg_tariff_zone(
            _leg(LegMode.BUS, "Berliner Straße", "Alexanderplatz", carrier="BVG")
        )
        is None
    )


def test_bilet_abc_ulgowy_z_tej_samej_tabeli():
    seg = Segment(
        Carrier.BVG_BERLIN,
        "Flughafen BER",
        "Alexanderplatz",
        ride_duration_min=40,
        discounts=DiscountProfile(bvg_berlin_ulgowy=True),
        tariff_zone="ABC",
    )
    result = estimate_price(seg)
    assert (result.amount, result.price_type) == (3.50, PriceType.OFFICIAL)


def test_wartosc_zastepcza_nigdy_nie_jest_oficjalna_taryfa():
    # SKM/S-Bahn (SUBURBAN) NIE dostają już tej wartości — tests/test_suburban_pricing.py.
    for leg in (
        _leg(
            LegMode.BUS,
            "Zgorzelec",
            "Görlitz",
            ZGORZELEC,
            GOERLITZ,
            carrier="",
            minutes=10,
            motis_mode="BUS",
        ),
    ):
        priced = pricing.price_bus_leg(leg)
        assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
        assert priced.price_type == "szacunek"
        assert priced.breakdown["price_verified"] is False
        assert priced.breakdown["wartosc_zastepcza"] is True
        assert priced.unverified_label == "cena niepotwierdzona (wartość zastępcza, nie z cennika)"


# --- 2) Ranking "Najtańsza" ------------------------------------------------------------------


def _priced(amount, *, verified=True, placeholder=False, start_hour=8, minutes=120, currency="PLN"):
    depart = datetime(2026, 10, 20, start_hour, 0)
    leg = Leg(
        mode=LegMode.RAIL,
        origin_name="A",
        destination_name="B",
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name="X",
        distance_km=100.0,
    )
    breakdown = {} if verified else {"price_verified": False}
    if placeholder:
        breakdown["wartosc_zastepcza"] = True
    return PricedLeg(
        leg=leg, amount=amount, currency=currency, price_type="szacunek", breakdown=breakdown
    )


def test_wariant_z_wartoscia_zastepcza_nie_wygrywa_najtanszej_z_potwierdzonym():
    # Szczecin -> Berlin: 4 PLN wartości zastępczej (SKM) + szacunek PLN/km vs wariant potwierdzony.
    z_zastepcza = scoring.build_itinerary(
        "SKM + RE",
        [
            _priced(4.0, verified=False, placeholder=True),
            _priced(23.0, verified=False, start_hour=11),
        ],
    )
    potwierdzony = scoring.build_itinerary("autokar + BVG", [_priced(60.0)])
    assert not z_zastepcza.is_infeasible
    assert z_zastepcza.total_price_pln < potwierdzony.total_price_pln
    assert not z_zastepcza.price_verified and potwierdzony.price_verified

    recs = scoring.pick_recommendations([z_zastepcza, potwierdzony])

    assert recs["najtansza"] is potwierdzony
    assert recs["najtansza_bezpieczna"] is potwierdzony
    assert scoring.cheaper_unverified([z_zastepcza, potwierdzony], potwierdzony) == [z_zastepcza]
    note = scoring.price_ranking_note("najtansza", potwierdzony, [z_zastepcza, potwierdzony])
    assert "Pominięto 1 wariant(y)" in note and "SKM + RE" in note


def test_bez_potwierdzonego_wariantu_najtansza_nominalnie_z_jawna_uwaga():
    a = scoring.build_itinerary("A", [_priced(30.0, verified=False)])
    b = scoring.build_itinerary("B", [_priced(10.0, verified=False, placeholder=True)])

    recs = scoring.pick_recommendations([a, b])

    assert recs["najtansza"] is b
    note = scoring.price_ranking_note("najtansza", b, [a, b])
    assert note.startswith("Żaden wariant w tej kategorii nie ma w pełni potwierdzonej ceny")
    assert scoring.price_ranking_note("najszybsza", b, [a, b]) is None


def test_bez_cen_niepotwierdzonych_ranking_bez_zmian_i_bez_uwagi():
    tania = scoring.build_itinerary("tania", [_priced(20.0)])
    droga = scoring.build_itinerary("droga", [_priced(80.0)])
    recs = scoring.pick_recommendations([tania, droga])
    assert recs["najtansza"] is tania
    assert scoring.price_ranking_note("najtansza", tania, [tania, droga]) is None


def test_itinerary_bez_legow_jest_potwierdzony():
    # _itinerary() w tests/test_routing.py buduje warianty bez legów — ranking jak dotąd po cenie.
    pusty = Itinerary(
        variant_name="x", legs=[], total_price_pln=1.0, total_duration_min=1.0, num_transfers=0
    )
    assert pusty.price_verified


# --- 3) demo.py: dopisek "cena niepotwierdzona" ----------------------------------------------


def test_demo_format_itinerary_oznacza_ceny_niepotwierdzone():
    itinerary = scoring.build_itinerary(
        "SKM + RE",
        [
            _priced(4.0, verified=False, placeholder=True),
            _priced(23.0, verified=False, start_hour=11),
            _priced(5.0, currency="EUR", start_hour=14, minutes=30),
        ],
    )
    text = demo.format_itinerary(itinerary)
    lines = text.splitlines()
    assert "cena niepotwierdzona (zawiera odcinki bez potwierdzonej taryfy)" in lines[1]
    assert "4.00 PLN (szacunek) — cena niepotwierdzona (wartość zastępcza, nie z cennika)" in text
    assert "23.00 PLN (szacunek) — cena niepotwierdzona" in text
    eur_line = next(line for line in lines if "5.00 EUR" in line)
    assert "niepotwierdzona" not in eur_line


def test_demo_format_itinerary_bez_dopisku_dla_potwierdzonych_cen():
    itinerary = scoring.build_itinerary("IC", [_priced(50.0)])
    assert "niepotwierdzona" not in demo.format_itinerary(itinerary)


# --- 4) FlixBus: cena z fallbacku km jest niepotwierdzona, z live API nie --------------------


def _flixbus_leg(depart_hour=8):
    depart = datetime(2026, 10, 20, depart_hour, 0)
    return Leg(
        mode=LegMode.BUS,
        origin_name="Lublin",
        destination_name="Berlin",
        depart=depart,
        arrive=depart + timedelta(hours=9),
        carrier_name="FlixBus",
        distance_km=600.0,
        extra={"motis_mode": "BUS"},
    )


def _flixbus_api_nie_dziala(monkeypatch):
    def boom(*a, **kw):
        raise _flixbus_api.FlixbusApiError("brak sieci (test)")

    monkeypatch.setattr(_flixbus_api, "find_city_id", boom)


def _flixbus_api_dziala(monkeypatch, payload=None):
    monkeypatch.setattr(
        _flixbus_api, "find_city_id", lambda city, **kw: {"Lublin": "1", "Berlin": "2"}[city]
    )
    monkeypatch.setattr(
        _flixbus_api,
        "fetch_cheapest_trip",
        lambda *a, **kw: payload or {"price": {"total": 19.99, "currency": "EUR"}},
    )


def test_flixbus_fallback_km_w_fares_ma_price_verified_false(monkeypatch):
    _flixbus_api_nie_dziala(monkeypatch)
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600, travel_date="2026-10-20")
    result = estimate_price(seg)
    assert result.breakdown["zrodlo"] == "fallback_km"
    assert result.breakdown["price_verified"] is False
    assert result.amount == pytest.approx(600 * 0.27)


def test_flixbus_z_live_api_nie_ma_flagi_niepotwierdzonej(monkeypatch):
    _flixbus_api_dziala(monkeypatch)
    seg = Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600, travel_date="2026-10-20")
    result = estimate_price(seg)
    assert result.breakdown["zrodlo"] == "api_flixbus_live"
    assert "price_verified" not in result.breakdown


def test_flixbus_fallback_przy_bledzie_bez_daty_i_zlej_odpowiedzi_jest_niepotwierdzony(
    monkeypatch,
):
    # bez travel_date (API wymaga daty)
    bez_daty = estimate_price(Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600))
    assert bez_daty.breakdown["price_verified"] is False
    # API odpowiada, ale bez ceny
    _flixbus_api_dziala(monkeypatch, payload={"price": {}})
    zla_odpowiedz = estimate_price(
        Segment(Carrier.FLIXBUS, "Lublin", "Berlin", distance_km=600, travel_date="2026-10-20")
    )
    assert zla_odpowiedz.breakdown["zrodlo"] == "fallback_km"
    assert zla_odpowiedz.breakdown["price_verified"] is False


def test_odcinek_flixbus_z_fallbacku_jest_niepotwierdzony_z_dopiskiem(monkeypatch):
    _flixbus_api_nie_dziala(monkeypatch)
    priced = pricing.price_bus_leg(_flixbus_leg())
    assert priced.breakdown["zrodlo"] == "fallback_km"
    assert not priced.price_verified
    assert priced.unverified_label == "cena niepotwierdzona"  # ten sam tekst co przy innych


def test_odcinek_flixbus_z_live_api_zostaje_potwierdzony(monkeypatch):
    _flixbus_api_dziala(monkeypatch)
    priced = pricing.price_bus_leg(_flixbus_leg())
    assert priced.breakdown["zrodlo"] == "api_flixbus_live"
    assert priced.amount == 19.99 and priced.currency == "EUR"
    assert priced.price_verified
    assert priced.unverified_label == ""


def test_flixbus_fallback_nie_wygrywa_najtanszej_z_potwierdzona_cena(monkeypatch):
    _flixbus_api_nie_dziala(monkeypatch)
    flix = scoring.build_itinerary("Flixbus", [pricing.price_bus_leg(_flixbus_leg())])
    potwierdzony = scoring.build_itinerary("Intercity", [_priced(300.0)])
    assert flix.total_price_pln < potwierdzony.total_price_pln  # 600 km x 0,27 = 162 zł < 300 zł
    assert not flix.price_verified and potwierdzony.price_verified

    recs = scoring.pick_recommendations([flix, potwierdzony])

    assert recs["najtansza"] is potwierdzony
    assert scoring.cheaper_unverified([flix, potwierdzony], potwierdzony) == [flix]


def test_flixbus_z_live_api_nadal_moze_wygrac_najtanszej(monkeypatch):
    _flixbus_api_dziala(monkeypatch, payload={"price": {"total": 15.0, "currency": "EUR"}})
    flix = scoring.build_itinerary("Flixbus", [pricing.price_bus_leg(_flixbus_leg())])
    potwierdzony = scoring.build_itinerary("Intercity", [_priced(300.0)])
    assert flix.price_verified
    assert scoring.pick_recommendations([flix, potwierdzony])["najtansza"] is flix


def test_demo_format_itinerary_oznacza_flixbusa_z_fallbacku_ale_nie_z_api(monkeypatch):
    _flixbus_api_nie_dziala(monkeypatch)
    z_fallbacku = scoring.build_itinerary("Flixbus", [pricing.price_bus_leg(_flixbus_leg())])
    text = demo.format_itinerary(z_fallbacku)
    assert "cena niepotwierdzona (zawiera odcinki bez potwierdzonej taryfy)" in text
    assert "162.00 PLN (szacunek) — cena niepotwierdzona" in text

    _flixbus_api_dziala(monkeypatch)
    z_api = scoring.build_itinerary("Flixbus", [pricing.price_bus_leg(_flixbus_leg())])
    assert "niepotwierdzona" not in demo.format_itinerary(z_api)
