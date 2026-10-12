"""Regresje: tryb MOTIS SUBURBAN (SKM, S-Bahn) to kolej, nie autobus miejski.

Wcześniej SUBURBAN -> LegMode.BUS -> price_bus_leg -> LOCAL_BUS_FLAT_PLN (4,00 PLN) nawet za
~70 km pociągu (SKM Szczecin -> Angermünde, test na żywo PR #97). Teraz:
- S-Bahn Berlin w kole BVG nadal dostaje bilet BVG (fares/data/bvg_berlin.json),
- SUBURBAN w NRW nadal dostaje eezy.nrw,
- pozostałe SUBURBAN (SKM Szczecin/Trójmiasto, S-Bahn poza znanymi taryfami) dostają
  niepotwierdzony szacunek PLN/km (NIE ryczałt autobusowy) i nie wygrywają "Najtańszej".

Współrzędne przybliżone (ok. 0,01°) — wystarczą do rozróżnienia miejsc, nie są danymi cenowymi."""

from datetime import datetime, timedelta

from fares.model import Carrier, DiscountProfile
from routing import motis_client, pricing, scoring
from routing.model import Leg, LegMode, PricedLeg

SZCZECIN_GLOWNY = (53.4285, 14.5528)
ANGERMUENDE = (53.0136, 13.9947)
GDANSK_GLOWNY = (54.3560, 18.6440)
GDYNIA_GLOWNA = (54.5200, 18.5300)
BERLIN_ALEXANDERPLATZ = (52.5219, 13.4132)
BERLIN_OSTKREUZ = (52.5030, 13.4690)
POTSDAM_HBF = (52.3919, 13.0668)
DUSSELDORF_HBF = (51.2200, 6.7940)
DUISBURG_HBF = (51.4300, 6.7750)
HANNOVER_HBF = (52.3766, 9.7410)
HANNOVER_FLUGHAFEN = (52.4590, 9.6970)


def _suburban(origin, destination, origin_xy, destination_xy, *, carrier, minutes=60):
    depart = datetime(2026, 10, 20, 8, 0)
    return Leg(
        mode=LegMode.BUS,  # tak mapuje SUBURBAN motis_client.itinerary_to_legs
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name=carrier,
        distance_km=motis_client.haversine_km(*origin_xy, *destination_xy),
        extra={
            "motis_mode": "SUBURBAN",
            "origin_lat": origin_xy[0],
            "origin_lon": origin_xy[1],
            "destination_lat": destination_xy[0],
            "destination_lon": destination_xy[1],
        },
    )


def test_motis_mapuje_suburban_na_bus_i_zachowuje_tryb_motis():
    itinerary = {
        "legs": [
            {
                "mode": "SUBURBAN",
                "from": {"name": "Szczecin Główny", "lat": 53.4285, "lon": 14.5528},
                "to": {"name": "Angermünde", "lat": 53.0136, "lon": 13.9947},
                "startTime": "2026-10-20T08:00:00Z",
                "endTime": "2026-10-20T09:00:00Z",
                "agencyName": "SKM",
            }
        ]
    }
    (leg,) = motis_client.itinerary_to_legs(itinerary)
    assert leg.mode is LegMode.BUS
    assert pricing.is_suburban_leg(leg)


def test_skm_szczecin_angermunde_nie_dostaje_ryczaltu_autobusowego():
    leg = _suburban(
        "Szczecin Główny", "Angermünde", SZCZECIN_GLOWNY, ANGERMUENDE, carrier="SKM", minutes=60
    )
    priced = pricing.price_bus_leg(leg)

    assert leg.distance_km > 50  # prawie 60 km w linii prostej (ok. 70 km koleją)
    assert priced.amount != pricing.LOCAL_BUS_FLAT_PLN
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * leg.distance_km, 2)
    assert priced.currency == "PLN"
    assert priced.price_type == "szacunek"
    assert priced.price_verified is False
    assert priced.breakdown["price_verified"] is False
    assert priced.breakdown["tryb_motis"] == "SUBURBAN"
    assert "wartosc_zastepcza" not in priced.breakdown  # to nie autobusowy placeholder
    assert priced.unverified_label == "cena niepotwierdzona"
    assert "cena niepotwierdzona" in priced.notes
    assert "bez ryczałtu autobusowego" in priced.notes
    assert priced.carrier is None  # żaden moduł taryf nie wycenił tego odcinka


