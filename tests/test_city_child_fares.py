"""Testy reguł wiekowych dla dzieci w 5 miastach/przewoźnikach:
ZTM Warszawa, MPK Kraków, ZTM Poznań, BVG Berlin i VRR (NRW).

Wszystkie reguły i progi wiekowe zostały zweryfikowane na oficjalnych stronach przewoźników
z datą 2026-10-15 (co najmniej dwa niezależne źródła per ulga).
"""

import pytest

from fares import estimate_price
from fares._data_loading import load
from fares.model import Carrier, DiscountProfile, PriceType, Segment


# ==============================================================================
# 1. ZTM WARSZAWA
# ==============================================================================


def _cena_waw(minuty=15, travel_date=None, **discounts):
    seg = Segment(
        Carrier.ZTM_WARSZAWA,
        "Centrum",
        "Politechnika",
        ride_duration_min=minuty,
        travel_date=travel_date,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


def test_ztm_warszawa_zrodla_danych():
    tabela = load("ztm_warszawa.json")
    bezplatne = tabela["dzieci_bezplatne"]
    ulgowe = tabela["dzieci_ulgowe"]
    assert bezplatne["data_weryfikacji"] == "2026-10-15"
    assert bezplatne["zrodlo_url"].startswith("https://")
    assert bezplatne["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci od urodzenia do 30 września w roku kalendarzowym, w którym kończą 7 lat" in bezplatne["cytat"]

    assert ulgowe["data_weryfikacji"] == "2026-10-15"
    assert ulgowe["zrodlo_url"].startswith("https://")
    assert ulgowe["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci i młodzież od 1 października roku kalendarzowego, w którym kończą 7 lat do ukończenia 16 roku życia" in ulgowe["cytat"]


def test_ztm_warszawa_dziecko_ponizej_6_lat_bezplatnie():
    for wiek in (0, 3, 5):
        res = _cena_waw(age=wiek)
        assert res.amount == 0.0
        assert res.price_type is PriceType.OFFICIAL
        assert res.breakdown["typ_biletu"] == "bezpłatny (100%)"


def test_ztm_warszawa_wiek_5_6_7_8_przed_i_po_30_wrzesnia_i_bez_daty():
    # Wiek 5 lat (poniżej 6 lat): bezpłatny pewny (OFFICIAL) w każdym przypadku
    res_5_przed = _cena_waw(travel_date="2026-09-15", age=5)
    assert res_5_przed.amount == 0.0
    assert res_5_przed.price_type is PriceType.OFFICIAL

    res_5_po = _cena_waw(travel_date="2026-10-15", age=5)
    assert res_5_po.amount == 0.0
    assert res_5_po.price_type is PriceType.OFFICIAL

    res_5_bez_daty = _cena_waw(age=5)
    assert res_5_bez_daty.amount == 0.0
    assert res_5_bez_daty.price_type is PriceType.OFFICIAL

    # Wiek 6 lat: przybliżenie (ESTIMATE) bez względu na datę podróży
    res_6_przed = _cena_waw(travel_date="2026-09-15", age=6)
    assert res_6_przed.amount == 0.0
    assert res_6_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_przed.notes

    res_6_po = _cena_waw(travel_date="2026-10-15", age=6)
    assert res_6_po.amount == 1.70  # ulgowy jako szacunek
    assert res_6_po.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_po.notes

    res_6_bez_daty = _cena_waw(age=6)
    assert res_6_bez_daty.amount == 1.70
    assert res_6_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_bez_daty.notes

    # Wiek 7 lat:
    # - do 30 września: niepewny (dziecko mogło skończyć 7 lat w roku podróży) -> szacunek 0.0 zł
    res_7_przed = _cena_waw(travel_date="2026-09-15", age=7)
    assert res_7_przed.amount == 0.0
    assert res_7_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_przed.notes

    # - po 30 września: pewny bilet ulgowy 50% (OFFICIAL)
    res_7_po = _cena_waw(travel_date="2026-10-15", age=7)
    assert res_7_po.amount == 1.70
    assert res_7_po.price_type is PriceType.OFFICIAL

    # - bez daty podróży: niepewny -> szacunek ulgowy
    res_7_bez_daty = _cena_waw(age=7)
    assert res_7_bez_daty.amount == 1.70
    assert res_7_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_bez_daty.notes

    # Wiek 8 lat: pewny bilet ulgowy 50% (OFFICIAL) przed, po i bez daty
    res_8_przed = _cena_waw(travel_date="2026-09-15", age=8)
    assert res_8_przed.amount == 1.70
    assert res_8_przed.price_type is PriceType.OFFICIAL

    res_8_po = _cena_waw(travel_date="2026-10-15", age=8)
    assert res_8_po.amount == 1.70
    assert res_8_po.price_type is PriceType.OFFICIAL

    res_8_bez_daty = _cena_waw(age=8)
    assert res_8_bez_daty.amount == 1.70
    assert res_8_bez_daty.price_type is PriceType.OFFICIAL


def test_ztm_warszawa_prog_wieku_16_lat():
    # Wiek 7-15 lat: ulga 50% z samego wieku
    for wiek in (7, 10, 15):
        res = _cena_waw(age=wiek)
        assert res.amount == 1.70
        assert res.breakdown["typ_biletu"] == "ulgowy (50%)"

    # Wiek 16 lat (tuż powyżej progu): bilet normalny (ulga wymaga legitymacji szkolnej)
    res_16 = _cena_waw(age=16)
    assert res_16.amount == 3.40
    assert res_16.breakdown["typ_biletu"] == "normalny"

    # Wiek 16 lat z legitymacją szkolną (flaga ulgowy): ulga 50%
    res_16_legit = _cena_waw(age=16, ztm_warszawa_ulgowy=True)
    assert res_16_legit.amount == 1.70

    # Karta Ucznia podstawówki (flaga bezpłatny): przejazd bezpłatny
    res_16_bezplatny = _cena_waw(age=16, ztm_warszawa_bezplatny=True)
    assert res_16_bezplatny.amount == 0.0


# ==============================================================================
# 2. MPK KRAKÓW
# ==============================================================================


def _cena_krk(minuty=10, travel_date=None, **discounts):
    seg = Segment(
        Carrier.MPK_KRAKOW,
        "Dworzec Główny",
        "Wawel",
        ride_duration_min=minuty,
        travel_date=travel_date,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


def test_mpk_krakow_zrodla_danych():
    tabela = load("mpk_krakow.json")
    bezplatne = tabela["dzieci_bezplatne"]
    ulgowe = tabela["dzieci_ulgowe"]
    assert bezplatne["data_weryfikacji"] == "2026-10-15"
    assert bezplatne["zrodlo_url"].startswith("https://")
    assert bezplatne["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci od urodzenia do dnia 30 września roku, w którym kończą 7 rok życia" in bezplatne["cytat"]

    assert ulgowe["data_weryfikacji"] == "2026-10-15"
    assert ulgowe["zrodlo_url"].startswith("https://")
    assert ulgowe["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci i młodzież od 1 października roku kalendarzowego, w którym kończą 7 lat do ukończenia 16 roku życia" in ulgowe["cytat"]


def test_mpk_krakow_dziecko_ponizej_6_lat_bezplatnie():
    for wiek in (0, 3, 5):
        res = _cena_krk(age=wiek)
        assert res.amount == 0.0
        assert res.price_type is PriceType.OFFICIAL
        assert res.breakdown["typ_biletu"] == "bezpłatny (100%)"


def test_mpk_krakow_wiek_5_6_7_8_przed_i_po_30_wrzesnia_i_bez_daty():
    # Wiek 5 lat (poniżej 6 lat): bezpłatny pewny (OFFICIAL) w każdym przypadku
    res_5_przed = _cena_krk(travel_date="2026-09-15", age=5)
    assert res_5_przed.amount == 0.0
    assert res_5_przed.price_type is PriceType.OFFICIAL

    res_5_po = _cena_krk(travel_date="2026-10-15", age=5)
    assert res_5_po.amount == 0.0
    assert res_5_po.price_type is PriceType.OFFICIAL

    res_5_bez_daty = _cena_krk(age=5)
    assert res_5_bez_daty.amount == 0.0
    assert res_5_bez_daty.price_type is PriceType.OFFICIAL

    # Wiek 6 lat: przybliżenie (ESTIMATE) bez względu na datę podróży
    res_6_przed = _cena_krk(travel_date="2026-09-15", age=6)
    assert res_6_przed.amount == 0.0
    assert res_6_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_przed.notes

    res_6_po = _cena_krk(travel_date="2026-10-15", age=6)
    assert res_6_po.amount == 2.00  # ulgowy jako szacunek
    assert res_6_po.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_po.notes

    res_6_bez_daty = _cena_krk(age=6)
    assert res_6_bez_daty.amount == 2.00
    assert res_6_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_bez_daty.notes

    # Wiek 7 lat:
    # - do 30 września: niepewny (dziecko mogło skończyć 7 lat w roku podróży) -> szacunek 0.0 zł
    res_7_przed = _cena_krk(travel_date="2026-09-15", age=7)
    assert res_7_przed.amount == 0.0
    assert res_7_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_przed.notes

    # - po 30 września: pewny bilet ulgowy 50% (OFFICIAL)
    res_7_po = _cena_krk(travel_date="2026-10-15", age=7)
    assert res_7_po.amount == 2.00
    assert res_7_po.price_type is PriceType.OFFICIAL

    # - bez daty podróży: niepewny -> szacunek ulgowy
    res_7_bez_daty = _cena_krk(age=7)
    assert res_7_bez_daty.amount == 2.00
    assert res_7_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_bez_daty.notes

    # Wiek 8 lat: pewny bilet ulgowy 50% (OFFICIAL) przed, po i bez daty
    res_8_przed = _cena_krk(travel_date="2026-09-15", age=8)
    assert res_8_przed.amount == 2.00
    assert res_8_przed.price_type is PriceType.OFFICIAL

    res_8_po = _cena_krk(travel_date="2026-10-15", age=8)
    assert res_8_po.amount == 2.00
    assert res_8_po.price_type is PriceType.OFFICIAL

    res_8_bez_daty = _cena_krk(age=8)
    assert res_8_bez_daty.amount == 2.00
    assert res_8_bez_daty.price_type is PriceType.OFFICIAL


def test_mpk_krakow_prog_wieku_16_lat():
    # Wiek 7-15 lat: ulga 50% z samego wieku
    for wiek in (7, 10, 15):
        res = _cena_krk(age=wiek)
        assert res.amount == 2.00
        assert res.breakdown["typ_biletu"] == "ulgowy (50%)"

    # Wiek 16 lat (tuż powyżej progu): bilet normalny
    res_16 = _cena_krk(age=16)
    assert res_16.amount == 4.00
    assert res_16.breakdown["typ_biletu"] == "normalny"

    # Wiek 16 lat z legitymacją szkolną (flaga ulgowy): ulga 50%
    res_16_legit = _cena_krk(age=16, mpk_krakow_ulgowy=True)
    assert res_16_legit.amount == 2.00

    # Uczeń podstawówki w Metropolii Krakowskiej (flaga bezpłatny): przejazd bezpłatny
    res_16_bezplatny = _cena_krk(age=16, mpk_krakow_bezplatny=True)
    assert res_16_bezplatny.amount == 0.0


# ==============================================================================
# 3. ZTM POZNAŃ
# ==============================================================================


def _cena_poz(minuty=10, travel_date=None, **discounts):
    seg = Segment(
        Carrier.ZTM_POZNAN,
        "Most Teatralny",
        "Rondo Kaponiera",
        ride_duration_min=minuty,
        travel_date=travel_date,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


def test_ztm_poznan_zrodla_danych():
    tabela = load("ztm_poznan.json")
    bezplatne = tabela["dzieci_bezplatne"]
    ulgowe = tabela["dzieci_ulgowe"]
    assert bezplatne["data_weryfikacji"] == "2026-10-15"
    assert bezplatne["zrodlo_url"].startswith("https://")
    assert bezplatne["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci do 30 września roku, w którym kończą 7. rok życia" in bezplatne["cytat"]

    assert ulgowe["data_weryfikacji"] == "2026-10-15"
    assert ulgowe["zrodlo_url"].startswith("https://")
    assert ulgowe["drugie_zrodlo_url"].startswith("https://")
    assert "Dzieci i młodzież od dnia 1 października roku, w którym kończą 7. rok życia, do ukończenia 18. roku życia" in ulgowe["cytat"]


def test_ztm_poznan_dziecko_ponizej_6_lat_bezplatnie():
    for wiek in (0, 3, 5):
        res = _cena_poz(age=wiek)
        assert res.amount == 0.0
        assert res.price_type is PriceType.OFFICIAL
        assert res.breakdown["typ_biletu"] == "bezpłatny (100%)"


def test_ztm_poznan_wiek_5_6_7_8_przed_i_po_30_wrzesnia_i_bez_daty():
    # Wiek 5 lat (poniżej 6 lat): bezpłatny pewny (OFFICIAL) w każdym przypadku
    res_5_przed = _cena_poz(travel_date="2026-09-15", age=5)
    assert res_5_przed.amount == 0.0
    assert res_5_przed.price_type is PriceType.OFFICIAL

    res_5_po = _cena_poz(travel_date="2026-10-15", age=5)
    assert res_5_po.amount == 0.0
    assert res_5_po.price_type is PriceType.OFFICIAL

    res_5_bez_daty = _cena_poz(age=5)
    assert res_5_bez_daty.amount == 0.0
    assert res_5_bez_daty.price_type is PriceType.OFFICIAL

    # Wiek 6 lat: przybliżenie (ESTIMATE) bez względu na datę podróży
    res_6_przed = _cena_poz(travel_date="2026-09-15", age=6)
    assert res_6_przed.amount == 0.0
    assert res_6_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_przed.notes

    res_6_po = _cena_poz(travel_date="2026-10-15", age=6)
    assert res_6_po.amount == 2.50  # ulgowy jako szacunek
    assert res_6_po.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_po.notes

    res_6_bez_daty = _cena_poz(age=6)
    assert res_6_bez_daty.amount == 2.50
    assert res_6_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_6_bez_daty.notes

    # Wiek 7 lat:
    # - do 30 września: niepewny (dziecko mogło skończyć 7 lat w roku podróży) -> szacunek 0.0 zł
    res_7_przed = _cena_poz(travel_date="2026-09-15", age=7)
    assert res_7_przed.amount == 0.0
    assert res_7_przed.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_przed.notes

    # - po 30 września: pewny bilet ulgowy 50% (OFFICIAL)
    res_7_po = _cena_poz(travel_date="2026-10-15", age=7)
    assert res_7_po.amount == 2.50
    assert res_7_po.price_type is PriceType.OFFICIAL

    # - bez daty podróży: niepewny -> szacunek ulgowy
    res_7_bez_daty = _cena_poz(age=7)
    assert res_7_bez_daty.amount == 2.50
    assert res_7_bez_daty.price_type is PriceType.ESTIMATE
    assert "daty urodzenia" in res_7_bez_daty.notes

    # Wiek 8 lat: pewny bilet ulgowy 50% (OFFICIAL) przed, po i bez daty
    res_8_przed = _cena_poz(travel_date="2026-09-15", age=8)
    assert res_8_przed.amount == 2.50
    assert res_8_przed.price_type is PriceType.OFFICIAL

    res_8_po = _cena_poz(travel_date="2026-10-15", age=8)
    assert res_8_po.amount == 2.50
    assert res_8_po.price_type is PriceType.OFFICIAL

    res_8_bez_daty = _cena_poz(age=8)
    assert res_8_bez_daty.amount == 2.50
    assert res_8_bez_daty.price_type is PriceType.OFFICIAL


def test_ztm_poznan_prog_wieku_18_lat():
    # Wiek 7-17 lat: ulga 50% z samego wieku
    for wiek in (7, 12, 17):
        res = _cena_poz(age=wiek)
        assert res.amount == 2.50
        assert res.breakdown["typ_biletu"] == "ulgowy (50%)"

    # Wiek 18 lat (tuż powyżej progu 18 lat): bilet normalny
    res_18 = _cena_poz(age=18)
    assert res_18.amount == 5.00
    assert res_18.breakdown["typ_biletu"] == "normalny"

    # Wiek 18 lat z legitymacją szkolną (flaga ulgowy): ulga 50%
    res_18_legit = _cena_poz(age=18, ztm_poznan_ulgowy=True)
    assert res_18_legit.amount == 2.50


# ==============================================================================
# 4. BVG BERLIN
# ==============================================================================


def _cena_bvg(minuty=10, strefa="Kurzstrecke", **discounts):
    seg = Segment(
        Carrier.BVG_BERLIN,
        "Alexanderplatz",
        "Hackescher Markt",
        ride_duration_min=minuty,
        tariff_zone=strefa,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


def test_bvg_berlin_zrodla_danych():
    tabela = load("bvg_berlin.json")
    bezplatne = tabela["dzieci_ponizej_6_lat_bezplatnie"]
    ulgowe = tabela["wiek_ulgowy"]
    assert bezplatne["data_weryfikacji"] == "2026-10-15"
    assert bezplatne["zrodlo_url"].startswith("https://")
    assert bezplatne["drugie_zrodlo_url"].startswith("https://")
    assert "Kinder unter sechs Jahren können generell unentgeltlich mitgenommen werden" in bezplatne["cytat"]

    assert ulgowe["data_weryfikacji"] == "2026-10-15"
    assert ulgowe["zrodlo_url"].startswith("https://")
    assert ulgowe["drugie_zrodlo_url"].startswith("https://")
    assert "Ermäßigungstarif: für Kinder von 6 bis 14 Jahren" in ulgowe["cytat"]
    assert ulgowe["zakres_wieku"] == [6, 14]


def test_bvg_berlin_dziecko_ponizej_6_lat_bezplatnie():
    for wiek in (0, 4, 5):
        res = _cena_bvg(age=wiek)
        assert res.amount == 0.0
        assert res.price_type is PriceType.OFFICIAL
        assert res.currency == "EUR"
        assert res.breakdown["typ_biletu"].startswith("bezpłatny")


def test_bvg_berlin_prog_wieku_6_i_14_lat():
    # Wiek 5 lat: tuż poniżej progu -> bezpłatny
    assert _cena_bvg(age=5).amount == 0.0

    # Wiek 6 lat: tuż na progu -> taryfa ulgowa (Ermäßigungstarif)
    res_6 = _cena_bvg(age=6)
    assert res_6.amount == 2.10  # Kurzstrecke ulgowy
    assert res_6.breakdown["typ_biletu"] == "ulgowy (Ermäßigungstarif)"

    # Wiek 14 lat: tuż na górnym progu -> taryfa ulgowa
    res_14 = _cena_bvg(age=14)
    assert res_14.amount == 2.10
    assert res_14.breakdown["typ_biletu"] == "ulgowy (Ermäßigungstarif)"

    # Wiek 15 lat: tuż powyżej progu 14 lat -> taryfa normalna
    res_15 = _cena_bvg(age=15)
    assert res_15.amount == 2.80  # Kurzstrecke normalny
    assert res_15.breakdown["typ_biletu"] == "normalny"

    # Wiek 15 lat z flagą ulgowy -> bilet ulgowy
    assert _cena_bvg(age=15, bvg_berlin_ulgowy=True).amount == 2.10

    # Schwerbehindertenausweis ma pierwszeństwo
    assert _cena_bvg(age=15, bvg_berlin_schwerbehindert=True).amount == 0.0


# ==============================================================================
# 5. VRR (NRW / eezy.nrw)
# ==============================================================================


def _cena_vrr(km=10.0, **discounts):
    seg = Segment(
        Carrier.VRR,
        "Düsseldorf Hbf",
        "Neuss Hbf",
        distance_km=km,
        discounts=DiscountProfile(**discounts),
    )
    return estimate_price(seg)


def test_vrr_zrodla_danych():
    tabela = load("vrr_eezy.json")
    bezplatne = tabela["dzieci_ponizej_6_lat_bezplatnie"]
    ulgowe = tabela["wiek_ulgowy"]
    assert bezplatne["data_weryfikacji"] == "2026-10-15"
    assert bezplatne["zrodlo_url"].startswith("https://")
    assert bezplatne["drugie_zrodlo_url"].startswith("https://")
    assert "Kinder unter sechs Jahren benötigen im ÖPNV kein Ticket" in bezplatne["cytat"]

    assert ulgowe["data_weryfikacji"] == "2026-10-15"
    assert ulgowe["zrodlo_url"].startswith("https://")
    assert ulgowe["drugie_zrodlo_url"].startswith("https://")
    assert "Kindertarif" in ulgowe["cytat"]
    assert ulgowe["zakres_wieku"] == [6, 14]


def test_vrr_dziecko_ponizej_6_lat_bezplatnie():
    for wiek in (0, 4, 5):
        res = _cena_vrr(age=wiek)
        assert res.amount == 0.0
        assert res.price_type is PriceType.OFFICIAL
        assert res.currency == "EUR"
        assert res.breakdown["typ_biletu"].startswith("bezpłatny")


def test_vrr_prog_wieku_6_i_14_lat():
    # Dorosły: 1.73 + 0.29 * 10 = 4.63 EUR
    # Kindertarif (50% zniżki): round(4.63 * 0.5, 2) = 2.31 EUR
    dorosly = _cena_vrr()
    assert dorosly.amount == 4.63

    # Wiek 5 lat: tuż poniżej progu -> bezpłatny
    assert _cena_vrr(age=5).amount == 0.0

    # Wiek 6 lat: tuż na progu -> Kindertarif (50% rabatu)
    res_6 = _cena_vrr(age=6)
    assert res_6.amount == 2.31
    assert res_6.breakdown["kindertarif"] is True

    # Wiek 14 lat: tuż na górnym progu -> Kindertarif
    res_14 = _cena_vrr(age=14)
    assert res_14.amount == 2.31
    assert res_14.breakdown["kindertarif"] is True

    # Wiek 15 lat: tuż powyżej progu 14 lat -> taryfa normalna
    res_15 = _cena_vrr(age=15)
    assert res_15.amount == 4.63
    assert res_15.breakdown["kindertarif"] is False

    # Wiek 15 lat z flagą vrr_dziecko -> Kindertarif
    assert _cena_vrr(age=15, vrr_dziecko=True).amount == 2.31
