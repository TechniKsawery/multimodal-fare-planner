"""Koleje Mazowieckie: Tabela nr 1 taryfy TP-KM (27 pasm, bilet jednorazowy normalny, 2. klasa, brutto).

Źródło: oficjalny PDF TP-KM ze zmianami 1–6, s. 13; tabelę potwierdził w PDF właściciel projektu
2026-10-13 (price_verified=True). Ulgi, bilety okresowe i powyżej 520 km nie są modelowane.
"""

from datetime import datetime, timedelta

import pytest

from fares import koleje_mazowieckie
from fares._data_loading import load
from fares.calculator import estimate_price
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing
from routing.model import Leg, LegMode

URL = (
    "https://www.mazowieckie.com.pl/sites/default/files/Za%C5%82%C4%85cznik%20do%20Taryfy%20"
    "przewozowej%20Kolei%20Mazowieckich-KM%20%28TP-KM%29%20z%20uwzgl.%20Zmian%20nr%201-6_0.pdf"
)

# Tabela nr 1 ze s. 13 PDF: (górna granica km, brutto, PTU, netto).
TABELA = [
    (5, 4.20, 0.31, 3.89), (10, 7.50, 0.56, 6.94), (15, 8.80, 0.65, 8.15),
    (20, 10.40, 0.77, 9.63), (30, 13.60, 1.01, 12.59), (40, 15.30, 1.13, 14.17),
    (50, 17.90, 1.33, 16.57), (60, 19.70, 1.46, 18.24), (70, 21.80, 1.61, 20.19),
    (80, 24.20, 1.79, 22.41), (90, 26.50, 1.96, 24.54), (100, 28.90, 2.14, 26.76),
    (120, 31.80, 2.36, 29.44), (140, 33.90, 2.51, 31.39), (160, 36.50, 2.70, 33.80),
    (180, 38.50, 2.85, 35.65), (200, 41.40, 3.07, 38.33), (220, 44.20, 3.27, 40.93),
    (240, 45.60, 3.38, 42.22), (260, 47.00, 3.48, 43.52), (280, 49.70, 3.68, 46.02),
    (320, 51.20, 3.79, 47.41), (360, 52.30, 3.87, 48.43), (400, 54.10, 4.01, 50.09),
    (440, 55.60, 4.12, 51.48), (480, 56.70, 4.20, 52.50), (520, 58.90, 4.36, 54.54),
]  # fmt: skip

KM = load("koleje_mazowieckie.json")
WARSZAWA_WSCHODNIA = (52.2519, 21.0885)
SIEDLCE = (52.1690, 22.2860)
RADOM = (51.4027, 21.1471)
WARSZAWA_ZACHODNIA = (52.2194, 20.9657)


def _segment(km, ulga="brak", *, po_torach=False, source=None):
    return Segment(
        carrier=Carrier.KOLEJE_MAZOWIECKIE,
        origin="A",
        destination="B",
        distance_km=km,
        discounts=DiscountProfile(pkp_ulga_kod=ulga),
        distance_along_track=po_torach,
        distance_source=source,
    )


def _leg(carrier="Koleje Mazowieckie", origin="Warszawa Wschodnia", destination="Siedlce",
         origin_xy=WARSZAWA_WSCHODNIA, destination_xy=SIEDLCE, *, mode=LegMode.RAIL,
         distance_km="prosta", extra=None):  # fmt: skip
    depart = datetime(2026, 10, 20, 8, 0)
    leg_extra = dict(
        origin_lat=origin_xy[0],
        origin_lon=origin_xy[1],
        destination_lat=destination_xy[0],
        destination_lon=destination_xy[1],
    )
    leg_extra.update(extra or {})
    if distance_km == "prosta":
        distance_km = motis_client.haversine_km(*origin_xy, *destination_xy)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=60),
        distance_km=distance_km,
        carrier_name=carrier,
        extra=leg_extra,
    )


def test_tabela_ma_27_pasm_zgodnych_z_pdf():
    pasma = KM["pasma_odleglosci_km"]
    assert [(b["do_km"], b["cena"], b["ptu"], b["netto"]) for b in pasma] == TABELA


def test_brutto_rowna_sie_netto_plus_ptu_w_kazdym_pasmie():
    for b in KM["pasma_odleglosci_km"]:
        assert round(b["netto"] + b["ptu"], 2) == b["cena"], b["zakres"]


def test_kazde_pasmo_ma_zrodlo_url_i_date_weryfikacji():
    for b in KM["pasma_odleglosci_km"]:
        assert b["potwierdzone"]["zrodlo_url"] == URL
        assert b["potwierdzone"]["data"] == "2026-10-13"
    assert KM["zrodlo"]["url"] == URL


@pytest.mark.parametrize("do_km, cena, _ptu, _netto", TABELA)
def test_gorna_granica_kazdego_pasma(do_km, cena, _ptu, _netto):
    assert koleje_mazowieckie.estimate(_segment(do_km)).amount == cena