def test_skm_trojmiasto_tez_niepotwierdzony_nie_ryczalt():
    leg = _suburban("Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA, carrier="SKM")
    priced = pricing.price_bus_leg(leg)
    assert priced.amount != pricing.LOCAL_BUS_FLAT_PLN
    assert priced.price_verified is False


def test_pozostale_tryby_lokalne_nadal_maja_ryczalt_bus_jako_wartosc_zastepcza():
    # Krótki odcinek (poniżej LOCAL_BUS_MAX_KM); długie idą na szacunek PLN/km
    # (tests/test_long_local_leg_pricing.py).
    leg = _suburban(
        "Szczecin Główny", "Szczecin Gumieńce", SZCZECIN_GLOWNY, (53.4150, 14.4900), carrier="X"
    )
    leg.extra["motis_mode"] = "BUS"
    assert leg.distance_km < pricing.LOCAL_BUS_MAX_KM
    priced = pricing.price_bus_leg(leg)
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
    assert priced.breakdown["wartosc_zastepcza"] is True


def test_s_bahn_berlin_w_kole_bvg_nadal_bilet_bvg():
    leg = _suburban(
        "S+U Alexanderplatz",
        "S Ostkreuz",
        BERLIN_ALEXANDERPLATZ,
        BERLIN_OSTKREUZ,
        carrier="S-Bahn Berlin GmbH",
        minutes=25,  # > 15 min, więc nie Kurzstrecke
    )
    priced = pricing.price_bus_leg(leg)
    assert priced.carrier is Carrier.BVG_BERLIN
    assert (priced.amount, priced.currency, priced.price_type) == (4.00, "EUR", "oficjalna_taryfa")
    assert priced.price_verified is True
    assert priced.breakdown["strefa"] == "AB"


def test_s_bahn_berlin_poza_kolem_bvg_nie_jest_zgadywany():
    # Potsdam leży poza kołem 20 km i poza strefami AB/ABC z naszego cennika.
    leg = _suburban(
        "S+U Alexanderplatz", "Potsdam Hbf", BERLIN_ALEXANDERPLATZ, POTSDAM_HBF, carrier="S-Bahn"
    )
    priced = pricing.price_bus_leg(leg)
    if priced.carrier is None:
        assert priced.price_verified is False
        assert priced.amount != pricing.LOCAL_BUS_FLAT_PLN
    else:  # gdyby koło BVG kiedyś objęło Potsdam, wynik ma być z cennika
        assert priced.carrier is Carrier.BVG_BERLIN


def test_s_bahn_w_nrw_nadal_eezy_nrw():
    leg = _suburban(
        "Düsseldorf Hbf", "Duisburg Hbf", DUSSELDORF_HBF, DUISBURG_HBF, carrier="S-Bahn Rhein-Ruhr"
    )
    priced = pricing.price_bus_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.VRR
    assert priced.price_verified is True


def test_s_bahn_poza_znanymi_taryfami_w_de_niepotwierdzony():
    leg = _suburban(
        "Hannover Hbf", "Hannover Flughafen", HANNOVER_HBF, HANNOVER_FLUGHAFEN, carrier="S-Bahn"
    )
    priced = pricing.price_bus_leg(leg)
    assert priced.amount != pricing.LOCAL_BUS_FLAT_PLN
    assert priced.price_verified is False
    assert priced.breakdown["tryb_motis"] == "SUBURBAN"


def test_price_leg_kieruje_suburban_przez_ta_sama_sciezke():
    leg = _suburban(
        "Szczecin Główny", "Angermünde", SZCZECIN_GLOWNY, ANGERMUENDE, carrier="SKM", minutes=60
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.breakdown["tryb_motis"] == "SUBURBAN"
    assert priced.price_verified is False


def _confirmed(amount):
    depart = datetime(2026, 10, 20, 8, 0)
    leg = Leg(
        mode=LegMode.RAIL,
        origin_name="Szczecin Główny",
        destination_name="Berlin Hbf",
        depart=depart,
        arrive=depart + timedelta(minutes=120),
        carrier_name="PKP Intercity",
        distance_km=125.0,
    )
    return PricedLeg(leg=leg, amount=amount, currency="PLN", price_type="oficjalna_taryfa")


def test_ranking_najtansza_nie_preferuje_skm_o_niepotwierdzonej_cenie():
    skm = pricing.price_bus_leg(
        _suburban(
            "Szczecin Główny", "Angermünde", SZCZECIN_GLOWNY, ANGERMUENDE, carrier="SKM", minutes=60
        )
    )
    # Wariant z SKM jest NOMINALNIE tańszy (kilkanaście PLN) niż potwierdzony bilet.
    z_skm = scoring.build_itinerary("SKM + RE", [skm])
    potwierdzony = scoring.build_itinerary("IC", [_confirmed(skm.amount + 30.0)])
    assert z_skm.total_price_pln < potwierdzony.total_price_pln
    assert not z_skm.price_verified and potwierdzony.price_verified

    recs = scoring.pick_recommendations([z_skm, potwierdzony])

    assert recs["najtansza"] is potwierdzony
    assert recs["najtansza_bezpieczna"] is potwierdzony
    note = scoring.price_ranking_note("najtansza", potwierdzony, [z_skm, potwierdzony])
    assert "Pominięto 1 wariant(y)" in note and "SKM + RE" in note
