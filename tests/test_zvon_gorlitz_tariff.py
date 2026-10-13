"""EuropastadtTarif ZVON (Görlitz–Zgorzelec): Einzelfahrt 2,00 / 1,50 EUR (zvon.de, 2026-10-13)."""

from datetime import datetime

import pytest

from common.currency import PLACEHOLDER_RATES_TO_PLN, to_pln
from fares import estimate_price
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import pricing
from routing.model import Leg, LegMode

ZVON = "ZVON Oberlausitz-Niederschlesien"
GORLITZ = (51.1528, 14.9872)
ZGORZELEC = (51.1500, 15.0100)


def _leg(carrier=ZVON, o=GORLITZ, d=ZGORZELEC, with_coords=True):
    extra = (
        {"origin_lat": o[0], "origin_lon": o[1], "destination_lat": d[0], "destination_lon": d[1]}
        if with_coords
        else {}
    )
    return Leg(
        mode=LegMode.BUS,
        origin_name="Görlitz Postplatz",
        destination_name="Zgorzelec Dworzec",
        depart=datetime(2026, 10, 14, 9, 0),
        arrive=datetime(2026, 10, 14, 9, 10),
        carrier_name=carrier,
        distance_km=2.0,
        requires_walk=False,
        extra=extra,
    )


def _seg(age=None):
    return Segment(Carrier.ZVON_GORLITZ, "A", "B", discounts=DiscountProfile(age=age))


def test_cena_normalna_2_eur_oficjalna_i_zweryfikowana():
    r = estimate_price(_seg())
    assert r.amount == 2.00 and r.currency == "EUR"
    assert r.price_type is PriceType.OFFICIAL
    assert r.breakdown["price_verified"] is True
    assert "zvon.de" in r.breakdown["zrodlo"] and r.breakdown["data_weryfikacji"] == "2026-10-13"


@pytest.mark.parametrize(
    "age,expected", [(0, 1.50), (14, 1.50), (15, 2.00), (16, 2.00), (20, 2.00)]
)
def test_granica_wieku_ulga_tylko_do_15_urodzin(age, expected):
    # "Nur Schüler bis zum 15. Geburtstag": 14-latek ulgowy, 15-latek (po urodzinach) normalny.
    assert estimate_price(_seg(age)).amount == expected


def test_brak_wieku_to_cena_normalna():
    assert estimate_price(_seg(None)).amount == 2.00


def test_student_nie_dostaje_ulgi():
    # Student to osoba pełnoletnia; inne flagi ulg (np. ulgowy PKP) nie wpływają na ZVON.
    profil = DiscountProfile(age=21, pkp_ulga_kod="student", mpk_wroclaw_ulgowy=True)
    r = estimate_price(Segment(Carrier.ZVON_GORLITZ, "A", "B", discounts=profil))
    assert r.amount == 2.00


def test_kurs_eur_pln_z_projektu():
    assert PLACEHOLDER_RATES_TO_PLN["EUR"] == 4.3775
    assert to_pln(2.00, "EUR") == pytest.approx(8.755)
    assert to_pln(1.50, "EUR") == pytest.approx(6.56625)


def test_odcinek_zvon_w_obszarze_wyceniany_taryfa_europastadt():
    priced = pricing.price_bus_leg(_leg(), DiscountProfile())
    assert priced.carrier is Carrier.ZVON_GORLITZ
    assert priced.amount == 2.00 and priced.currency == "EUR"
    assert priced.price_verified
    assert not priced.breakdown.get("wartosc_zastepcza")
    assert pricing.price_bus_leg(_leg(), DiscountProfile(age=12)).amount == 1.50


def test_inny_operator_w_obszarze_nie_dostaje_taryfy_zvon():
    # np. autobus zastępczy trilex/DLB: cena niepotwierdzona, zostaje szacunkiem
    priced = pricing.price_bus_leg(_leg(carrier="trilex Ersatzverkehr"), DiscountProfile())
    assert priced.carrier is not Carrier.ZVON_GORLITZ
    assert not priced.price_verified


def test_zvon_poza_obszarem_lub_bez_wspolrzednych_nie_dostaje_taryfy():
    daleko = _leg(d=(51.5, 14.0))
    assert pricing.price_bus_leg(daleko, DiscountProfile()).carrier is not Carrier.ZVON_GORLITZ
    brak = _leg(with_coords=False)
    assert pricing.price_bus_leg(brak, DiscountProfile()).carrier is not Carrier.ZVON_GORLITZ
