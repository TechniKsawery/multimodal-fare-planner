"""Taryfa ZTM Lublin wg oficjalnej strony ZDiTM, zweryfikowanej 2026-10-14 (cennik od 16.02.2026)."""

import pytest

from fares import estimate_price
from fares._data_loading import load
from fares.model import Carrier, DiscountProfile, PriceType, Segment

TABLE = load("ztm_lublin.json")


def _cena(minuty, **discounts):
    seg = Segment(
        Carrier.ZTM_LUBLIN,
        "A",
        "B",
        ride_duration_min=minuty,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


@pytest.mark.parametrize(
    "minuty, normalny, ulgowy",
    [(10, 3.40, 1.70), (30, 4.60, 2.30), (80, 5.20, 2.60), (200, 9.00, 4.50), (1000, 14.20, 7.10)],
)
def test_ceny_biletow_czasowych(minuty, normalny, ulgowy):
    assert _cena(minuty).amount == normalny
    assert _cena(minuty, ztm_lublin_ulgowy=True).amount == ulgowy


def test_bilet_jednoprzejazdowy_w_danych():
    assert TABLE["bilet_jednoprzejazdowy"] == {"normalny": 5.00, "ulgowy": 2.50}


def test_zrodlo_data_i_price_verified():
    assert TABLE["source_url"] == "https://zdtm.lublin.eu/pl/ulgi-w-przejazdach/33.html"
    assert TABLE["verified_date"] == "2026-10-14"
    assert TABLE["obowiazuje_od"] == "2026-02-16"
    assert TABLE["price_verified"] is True
    result = _cena(10)
    assert result.price_type is PriceType.OFFICIAL
    assert result.breakdown["price_verified"] is True
    assert result.breakdown["data_weryfikacji"] == "2026-10-14"


@pytest.mark.parametrize("wiek", [66, 65, 0, 4, 5])
def test_wiek_daje_przejazd_bezplatny(wiek):
    assert _cena(10, age=wiek).amount == 0.0


def test_65_plus_a_nie_70_plus():
    assert _cena(10, age=64).amount == 3.40
    assert _cena(10, age=65).amount == 0.0


def test_dziecko_8_lat_zakladany_uczen_podstawowki_z_adnotacja():
    result = _cena(10, age=8)
    assert result.amount == 0.0
    assert "powod_bezplatny" in result.breakdown
    assert "założony z wieku" in result.breakdown["powod_bezplatny"]


def test_wiek_6_zalezy_od_daty_podrozy():
    def cena(data):
        seg = Segment(
            Carrier.ZTM_LUBLIN,
            "A",
            "B",
            ride_duration_min=10,
            discounts=DiscountProfile(age=6),
            travel_date=data,
        )
        return estimate_price(seg).amount

    assert cena("2026-09-30") == 0.0  # do 30.09 pewne
    assert cena("2026-10-13") == 3.40  # po 30.09 roku 7. urodzin nie wiadomo -> górna granica
    assert (
        estimate_price(
            Segment(
                Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=10, discounts=DiscountProfile(age=6)
            )
        ).amount
        == 3.40
    )


def test_dwudziestolatek_bez_flagi_placi_normalnie_student_polski_bez_ulgi():
    result = _cena(10, age=20)
    assert result.amount == 3.40
    assert result.breakdown["typ_biletu"] == "normalny"
    assert TABLE["ulgi_niepotwierdzone"]["studenci_polskich_uczelni"]["status"] == "niepotwierdzone"


def test_dwudziestolatek_z_flaga_ulgowy_placi_polowe():
    assert _cena(10, age=20, ztm_lublin_ulgowy=True).amount == 1.70


def test_flaga_bezplatny_dziala_bez_wieku():
    result = _cena(10, ztm_lublin_bezplatny=True)
    assert result.amount == 0.0
    assert "powod_bezplatny" not in result.breakdown