@pytest.mark.parametrize(
    "km, cena",
    [(5, 4.20), (5.01, 7.50), (6, 7.50), (10, 7.50), (11, 8.80), (30, 13.60), (31, 15.30),
     (40, 15.30), (41, 17.90), (100, 28.90), (101, 31.80), (480, 56.70), (481, 58.90),
     (520, 58.90)],
)  # fmt: skip
def test_granice_pasm(km, cena):
    assert koleje_mazowieckie.estimate(_segment(km)).amount == cena


def test_powyzej_520_km_brak_pasma():
    with pytest.raises(ValueError, match="brak pasma"):
        koleje_mazowieckie.estimate(_segment(520.01))
    with pytest.raises(ValueError, match="brak pasma"):
        koleje_mazowieckie.estimate(_segment(521))


def test_brak_odleglosci_to_blad():
    with pytest.raises(ValueError, match="distance_km"):
        koleje_mazowieckie.estimate(_segment(None))


def test_zly_przewoznik_to_blad():
    seg = _segment(20)
    seg.carrier = Carrier.KOLEJE_MALOPOLSKIE
    with pytest.raises(ValueError, match="przewoźnik"):
        koleje_mazowieckie.estimate(seg)


def test_po_torach_to_oficjalna_taryfa_zweryfikowana():
    est = koleje_mazowieckie.estimate(_segment(95.08, po_torach=True, source="legGeometry MOTIS"))
    assert est.amount == 28.90
    assert est.price_type is PriceType.OFFICIAL
    assert est.breakdown["price_verified"] is True
    assert est.breakdown["zrodlo_url"] == URL
    assert est.breakdown["data_weryfikacji"] == "2026-10-13"
    assert est.breakdown["zrodlo_km"] == "legGeometry MOTIS"
    assert est.breakdown["cena_netto"] == 26.76 and est.breakdown["ptu"] == 2.14


def test_linia_prosta_to_szacunek_z_flaga_ale_kwota_zweryfikowana():
    est = koleje_mazowieckie.estimate(_segment(95.0))
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert "linii prostej" in est.notes


def test_ulga_daje_cene_normalna_niepotwierdzona():
    est = koleje_mazowieckie.estimate(_segment(95.0, ulga="student_do_26_lat_doktorant_do_35_lat", po_torach=True))
    assert est.amount == 28.90
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is False
    assert "nie są modelowane" in est.notes


def test_przez_kalkulator_ogolny():
    est = estimate_price(_segment(95.0, po_torach=True))
    assert est.carrier is Carrier.KOLEJE_MAZOWIECKIE


# --- routing -----------------------------------------------------------------------------------


@pytest.mark.parametrize("nazwa", ["Koleje Mazowieckie", "koleje  mazowieckie", "KM"])
def test_rozpoznanie_przewoznika(nazwa):
    assert pricing.infer_pl_local_rail_carrier(_leg(nazwa)) is Carrier.KOLEJE_MAZOWIECKIE


@pytest.mark.parametrize(
    "nazwa",
    ["WKD", "Warszawska Kolej Dojazdowa", "KMK", "Koleje Małopolskie", "KMŁ", "POLREGIO",
     "PKP Intercity", "SKM", "Łódzka Kolej Aglomeracyjna", "Koleje Śląskie"],
)  # fmt: skip
def test_inni_przewoznicy_nie_sa_km(nazwa):
    assert pricing.infer_pl_local_rail_carrier(_leg(nazwa)) is not Carrier.KOLEJE_MAZOWIECKIE


def test_autobus_km_nie_dostaje_tabeli():
    autobus = _leg(mode=LegMode.BUS, extra={"motis_mode": "BUS"})
    assert pricing.infer_pl_local_rail_carrier(autobus) is None


def test_suburban_km_dostaje_tabele():
    leg = _leg(mode=LegMode.BUS, extra={"motis_mode": "SUBURBAN"})
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.KOLEJE_MAZOWIECKIE


def test_wycena_odcinka_km_po_torach_z_motis():
    leg = _leg(
        "Koleje Mazowieckie",
        "Warszawa Wschodnia",
        "Siedlce",
        distance_km=88.0,
        extra={"distance_along_track_km": 95.08, "distance_along_track_source": "legGeometry"},
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MAZOWIECKIE
    assert priced.amount == 28.90
    assert priced.price_type == "oficjalna_taryfa"
    assert priced.price_verified is True


def test_wycena_odcinka_km_bez_km_po_torach_to_szacunek():
    leg = _leg(distance_km=88.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MAZOWIECKIE
    assert priced.amount == 26.50  # 81-90 km, linia prosta
    assert priced.price_type == "szacunek"


def test_powyzej_520_km_fallback_niepotwierdzony():
    leg = _leg(distance_km=600.0, extra={"distance_along_track_km": 600.0})
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_verified is False
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * 600.0, 2)
