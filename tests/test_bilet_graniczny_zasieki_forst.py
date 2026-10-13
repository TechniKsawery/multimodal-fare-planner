"""Bilet graniczny Polska-Niemcy Zasieki - Forst: 5,00 zł, bez ulg ustawowych, dzieci < 6 lat gratis."""

import json
from datetime import datetime, timedelta

import pytest

from fares import bilet_graniczny_zasieki_forst as bg
from fares import estimate_price
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing
from routing.model import Leg, LegMode

ZASIEKI = (51.6130, 14.7190)
FORST = (51.7370, 14.6350)
WROCLAW_GLOWNY = (51.0987, 17.0366)


def _leg(origin, destination, origin_xy, destination_xy, *, carrier, mode=LegMode.RAIL, extra=None):
    extra = dict(extra or {})
    extra.update(
        origin_lat=origin_xy[0],
        origin_lon=origin_xy[1],
        destination_lat=destination_xy[0],
        destination_lon=destination_xy[1],
    )
    depart = datetime(2026, 10, 20, 8, 0)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=20),
        carrier_name=carrier,
        distance_km=motis_client.haversine_km(*origin_xy, *destination_xy),
        extra=extra,
    )


def _seg(**discounts):
    return Segment(
        Carrier.BILET_GRANICZNY_ZASIEKI_FORST,
        "Zasieki",
        "Forst (Lausitz)",
        discounts=DiscountProfile(**discounts),
    )


def test_cena_stala_5_zl_oficjalna():
    r = estimate_price(_seg())
    assert (r.amount, r.currency) == (5.0, "PLN")
    assert r.price_type is PriceType.OFFICIAL
    assert r.breakdown["price_verified"] is True
    assert r.breakdown["kierunek"] == "w jedną stronę"
    assert r.breakdown["data_odczytu"] == "2026-10-13"
    assert r.breakdown["obowiazuje_od"] == "2024-10-01"


def test_url_regulaminu_oznaczony_do_uzupelnienia():
    r = estimate_price(_seg())
    assert r.breakdown["zrodlo_url"] is None
    assert r.breakdown["zrodlo_url_do_uzupelnienia"] is True


@pytest.mark.parametrize("age", [None, 6, 7, 15, 20, 26, 40, 70])
def test_uczniowie_studenci_i_dorosli_placa_pelna_cene(age):
    assert estimate_price(_seg(age=age)).amount == 5.0


@pytest.mark.parametrize("flag", ["ztm_lublin_ulgowy", "mpk_wroclaw_ulgowy", "bahncard"])
def test_ulgi_innych_taryf_nie_obnizaja_ceny(flag):
    value = "50" if flag == "bahncard" else True
    assert estimate_price(_seg(pkp_ulga_kod="studenci", **{flag: value})).amount == 5.0


@pytest.mark.parametrize("age", [0, 1, 5])
def test_dzieci_ponizej_6_lat_gratis(age):
    r = estimate_price(_seg(age=age))
    assert (r.amount, r.currency, r.price_type) == (0.0, "PLN", PriceType.OFFICIAL)
    assert "bezpłatnie" in r.notes


def test_json_zgodny_z_regulaminem():
    from fares._data_loading import DATA_DIR

    data = json.loads((DATA_DIR / "bilet_graniczny_zasieki_forst.json").read_text("utf-8"))
    assert (data["cena"], data["waluta"], data["kierunek"]) == (5.0, "PLN", "w jedną stronę")
    assert data["dzieci_gratis_wiek_ponizej"] == 6
    assert data["obowiazuje_od"] == "2024-10-01"
    assert data["weryfikacja"]["data_odczytu"] == "2026-10-13"
    assert data["weryfikacja"]["url"] is None and data["weryfikacja"]["url_do_uzupelnienia"]


def test_zly_przewoznik_rzuca_blad():
    with pytest.raises(ValueError):
        bg.estimate(Segment(Carrier.ZVON_GORLITZ, "Zasieki", "Forst"))


@pytest.mark.parametrize(
    "a, b, axy, bxy, carrier",
    [
        ("Zasieki", "Forst (Lausitz)", ZASIEKI, FORST, "DB Regio"),
        ("Forst (Lausitz)", "Zasieki", FORST, ZASIEKI, "DB Regio AG Südost"),
        ("Zasieki", "Forst (Lausitz)", ZASIEKI, FORST, "Koleje Dolnośląskie"),
        ("Zasieki Gr.", "Forst Lausitz", ZASIEKI, FORST, "Koleje Dolnośląskie"),
    ],
)
def test_odcinek_zasieki_forst_wyceniony_na_5_zl(a, b, axy, bxy, carrier):
    priced = pricing.price_rail_leg(_leg(a, b, axy, bxy, carrier=carrier), DiscountProfile())
    assert priced.carrier is Carrier.BILET_GRANICZNY_ZASIEKI_FORST
    assert (priced.amount, priced.currency) == (5.0, "PLN")
    assert priced.price_type == "oficjalna_taryfa"
    assert priced.breakdown["price_verified"] is True


def test_student_i_dziecko_przez_price_rail_leg():
    leg = _leg("Zasieki", "Forst (Lausitz)", ZASIEKI, FORST, carrier="DB Regio")
    student = pricing.price_rail_leg(leg, DiscountProfile(age=22, pkp_ulga_kod="studenci"))
    dziecko = pricing.price_rail_leg(leg, DiscountProfile(age=4))
    assert student.amount == 5.0
    assert dziecko.amount == 0.0


def test_autobus_zastepczy_nie_dostaje_biletu_granicznego():
    leg = _leg(
        "Zasieki",
        "Forst (Lausitz)",
        ZASIEKI,
        FORST,
        carrier="DB Regio",
        extra={"motis_mode": "BUS"},
    )
    assert pricing.is_bilet_graniczny_zasieki_forst(leg) is False


def test_tryb_bus_nie_dostaje_biletu_granicznego():
    leg = _leg("Zasieki", "Forst (Lausitz)", ZASIEKI, FORST, carrier="DB Regio", mode=LegMode.BUS)
    assert pricing.is_bilet_graniczny_zasieki_forst(leg) is False


def test_inny_przewoznik_dluzszy_i_czastkowy_odcinek_nie_pasuja():
    inny = _leg("Zasieki", "Forst (Lausitz)", ZASIEKI, FORST, carrier="Polregio")
    dlugi = _leg(
        "Wrocław Główny", "Forst (Lausitz)", WROCLAW_GLOWNY, FORST, carrier="Koleje Dolnośląskie"
    )
    czastkowy = _leg(
        "Zasieki", "Zasieki Gr.", ZASIEKI, (51.6128, 14.7160), carrier="Koleje Dolnośląskie"
    )
    for leg in (inny, dlugi, czastkowy):
        assert pricing.is_bilet_graniczny_zasieki_forst(leg) is False
        priced = pricing.price_rail_leg(leg, DiscountProfile())
        assert priced.carrier is not Carrier.BILET_GRANICZNY_ZASIEKI_FORST


def test_pociag_zgorzelec_gorlitz_nadal_0_zl():
    leg = _leg(
        "Zgorzelec",
        "Görlitz",
        (51.15, 15.02),
        (51.1468, 14.9757),
        carrier="Koleje Dolnośląskie",
    )
    assert pricing.is_bilet_graniczny_zasieki_forst(leg) is False
    assert pricing.price_rail_leg(leg, DiscountProfile()).amount == 0.0
