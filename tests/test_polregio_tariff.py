"""Degresywna tabela Taryfy Podstawowej POLREGIO/KD/KŚ zamiast sztywnego 0,35 zł/km.

Wszystkie 30 pasm w fares/data/polregio_taryfa_podstawowa.json zostało potwierdzone przez Gemini
w TPR POLREGIO od 1.09.2026 (źródło i data przy każdym paśmie). Potwierdzona jest KWOTA pasma;
odległość z MOTIS to linia prosta, więc wynik ma price_verified=True, ale price_type "szacunek"
z opisem przybliżenia, dopóki Segment.distance_along_track nie jest True (km po torach).
Pasmo bez źródła/daty zostaje niepotwierdzone — to sprawdza sztuczna fixture
tests/fixtures/polregio_tabela_z_potwierdzeniem.json (nie dane cenowe)."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fares import polregio
from fares._data_loading import load
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import pricing
from routing.model import Leg, LegMode

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "polregio_tabela_z_potwierdzeniem.json").read_text(
        encoding="utf-8"
    )
)
TABLE = load("polregio_taryfa_podstawowa.json")

LUBLIN_GLOWNY = (51.2297, 22.5745)
DEBLIN = (51.5640, 21.8473)
SZCZECIN_GLOWNY = (53.4285, 14.5528)
ANGERMUENDE = (53.0136, 13.9947)
BERLIN_HBF = (52.5251, 13.3694)
ESSEN_HBF = (51.4514, 7.0139)
DORTMUND_HBF = (51.5178, 7.4593)


def _segment(km, ulga="brak", *, po_torach=False):
    return Segment(
        carrier=Carrier.POLREGIO_PODSTAWOWA,
        origin="A",
        destination="B",
        distance_km=km,
        discounts=DiscountProfile(pkp_ulga_kod=ulga),
        distance_along_track=po_torach,
    )


def _leg(carrier, origin_xy=None, destination_xy=None, *, distance_km=40.0, extra=None):
    depart = datetime(2026, 10, 20, 8, 0)
    extra = dict(extra or {})
    if origin_xy and destination_xy:
        extra.update(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
    return Leg(
        mode=LegMode.RAIL,
        origin_name="A",
        destination_name="B",
        depart=depart,
        arrive=depart + timedelta(minutes=60),
        carrier_name=carrier,
        distance_km=distance_km,
        extra=extra,
    )


# --- dane --------------------------------------------------------------------------------


def test_klucz_liczb_z_raportu_jest_w_tabeli():
    ceny = {b["do_km"]: b["cena"] for b in TABLE["pasma_odleglosci_km"]}
    assert ceny[5] == 6.10
    assert ceny[80] == 25.90
    assert ceny[100] == 29.70


def test_tabela_jest_rosnaca_i_degresywna_w_przeliczeniu_na_km():
    pasma = TABLE["pasma_odleglosci_km"]
    assert [b["do_km"] for b in pasma] == sorted(b["do_km"] for b in pasma)
    ceny = [b["cena"] for b in pasma]
    assert ceny == sorted(ceny)
    stawka_100 = 29.70 / 100
    stawka_5 = 6.10 / 5
    assert stawka_5 > 0.35 > stawka_100


def test_wszystkie_pasma_potwierdzone_ze_zrodlem_i_data():
    assert TABLE["weryfikacja"]["status"] == "potwierdzone"
    assert len(TABLE["pasma_odleglosci_km"]) == 30
    for b in TABLE["pasma_odleglosci_km"]:
        c = b["potwierdzone"]
        assert c["zrodlo_url"].startswith("https://"), b
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["data"]), b


# --- kalkulator --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "km, oczekiwana",
    [
        (0.5, 6.10),
        (5.0, 6.10),
        (5.4, 6.70),  # taryfowe km zaokrąglamy w górę: 6 km = pasmo 6-10
        (10, 6.70),
        (77, 25.90),
        (80, 25.90),
        (95, 29.70),
        (200, 42.20),
        (800, 61.20),
    ],
)
def test_pasma_odleglosci(km, oczekiwana):
    assert polregio.estimate(_segment(km)).amount == oczekiwana


def test_powyzej_ostatniego_pasma_blad_zamiast_zgadywania():
    with pytest.raises(ValueError, match="brak pasma"):
        polregio.estimate(_segment(801))


def test_brak_dystansu_to_blad():
    with pytest.raises(ValueError, match="distance_km"):
        polregio.estimate(_segment(None))


def test_wynik_z_potwierdzonego_pasma_ma_zrodlo_ale_zostaje_szacunkiem_dla_linii_prostej():
    est = polregio.estimate(_segment(77))
    assert est.breakdown["price_verified"] is True
    assert est.breakdown["zrodlo_url"].startswith("https://polregio.pl/")
    assert est.breakdown["data_weryfikacji"] == "2026-10-12"
    assert est.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert est.price_type is PriceType.ESTIMATE
    assert "linii prostej" in est.notes
    assert "NIEPOTWIERDZONA" not in est.notes


def test_km_po_torach_i_potwierdzone_pasmo_to_oficjalna_taryfa():
    est = polregio.estimate(_segment(77, po_torach=True))
    assert est.price_type is PriceType.OFFICIAL
    assert est.breakdown["price_verified"] is True
    assert est.breakdown["odleglosc_taryfowa"] == "po torach"
    assert "linii prostej" not in est.notes


def test_ulga_procentem_od_ceny_bazowej_i_nie_jest_odczytem_z_cennika():
    est = polregio.estimate(_segment(77, "student_do_26_lat_doktorant_do_35_lat", po_torach=True))
    assert est.amount == pytest.approx(25.90 * 0.49, abs=0.01)
    assert est.breakdown["ulga_procent"] == 51
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE
    assert "ulga" in est.breakdown["powod_szacunku"]


def test_nieznany_kod_ulgi():
    with pytest.raises(ValueError, match="nieznany kod ulgi"):
        polregio.estimate(_segment(10, "wymyslona"))


# --- ścieżka 'pasmo potwierdzone' (fixture) -----------------------------------------------


def test_potwierdzone_pasmo_z_url_i_data_po_torach_daje_oficjalna_taryfe():
    est = polregio.estimate(_segment(3, po_torach=True), table=FIXTURE)
    assert est.amount == 10.0
    assert est.price_type is PriceType.OFFICIAL
    assert est.breakdown["price_verified"] is True
    assert est.breakdown["zrodlo_url"] == "https://example.invalid/cennik.pdf"
    assert est.breakdown["data_weryfikacji"] == "2026-10-12"


def test_potwierdzone_pasmo_z_linii_prostej_to_szacunek_z_opisem_przyblizenia():
    est = polregio.estimate(_segment(3), table=FIXTURE)
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is True
    assert "linii prostej" in est.notes


def test_pasmo_bez_potwierdzenia_w_tej_samej_tabeli_zostaje_szacunkiem():
    est = polregio.estimate(_segment(8, po_torach=True), table=FIXTURE)
    assert est.amount == 20.0
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is False
    assert "NIEPOTWIERDZONA" in est.notes


@pytest.mark.parametrize("km", [15, 30])  # puste 'data' / URL nie jest adresem http
def test_potwierdzenie_bez_daty_albo_url_nie_liczy_sie(km):
    est = polregio.estimate(_segment(km), table=FIXTURE)
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE


def test_potwierdzone_pasmo_z_ulga_juz_nie_jest_odczytem_z_cennika():
    est = polregio.estimate(
        _segment(3, "dzieci_mlodziez_szkolna_do_24_lat", po_torach=True), table=FIXTURE
    )
    assert est.amount == pytest.approx(6.30)
    assert est.breakdown["price_verified"] is False


# --- routing: kto dostaje tabelę, a kto nadal zgrubny szacunek 0,35 zł/km ---------------------


@pytest.mark.parametrize(
    "przewoznik", ["POLREGIO", "Polregio sp. z o.o.", "Koleje Dolnośląskie", "Koleje Śląskie"]
)
def test_polregio_kd_ks_w_polsce_dostaja_tabele(przewoznik):
    leg = _leg(przewoznik, LUBLIN_GLOWNY, DEBLIN, distance_km=57.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.POLREGIO_PODSTAWOWA
    assert priced.amount == 22.00  # pasmo 54-59 km
    assert priced.currency == "PLN"
    # kwota pasma potwierdzona, ale odległość to linia prosta z MOTIS -> szacunek z opisem
    assert priced.price_type == "szacunek"
    assert priced.breakdown["price_verified"] is True
    assert priced.price_verified is True
    assert priced.breakdown["zrodlo_url"].startswith("https://polregio.pl/")
    assert priced.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert "linii prostej" in priced.notes


def test_tabela_zastepuje_sztywne_035_na_krotkim_odcinku():
    leg = _leg("POLREGIO", LUBLIN_GLOWNY, DEBLIN, distance_km=5.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.amount == 6.10
    assert priced.amount != round(pricing.GENERIC_FALLBACK_PLN_PER_KM * 5.0, 2)  # 1,75 zł


def test_polregio_rozpoznane_po_prefiksie_datasetu_gdy_brak_wspolrzednych():
    leg = _leg(
        "POLREGIO",
        distance_km=30.0,
        extra={"origin_stop_id": "pl_123", "destination_stop_id": "pl_456"},
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.POLREGIO_PODSTAWOWA
    assert priced.amount == 12.70


def test_polregio_bez_ustalonego_kraju_dalej_zgrubny_szacunek():
    leg = _leg("POLREGIO", distance_km=30.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.amount == round(0.35 * 30.0, 2)
    assert priced.breakdown["price_verified"] is False


def test_polregio_transgraniczne_nie_dostaje_polskiej_tabeli():
    leg = _leg("POLREGIO", SZCZECIN_GLOWNY, ANGERMUENDE, distance_km=58.2)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.amount == round(0.35 * 58.2, 2)
    assert priced.breakdown["price_verified"] is False


def test_polregio_w_niemczech_nie_dostaje_polskiej_tabeli():
    leg = _leg("POLREGIO", ESSEN_HBF, DORTMUND_HBF, distance_km=33.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is not Carrier.POLREGIO_PODSTAWOWA


@pytest.mark.parametrize(
    "przewoznik",
    ["Łódzka Kolej Aglomeracyjna", "SKM Trójmiasto", "Jakiś Nieznany"],
)
def test_pozostali_przewoznicy_polscy_dalej_zgrubny_szacunek(przewoznik):
    leg = _leg(przewoznik, LUBLIN_GLOWNY, DEBLIN, distance_km=57.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.amount == round(0.35 * 57.0, 2)
    assert priced.breakdown["price_verified"] is False
