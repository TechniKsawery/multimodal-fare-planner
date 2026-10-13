"""Lokalne taryfy kolejowe: SKM Trójmiasto (Taryfa Pomorska), SKM Warszawa (bilety czasowe ZTM),
ŁKA w Łodzi (Strefa A). Wszystkie kwoty i zasady honorowania pochodzą z raportów Gemini z
2026-10-12 (research/skm-km-tabele.md, research/ztm-lka-regio.md) i mają status "wg Gemini,
niezweryfikowane niezależnie" — domeny przewoźników są z chmury zablokowane.

Koleje Małopolskie i Koleje Mazowieckie mają osobne moduły i testy:
tests/test_koleje_malopolskie_tariff.py, tests/test_koleje_mazowieckie_tariff.py. WKD nie ma tabeli
i nie honoruje biletów ZTM: idzie zgrubnym szacunkiem PLN/km.

Współrzędne przybliżone (ok. 0,01°) — rozróżniają miejsca, nie są danymi cenowymi."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fares import lka_lodz, skm_trojmiasto
from fares._data_loading import load
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing
from routing.model import Leg, LegMode

STATUS = "wg Gemini, niezweryfikowane niezależnie"

GDANSK_GLOWNY = (54.3560, 18.6440)
GDYNIA_GLOWNA = (54.5200, 18.5300)
WEJHEROWO = (54.6050, 18.2400)
WARSZAWA_CENTRALNA = (52.2289, 21.0033)
WARSZAWA_WSCHODNIA = (52.2514, 21.0364)
WARSZAWA_ZACHODNIA = (52.2194, 20.9657)
WARSZAWA_PLUDY = (52.2937, 21.0620)
WARSZAWA_LOTNISKO = (52.1696, 20.9690)
PRUSZKOW = (52.1664, 20.8097)
LODZ_KALISKA = (51.7585, 19.4300)
LODZ_WIDZEW = (51.7600, 19.5340)
ZGIERZ = (51.8553, 19.4066)

# Normalne ceny 21 pasm: Taryfa Pomorska od 1.03.2026, Tabela nr 1 (raport Gemini).
SKM_PASMA = [
    (6, 7.00), (12, 8.00), (18, 9.00), (24, 11.00), (30, 12.00), (40, 14.00), (50, 16.00),
    (60, 18.00), (70, 20.00), (80, 22.00), (90, 24.00), (100, 26.00), (120, 30.00),
    (140, 32.00), (160, 34.00), (180, 36.00), (200, 38.00), (220, 39.00), (300, 40.00),
    (400, 41.00), (500, 42.00),
]  # fmt: skip


def _leg(
    carrier,
    origin,
    destination,
    origin_xy,
    destination_xy,
    *,
    mode=LegMode.RAIL,
    minutes=20,
    motis_mode=None,
    extra=None,
    distance_km="prosta",
):
    depart = datetime(2026, 10, 20, 8, 0)
    leg_extra = {}
    if origin_xy and destination_xy:
        leg_extra.update(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
    if motis_mode:
        leg_extra["motis_mode"] = motis_mode
    leg_extra.update(extra or {})
    if distance_km == "prosta":
        distance_km = motis_client.haversine_km(*origin_xy, *destination_xy) if origin_xy else None
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name=carrier,
        distance_km=distance_km,
        extra=leg_extra,
    )


def _skm_segment(km, ulga="brak", *, po_torach=False):
    return Segment(
        carrier=Carrier.SKM_TROJMIASTO,
        origin="A",
        destination="B",
        distance_km=km,
        discounts=DiscountProfile(pkp_ulga_kod=ulga),
        distance_along_track=po_torach,
    )


# --- SKM Trójmiasto: dane ------------------------------------------------------------------

SKM = load("skm_trojmiasto.json")


def test_skm_21_pasm_zgodnych_z_raportem():
    assert len(SKM["pasma_odleglosci_km"]) == 21
    assert [(b["do_km"], b["cena"]) for b in SKM["pasma_odleglosci_km"]] == SKM_PASMA
    assert SKM["obowiazuje_od"] == "2026-03-01"


def test_skm_nie_ma_archiwalnych_cen_sprzed_marca_2026():
    ceny = {b["do_km"]: b["cena"] for b in SKM["pasma_odleglosci_km"]}
    assert ceny[40] == 14.00  # nie 12,00 (cennik 2023-2024)
    assert ceny[24] == 11.00  # nie 10,00


def test_skm_kazde_pasmo_ma_zrodlo_date_i_status_gemini():
    for b in SKM["pasma_odleglosci_km"]:
        c = b["potwierdzone"]
        assert c["zrodlo_url"] == (
            "https://www.skm.pkp.pl/files/user-uploads/ms/1_marca_2026/Cennik_1_marca_2026_po_zm_1.pdf"
        )
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["data"])
        assert c["status"] == STATUS
    assert STATUS in SKM["_status_weryfikacji"]


def test_skm_tabele_ulg_zgodne_z_procentem_od_ceny_normalnej():
    procent = {"37": 0.37, "49": 0.49, "51": 0.51}
    for b in SKM["pasma_odleglosci_km"]:
        assert set(b["ulgi"]) == set(procent)
        for kod, kwota in b["ulgi"].items():
            assert kwota == pytest.approx(round(b["cena"] * (1 - procent[kod]), 2), abs=0.011), b


def test_skm_tabela_rosnaca():
    do = [b["do_km"] for b in SKM["pasma_odleglosci_km"]]
    ceny = [b["cena"] for b in SKM["pasma_odleglosci_km"]]
    assert do == sorted(do)
    assert ceny == sorted(ceny)


def test_skm_dokumentuje_brak_honorowania_biletow_ztm_zkm():
    assert "ZTM Gdańsk" in SKM["_honorowanie"] and "ZKM Gdynia" in SKM["_honorowanie"]
    assert "NIE" in SKM["_honorowanie"]


# --- SKM Trójmiasto: kalkulator -------------------------------------------------------------


@pytest.mark.parametrize(
    "km, oczekiwana",
    [
        (0.5, 7.00),
        (6, 7.00),
        (6.1, 8.00),  # km taryfowe zaokrąglamy w górę
        (12, 8.00),
        (19, 11.00),
        (24, 11.00),
        (25, 12.00),
        (40, 14.00),
        (41, 16.00),
        (500, 42.00),
    ],
)
def test_skm_pasma_odleglosci(km, oczekiwana):
    assert skm_trojmiasto.estimate(_skm_segment(km)).amount == oczekiwana


def test_skm_powyzej_ostatniego_pasma_blad():
    with pytest.raises(ValueError, match="brak pasma"):
        skm_trojmiasto.estimate(_skm_segment(501))


def test_skm_brak_dystansu_to_blad():
    with pytest.raises(ValueError, match="distance_km"):
        skm_trojmiasto.estimate(_skm_segment(None))


def test_skm_linia_prosta_to_szacunek_z_opisem_i_zrodlem():
    est = skm_trojmiasto.estimate(_skm_segment(20))
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is False  # Gemini bez drugiego źródła (CONTRIBUTING.md)
    assert "Gemini" in est.breakdown["powod_szacunku"]
    assert est.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert est.breakdown["status_weryfikacji"] == STATUS
    assert est.breakdown["zrodlo_url"].startswith("https://www.skm.pkp.pl/")
    assert est.breakdown["data_weryfikacji"] == "2026-10-12"
    assert "linii prostej" in est.notes
    assert STATUS in est.notes
    assert "ZTM Gdańsk" in est.notes and "ZKM Gdynia" in est.notes


def test_skm_km_po_torach_bez_drugiego_zrodla_to_nadal_szacunek_niepotwierdzony():
    est = skm_trojmiasto.estimate(_skm_segment(20, po_torach=True))
    assert est.amount == 11.00
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is False
    assert est.breakdown["odleglosc_taryfowa"] == "po torach"
    assert "linii prostej" not in est.notes


def _tabela_z_drugim_zrodlem():
    """Kopia tabeli SKM, w której każde pasmo ma status inny niż „wg Gemini, niezweryfikowane”."""
    tabela = json.loads(json.dumps(SKM))
    for b in tabela["pasma_odleglosci_km"]:
        b["potwierdzone"]["status"] = "potwierdzone w drugim niezależnym źródle"
    return tabela


def test_skm_drugie_zrodlo_w_danych_przywraca_oficjalna_taryfe():
    # Po dodaniu drugiego źródła (zmiana "status" w danych) km po torach dają OFFICIAL.
    tabela = _tabela_z_drugim_zrodlem()
    est = skm_trojmiasto.estimate(_skm_segment(20, po_torach=True), tabela)
    assert est.breakdown["price_verified"] is True
    assert est.price_type is PriceType.OFFICIAL
    prosta = skm_trojmiasto.estimate(_skm_segment(20), tabela)
    assert prosta.breakdown["price_verified"] is True
    assert prosta.price_type is PriceType.ESTIMATE  # linia prosta zawsze szacunek


def test_skm_ulgi_ustawowe_z_tabel_ulg_tez_niepotwierdzone_bez_drugiego_zrodla():
    student = skm_trojmiasto.estimate(
        _skm_segment(20, "student_do_26_lat_doktorant_do_35_lat", po_torach=True)
    )
    assert student.amount == 5.39  # Tabela nr 8 (51%), pasmo 19-24 km
    assert student.breakdown["price_verified"] is False
    assert student.price_type is PriceType.ESTIMATE
    dziecko = skm_trojmiasto.estimate(_skm_segment(20, "dzieci_mlodziez_szkolna_do_24_lat"))
    assert dziecko.amount == 6.93  # Tabela nr 4 (37%)
    assert dziecko.breakdown["price_verified"] is False


def test_skm_ulgi_z_tabel_po_drugim_zrodle_sa_potwierdzone():
    student = skm_trojmiasto.estimate(
        _skm_segment(20, "student_do_26_lat_doktorant_do_35_lat", po_torach=True),
        _tabela_z_drugim_zrodlem(),
    )
    assert student.breakdown["price_verified"] is True
    assert student.price_type is PriceType.OFFICIAL


def test_skm_ulga_spoza_tabel_liczona_procentem_i_niepotwierdzona():
    est = skm_trojmiasto.estimate(
        _skm_segment(20, "zolnierze_niezawodowej_sluzby_wojskowej", po_torach=True)
    )
    assert est.amount == round(11.00 * (1 - 0.78), 2)
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE
    assert "procentem" in est.notes


def test_skm_nie_przyjmuje_innego_przewoznika():
    seg = _skm_segment(10)
    seg.carrier = Carrier.POLREGIO_PODSTAWOWA
    with pytest.raises(ValueError, match="przewoźnik"):
        skm_trojmiasto.estimate(seg)


# --- SKM Trójmiasto: routing ----------------------------------------------------------------


def test_skm_trojmiasto_w_trybie_rail_dostaje_tabele():
    leg = _leg("PKP SKM", "Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.SKM_TROJMIASTO
    assert priced.price_type == "szacunek"  # linia prosta
    assert priced.breakdown["price_verified"] is False
    assert priced.price_verified is False
    assert priced.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert priced.amount == skm_trojmiasto.estimate(_skm_segment(leg.distance_km)).amount


def test_skm_trojmiasto_w_trybie_suburban_dostaje_tabele():
    leg = _leg(
        "SKM",
        "Gdańsk Główny",
        "Gdynia Główna",
        GDANSK_GLOWNY,
        GDYNIA_GLOWNA,
        mode=LegMode.BUS,  # tak mapuje SUBURBAN motis_client.itinerary_to_legs
        motis_mode="SUBURBAN",
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.SKM_TROJMIASTO
    assert priced.amount not in (pricing.LOCAL_BUS_FLAT_PLN, round(0.35 * leg.distance_km, 2))
    assert "tryb_motis" not in priced.breakdown


def test_skm_trojmiasto_uzywa_km_po_torach_gdy_sa_dostepne():
    # Linia prosta 17,4 km -> pasmo 13-18 (9,00 zł); po torach 19,2 km -> pasmo 19-24 (11,00 zł).
    wspolne = dict(minutes=25, distance_km=17.4)
    prosta = _leg("SKM", "Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA, **wspolne)
    po_torach = _leg(
        "SKM",
        "Gdańsk Główny",
        "Gdynia Główna",
        GDANSK_GLOWNY,
        GDYNIA_GLOWNA,
        extra={
            "distance_along_track_km": 19.2,
            "distance_along_track_source": "legGeometry MOTIS",
        },
        **wspolne,
    )
    a = pricing.price_rail_leg(prosta, DiscountProfile())
    b = pricing.price_rail_leg(po_torach, DiscountProfile())
    assert (a.amount, a.price_type) == (9.00, "szacunek")
    assert (b.amount, b.price_type) == (11.00, "szacunek")  # Gemini, bez drugiego źródła
    assert b.price_verified is False
    assert b.breakdown["odleglosc_taryfowa"] == "po torach"
    assert b.breakdown["zrodlo_km"] == "legGeometry MOTIS"


def test_skm_trojmiasto_z_ulga_studencka_z_tabeli_ulg():
    leg = _leg("SKM", "Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA)
    leg.distance_km = 20.0
    d = DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat")
    assert pricing.price_rail_leg(leg, d).amount == 5.39


def test_skm_trojmiasto_bez_wspolrzednych_po_nazwie_przewoznika():
    leg = _leg(
        "PKP Szybka Kolej Miejska w Trójmieście",
        "Gdańsk Główny",
        "Gdynia Główna",
        None,
        None,
        distance_km=20.0,
    )
    assert pricing.price_rail_leg(leg, DiscountProfile()).carrier is Carrier.SKM_TROJMIASTO


def test_samo_skm_bez_wspolrzednych_i_bez_trojmiasta_nie_dostaje_tabeli():
    leg = _leg("SKM", "Szczecin Główny", "Szczecin Gumieńce", None, None, distance_km=6.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.breakdown["price_verified"] is False


def test_skm_poza_obszarem_trojmiasta_nie_dostaje_tabeli():
    leg = _leg("SKM", "Gdynia Główna", "Wejherowo", GDYNIA_GLOWNA, WEJHEROWO)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.price_verified is False


def test_skm_trojmiasto_bez_dystansu_to_niepotwierdzony_fallback():
    leg = _leg(
        "SKM", "Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA, distance_km=None
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"


# --- SKM Warszawa: bilety czasowe ZTM ---------------------------------------------------------


def test_dane_ztm_warszawa_zgodne_z_raportem_i_z_zrodlem_honorowania():
    dane = load("ztm_warszawa.json")
    bilety = {b["wazny_min"]: (b["normalny"], b["strefa"]) for b in dane["bilety_czasowe"]}
    assert bilety == {20: (3.40, "1+2"), 75: (4.40, "1"), 90: (7.00, "1+2")}
    assert "https://www.wtp.waw.pl/ceny-i-rodzaje-biletow/" in dane["_zrodlo_skm"]
    assert STATUS in dane["_zrodlo_skm"]
    assert "NIE są honorowane" in dane["_zrodlo_km_wkd"]
    assert "Płudy" in dane["_zrodlo_km_wkd"] and "Lotnisko Chopina" in dane["_zrodlo_km_wkd"]


@pytest.mark.parametrize(
    "minuty, kwota, wazny_min, strefa",
    [(15, 3.40, 20, "1+2"), (20, 3.40, 20, "1+2"), (60, 4.40, 75, "1"), (85, 7.00, 90, "1+2")],
)
@pytest.mark.parametrize("tryb", ["rail", "suburban"])
def test_skm_warszawa_cena_to_bilet_czasowy_ztm(minuty, kwota, wazny_min, strefa, tryb):
    leg = _leg(
        "Szybka Kolej Miejska",
        "Warszawa Centralna",
        "Warszawa Wschodnia",
        WARSZAWA_CENTRALNA,
        WARSZAWA_WSCHODNIA,
        minutes=minuty,
        mode=LegMode.RAIL if tryb == "rail" else LegMode.BUS,
        motis_mode="SUBURBAN" if tryb == "suburban" else None,
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.ZTM_WARSZAWA
    assert (priced.amount, priced.currency) == (kwota, "PLN")
    assert priced.breakdown["bilet_wazny_min"] == wazny_min
    assert priced.breakdown["strefa"] == strefa
    assert priced.breakdown["kolej"] == "SKM Warszawa"
    assert priced.breakdown["status_weryfikacji_honorowania"] == STATUS
    assert STATUS in priced.notes
    assert priced.breakdown["price_verified"] is False
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"


def test_skm_warszawa_ulgowy_ztm():
    leg = _leg(
        "SKM",
        "Warszawa Centralna",
        "Warszawa Zachodnia",
        WARSZAWA_CENTRALNA,
        WARSZAWA_ZACHODNIA,
        minutes=60,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile(ztm_warszawa_ulgowy=True))
    assert (priced.carrier, priced.amount) == (Carrier.ZTM_WARSZAWA, 2.20)
    assert priced.price_verified is False


def test_skm_warszawa_poza_kolem_ztm_nie_jest_zgadywane():
    leg = _leg(
        "Szybka Kolej Miejska", "Warszawa Zachodnia", "Pruszków", WARSZAWA_ZACHODNIA, PRUSZKOW
    )
    assert pricing.infer_pl_local_rail_carrier(leg) is None
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None and priced.price_verified is False


def test_skm_trojmiasto_nie_dostaje_biletu_ztm_warszawa():
    leg = _leg("SKM", "Gdańsk Główny", "Gdynia Główna", GDANSK_GLOWNY, GDYNIA_GLOWNA)
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.SKM_TROJMIASTO


# --- KM i WKD: bilety czasowe ZTM nie są honorowane --------------------------------------------


@pytest.mark.parametrize("przewoznik", ["WKD", "Warszawska Kolej Dojazdowa"])
def test_wkd_w_warszawie_w_trybie_suburban_nie_dostaje_biletu_ztm(przewoznik):
    leg = _leg(
        przewoznik,
        "Warszawa Wschodnia",
        "Warszawa Zachodnia",
        WARSZAWA_WSCHODNIA,
        WARSZAWA_ZACHODNIA,
        mode=LegMode.BUS,
        motis_mode="SUBURBAN",
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"
    assert "nie są honorowane" in priced.notes
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * leg.distance_km, 2)


@pytest.mark.parametrize("tryb", ["rail", "suburban"])
def test_km_w_warszawie_nie_dostaje_biletu_ztm_tylko_tabele_km(tryb):
    leg = _leg(
        "Koleje Mazowieckie",
        "Warszawa Wschodnia",
        "Warszawa Zachodnia",
        WARSZAWA_WSCHODNIA,
        WARSZAWA_ZACHODNIA,
        mode=LegMode.RAIL if tryb == "rail" else LegMode.BUS,
        motis_mode="SUBURBAN" if tryb == "suburban" else None,
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MAZOWIECKIE


@pytest.mark.parametrize(
    "origin, destination, origin_xy, destination_xy",
    [
        ("Warszawa Płudy", "Warszawa Lotnisko Chopina", WARSZAWA_PLUDY, WARSZAWA_LOTNISKO),
        ("Warszawa Lotnisko Chopina", "Warszawa Płudy", WARSZAWA_LOTNISKO, WARSZAWA_PLUDY),
    ],
)
@pytest.mark.parametrize("tryb", ["rail", "bus"])
def test_linia_lotniskowa_km_pludy_lotnisko_honoruje_bilety_czasowe_ztm(
    origin, destination, origin_xy, destination_xy, tryb
):
    leg = _leg(
        "Koleje Mazowieckie",
        origin,
        destination,
        origin_xy,
        destination_xy,
        minutes=18,
        mode=LegMode.RAIL if tryb == "rail" else LegMode.BUS,
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.ZTM_WARSZAWA
    assert priced.amount == 3.40
    assert priced.breakdown["kolej"] == "KM linia lotniskowa Płudy - Lotnisko Chopina"
    assert STATUS in priced.notes
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"


def test_wyjatek_lotniskowy_dotyczy_tylko_pary_pludy_lotnisko():
    leg = _leg(
        "Koleje Mazowieckie",
        "Warszawa Płudy",
        "Warszawa Wschodnia",
        WARSZAWA_PLUDY,
        WARSZAWA_WSCHODNIA,
    )
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.KOLEJE_MAZOWIECKIE
    assert not pricing.is_warsaw_airport_line(leg)


def test_koleje_malopolskie_maja_osobna_sciezke_nie_zgrubny_szacunek():
    # KMŁ wdrożone osobno (tests/test_koleje_malopolskie_tariff.py); tu tylko: nie przez POLREGIO/KM.
    leg = _leg(
        "Koleje Małopolskie", "Kraków Główny", "Tarnów", (50.0680, 19.9475), (50.0120, 20.9860)
    )
    assert pricing.infer_pl_regional_carrier(leg) is None
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.KOLEJE_MALOPOLSKIE
    assert not pricing._is_km_or_wkd(leg)


# --- ŁKA w Łodzi ------------------------------------------------------------------------------

LKA = load("lka_lodz.json")


def test_lka_dane_zgodne_z_raportem():
    bilety = {b["wazny_min"]: (b["normalny"], b["ulgowy"]) for b in LKA["bilety_czasowe"]}
    assert bilety == {20: (4.40, 2.20), 40: (5.60, 2.80), 80: (6.80, 3.40)}
    assert all(b["strefa"] == "A" for b in LKA["bilety_czasowe"])
    zrodlo = LKA["_zrodlo"] + LKA["_status_weryfikacji"]
    assert "https://lka.lodzkie.pl/Honorowanie-biletow-komunikacji-miejskiej-w-Lodzi/" in zrodlo
    assert STATUS in LKA["_status_weryfikacji"]
    assert "Open Payment System" in LKA["_uwaga"] and "QR" in LKA["_uwaga"]


@pytest.mark.parametrize(
    "minuty, kwota, wazny_min, typ",
    [
        (10, 4.40, 20, "szacunek"),
        (20, 4.40, 20, "szacunek"),
        (21, 5.60, 40, "szacunek"),
        (40, 5.60, 40, "szacunek"),
        (41, 6.80, 80, "szacunek"),
        (80, 6.80, 80, "szacunek"),
        (100, 6.80, 80, "szacunek"),  # dłużej niż najdłuższy bilet
    ],
)
def test_lka_w_lodzi_bilet_czasowy_wg_czasu_jazdy(minuty, kwota, wazny_min, typ):
    leg = _leg(
        "Łódzka Kolej Aglomeracyjna",
        "Łódź Kaliska",
        "Łódź Widzew",
        LODZ_KALISKA,
        LODZ_WIDZEW,
        minutes=minuty,
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.LKA_LODZ
    assert (priced.amount, priced.currency, priced.price_type) == (kwota, "PLN", typ)
    assert priced.breakdown["bilet_wazny_min"] == wazny_min
    assert priced.breakdown["strefa"] == "A"
    assert priced.breakdown["status_weryfikacji"] == STATUS
    assert priced.breakdown["price_verified"] is False  # Gemini bez drugiego źródła
    assert priced.price_verified is False
    assert "MPK" in priced.notes and "QR" in priced.notes


def test_lka_drugie_zrodlo_w_danych_przywraca_oficjalna_taryfe(monkeypatch):
    tabela = json.loads(json.dumps(LKA))
    tabela["weryfikacja"]["status"] = "potwierdzone w drugim niezależnym źródle"
    monkeypatch.setattr(lka_lodz, "_TABLE", tabela)
    leg = _leg("ŁKA", "Łódź Kaliska", "Łódź Widzew", LODZ_KALISKA, LODZ_WIDZEW, minutes=15)
    priced = pricing.price_leg(leg, DiscountProfile())
    assert (priced.amount, priced.price_type) == (4.40, "oficjalna_taryfa")
    assert priced.price_verified is True


def test_lka_sprinter_w_trybie_suburban_tez_w_lodzi():
    leg = _leg(
        "ŁKA Sprinter",
        "Łódź Kaliska",
        "Łódź Widzew",
        LODZ_KALISKA,
        LODZ_WIDZEW,
        mode=LegMode.BUS,
        motis_mode="SUBURBAN",
        minutes=15,
    )
    priced = pricing.price_leg(leg, DiscountProfile())
    assert (priced.carrier, priced.amount) == (Carrier.LKA_LODZ, 4.40)


def test_lka_z_ulga_pokazuje_cene_normalna_jako_niepotwierdzona():
    leg = _leg("ŁKA", "Łódź Kaliska", "Łódź Widzew", LODZ_KALISKA, LODZ_WIDZEW, minutes=15)
    priced = pricing.price_rail_leg(
        leg, DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat")
    )
    assert priced.amount == 4.40
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"
    assert "nie są modelowane" in priced.notes


def test_lka_poza_lodzia_nie_dostaje_taryfy_strefy_a():
    leg = _leg("Łódzka Kolej Aglomeracyjna", "Łódź Kaliska", "Zgierz", LODZ_KALISKA, ZGIERZ)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.price_verified is False


def test_lka_bez_wspolrzednych_wymaga_lodzi_w_obu_nazwach_przystankow():
    w_lodzi = _leg("ŁKA", "Łódź Kaliska", "Łódź Widzew", None, None, distance_km=5.0, minutes=12)
    poza = _leg("ŁKA", "Łódź Kaliska", "Zgierz", None, None, distance_km=12.0, minutes=20)
    assert pricing.price_rail_leg(w_lodzi, DiscountProfile()).carrier is Carrier.LKA_LODZ
    assert pricing.price_rail_leg(poza, DiscountProfile()).carrier is None


def test_lka_bez_czasu_jazdy_to_blad_kalkulatora():
    from fares import estimate_price

    seg = Segment(carrier=Carrier.LKA_LODZ, origin="A", destination="B")
    with pytest.raises(ValueError, match="ride_duration_min"):
        estimate_price(seg)


def test_pliki_danych_sa_poprawnym_json_z_url_zrodla():
    for nazwa in ("skm_trojmiasto.json", "lka_lodz.json"):
        tekst = (Path(__file__).parent.parent / "fares" / "data" / nazwa).read_text(
            encoding="utf-8"
        )
        dane = json.loads(tekst)
        assert "http" in dane["_zrodlo"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", dane["as_of"])
