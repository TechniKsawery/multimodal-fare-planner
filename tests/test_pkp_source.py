"""Pasma TLK/IC PKP Intercity niosą adres źródła (cennik, tabela ulg); datę weryfikacji - dopiero gdy
ktoś ją wpisze do fares/data/pkp_intercity.json (dziś jej w repo nie ma, więc nie jest zgadywana).
Kwoty bez zmian."""

from datetime import UTC, datetime

import pytest

from fares import pkp
from fares.model import Carrier, DiscountProfile, Segment
from routing import pricing
from routing.model import Leg, LegMode
from ui_helpers import leg_source

CENNIK = "https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Cennik_uslug_przewozowych_PKP_Intercity_tekst_ujednolicony_obowiazuje_od_23.07.2026_r.pdf"
ULGI = "https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Ulgi%20ustawowe/Tabele_ulg_ustawowych_11-02-2026.pdf"


def _seg(km, ulga="brak"):
    return Segment(
        Carrier.PKP_INTERCITY,
        "A",
        "B",
        distance_km=km,
        discounts=DiscountProfile(pkp_ulga_kod=ulga),
    )


def _rail_leg(route, km):
    return Leg(
        mode=LegMode.RAIL,
        origin_name="Warszawa Wschodnia",
        destination_name="Gdańsk Główny",
        depart=datetime(2026, 10, 18, 8, tzinfo=UTC),
        arrive=datetime(2026, 10, 18, 11, tzinfo=UTC),
        carrier_name="PKP Intercity",
        distance_km=km,
        extra={"route_short_name": route},
    )


@pytest.mark.parametrize(("km", "kwota"), [(155, 46.0), (285, 67.0)])
def test_pasmo_ma_url_cennika_a_kwota_bez_zmian(km, kwota):
    r = pkp.estimate(_seg(km))
    assert r.amount == kwota
    assert r.breakdown["zrodlo_url"] == CENNIK
    assert "zrodlo_ulgi_url" not in r.breakdown


def test_ulga_dodaje_url_tabeli_ulg():
    r = pkp.estimate(_seg(155, "student_do_26_lat_doktorant_do_35_lat"))
    assert r.breakdown["zrodlo_url"] == CENNIK
    assert r.breakdown["zrodlo_ulgi_url"] == ULGI


def test_bez_daty_w_danych_nie_ma_daty_w_breakdown():
    r = pkp.estimate(_seg(155))
    assert "data_weryfikacji" not in r.breakdown
    assert leg_source(type("P", (), {"breakdown": r.breakdown})()) == (CENNIK, None)


def test_data_z_danych_trafia_do_breakdown(monkeypatch):
    monkeypatch.setitem(pkp._TABLE, "data_weryfikacji", "2026-10-13")
    r = pkp.estimate(_seg(155))
    assert r.breakdown["data_weryfikacji"] == "2026-10-13"


@pytest.mark.parametrize("route", ["IC", "TLK"])
def test_odcinek_tlk_ic_w_routingu_zachowuje_zrodlo(route):
    priced = pricing.price_rail_leg(_rail_leg(route, 285), DiscountProfile())
    assert (priced.amount, priced.price_type) == (67.0, "oficjalna_taryfa")
    assert priced.breakdown["zrodlo_url"] == CENNIK


@pytest.mark.parametrize("route", ["EIC", "EIP"])
def test_eic_eip_nie_dostaje_zrodla_cennika_tlk_ic(route):
    priced = pricing.price_rail_leg(_rail_leg(route, 285), DiscountProfile())
    assert priced.price_type == "szacunek"
    assert not {"zrodlo_url", "zrodlo_ulgi_url", "data_weryfikacji"} & set(priced.breakdown)
