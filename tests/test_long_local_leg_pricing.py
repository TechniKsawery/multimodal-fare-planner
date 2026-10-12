"""Regresje: ryczałt LOCAL_BUS_FLAT_PLN (4 PLN) tylko dla KRÓTKICH odcinków.

Test na żywo MOTIS (Szczecin -> Berlin, 2026-10-17, PR #98): feed oznaczył odcinek
SKM Dworzec Główny -> Angermünde (linia RB66, 58,2 km, ok. 115 min) jako BUS (motis_mode BUS,
przewoźnik "Nahreisezug"), więc gałąź SUBURBAN z PR #98 się nie uruchomiła, a nieznany
operator lokalny dostał płaski ryczałt 4 PLN za 58 km. Teraz odcinek dłuższy niż
LOCAL_BUS_MAX_KM idzie na niepotwierdzony szacunek PLN/km. Nie wiemy, czy to pociąg, czy
komunikacja zastępcza, więc nie zgadujemy trybu."""

from datetime import datetime, timedelta

import pytest

from fares.model import Carrier, DiscountProfile
from routing import motis_client, pricing
from routing.model import Leg, LegMode

DEPART = datetime(2026, 10, 17, 8, 0)


def _rb66_leg() -> Leg:
    """Dokładnie odcinek ze zrzutu na żywo (współrzędnych feed w zrzucie nie pokazał)."""
    return Leg(
        mode=LegMode.BUS,
        origin_name="SKM Dworzec Glowny (PL) Kolumba, Polen",
        destination_name="Angermünde, Bahnhof",
        depart=DEPART,
        arrive=DEPART + timedelta(minutes=115),
        carrier_name="Nahreisezug",
        distance_km=58.2,
        extra={
            "motis_mode": "BUS",
            "route_short_name": "RB66",
            "origin_stop_id": "denv_413683",
            "destination_stop_id": "denv_452999",
        },
    )


def _local_leg(
    distance_km, *, route=None, carrier="Nieznany Przewoźnik", motis_mode="BUS", xy=None
):
    extra = {"motis_mode": motis_mode}
    if route:
        extra["route_short_name"] = route
    if xy:
        extra.update(
            origin_lat=xy[0][0],
            origin_lon=xy[0][1],
            destination_lat=xy[1][0],
            destination_lon=xy[1][1],
        )
    return Leg(
        mode=LegMode.BUS,
        origin_name="Przystanek A",
        destination_name="Przystanek B",
        depart=DEPART,
        arrive=DEPART + timedelta(minutes=30),
        carrier_name=carrier,
        distance_km=distance_km,
        extra=extra,
    )


# --- dokładny obiekt ze zrzutu na żywo ------------------------------------------------------


def test_rb66_z_zrzutu_na_zywo_dostaje_szacunek_za_km_nie_ryczalt():
    priced = pricing.price_bus_leg(_rb66_leg())

    assert priced.amount != pricing.LOCAL_BUS_FLAT_PLN
    assert priced.amount != 4.0
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * 58.2, 2) == 20.37
    assert priced.currency == "PLN"
    assert priced.price_type == "szacunek"
    assert priced.price_type != "oficjalna_taryfa"
    assert priced.price_verified is False
    assert priced.breakdown["price_verified"] is False
    assert "wartosc_zastepcza" not in priced.breakdown
    assert priced.breakdown["powod_szacunku"] == "odcinek za długi na ryczałt lokalny"
    assert priced.unverified_label == "cena niepotwierdzona"
    assert "cena niepotwierdzona" in priced.notes
    assert priced.carrier is None


def test_rb66_przez_price_leg_to_ta_sama_sciezka():
    priced = pricing.price_leg(_rb66_leg(), DiscountProfile())
    assert priced.amount == 20.37
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"


def test_rb66_sygnal_linii_tylko_w_opisie_nie_w_cenie_ani_trybie():
    leg = _rb66_leg()
    priced = pricing.price_bus_leg(leg)
    assert pricing.is_train_like_line(leg)
    assert "RB66" in priced.breakdown["sygnal_linii"]
    assert "pociąg" in priced.notes and "niepotwierdzon" in priced.notes
    assert leg.mode is LegMode.BUS and leg.extra["motis_mode"] == "BUS"  # tryb bez zmian
    assert "tryb_motis" not in priced.breakdown  # to nie ścieżka SUBURBAN


def test_ta_sama_dlugosc_bez_linii_kolejowej_tez_szacunek_ale_bez_sygnalu():
    priced = pricing.price_bus_leg(_local_leg(58.2, route="N66"))
    assert priced.amount == 20.37
    assert priced.price_verified is False
    assert "sygnal_linii" not in priced.breakdown
    assert "sugeruje pociąg" not in priced.notes


@pytest.mark.parametrize(
    "route", ["RB66", "RE1", "IRE 1", "S1", "S 7", "SKM", "PKM", "rb12", "RS3"]
)
def test_oznaczenia_linii_kolejowych(route):
    assert pricing.is_train_like_line(_local_leg(30.0, route=route))


@pytest.mark.parametrize("route", [None, "", "N66", "52", "175", "T1", "A", "Bus 5", "SB66", "RBX"])
def test_oznaczenia_nie_kolejowe(route):
    assert not pricing.is_train_like_line(_local_leg(30.0, route=route))


# --- próg: wyprowadzony z CITY_TARIFF_AREAS, testy graniczne --------------------------------


def test_prog_to_najwiekszy_promien_kola_taryfy_miejskiej():
    assert max(r for _a, _b, r in pricing.CITY_TARIFF_AREAS.values()) == pricing.LOCAL_BUS_MAX_KM
    assert pricing.LOCAL_BUS_MAX_KM == 20.0  # Berlin (BVG)
    assert pricing.LOCAL_BUS_MAX_KM < 58.2  # RB66 jest wyraźnie ponad progiem


@pytest.mark.parametrize("km", [0.5, 3.0, 19.9, 20.0])
def test_do_progu_wlacznie_ryczalt_z_flaga_wartosci_zastepczej(km):
    priced = pricing.price_bus_leg(_local_leg(km))
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
    assert priced.price_type == "szacunek"
    assert priced.price_verified is False
    assert priced.breakdown["wartosc_zastepcza"] is True
    assert priced.breakdown["powod_szacunku"] == "nieznany operator lokalny"
    assert priced.unverified_label == "cena niepotwierdzona (wartość zastępcza, nie z cennika)"


@pytest.mark.parametrize("km", [20.01, 20.1, 21.0, 58.2, 150.0])
def test_powyzej_progu_szacunek_za_km_bez_wartosci_zastepczej(km):
    priced = pricing.price_bus_leg(_local_leg(km))
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * km, 2)
    assert priced.price_type == "szacunek"
    assert priced.price_verified is False
    assert "wartosc_zastepcza" not in priced.breakdown
    assert priced.breakdown["powod_szacunku"] == "odcinek za długi na ryczałt lokalny"
    assert priced.breakdown["prog_ryczaltu_km"] == pricing.LOCAL_BUS_MAX_KM
    assert priced.unverified_label == "cena niepotwierdzona"


def test_krotki_lokalny_autobus_3_km_nadal_ryczalt():
    priced = pricing.price_bus_leg(_local_leg(3.0, route="175"))
    assert priced.amount == 4.0
    assert priced.breakdown["wartosc_zastepcza"] is True
    assert priced.price_verified is False


def test_krotki_odcinek_z_linia_rb_nadal_ryczalt_sygnal_nie_zmienia_ceny():
    priced = pricing.price_bus_leg(_local_leg(3.0, route="RB66"))
    assert priced.amount == 4.0
    assert priced.breakdown["wartosc_zastepcza"] is True


def test_brak_dystansu_nie_dowodzi_ze_odcinek_dlugi_zostaje_ryczalt():
    priced = pricing.price_bus_leg(_local_leg(None))
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
    assert priced.breakdown["wartosc_zastepcza"] is True


# --- nic nie psuje innych taryf --------------------------------------------------------------


def test_taryfa_miejska_ma_pierwszenstwo_przed_progiem():
    # Berlin: 18 km w kole BVG (< 20 km) i 25 km (> progu, ale oba końce w kole 20 km od centrum,
    # np. Spandau -> Köpenick) nadal dostają bilet BVG, nie szacunek PLN/km.
    for xy in (((52.5200, 13.4050), (52.4300, 13.5900)), ((52.5350, 13.1990), (52.4450, 13.5760))):
        leg = _local_leg(motis_client.haversine_km(*xy[0], *xy[1]), carrier="BVG", xy=xy)
        priced = pricing.price_bus_leg(leg)
        assert priced.carrier is Carrier.BVG_BERLIN
        assert priced.price_type == "oficjalna_taryfa"
        assert priced.price_verified is True


def test_nrw_dalej_eezy_nrw_nawet_powyzej_progu():
    xy = ((51.2200, 6.7940), (51.5100, 7.4600))  # Düsseldorf -> Dortmund, ponad 50 km
    leg = _local_leg(motis_client.haversine_km(*xy[0], *xy[1]), carrier="Bus NRW", xy=xy)
    assert leg.distance_km > pricing.LOCAL_BUS_MAX_KM
    priced = pricing.price_bus_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.VRR
    assert priced.price_verified is True


def test_suburban_nadal_wlasna_sciezka_nawet_krotki():
    priced = pricing.price_bus_leg(_local_leg(5.0, motis_mode="SUBURBAN", carrier="SKM"))
    assert priced.breakdown["tryb_motis"] == "SUBURBAN"
    assert "wartosc_zastepcza" not in priced.breakdown


def test_flixbus_nie_idzie_przez_prog(monkeypatch):
    from fares import _flixbus_api
    from fares.flixbus import _FALLBACK

    def boom(*a, **kw):
        raise _flixbus_api.FlixbusApiError("brak sieci (test)")

    monkeypatch.setattr(_flixbus_api, "find_city_id", boom)
    priced = pricing.price_bus_leg(_local_leg(300.0, carrier="FlixBus", motis_mode="COACH"))
    assert priced.amount == pytest.approx(300 * _FALLBACK["pln_per_km"])
    assert priced.breakdown.get("powod_szacunku") != pricing.LONG_LOCAL_LEG_REASON
    assert "wartosc_zastepcza" not in priced.breakdown


def test_inny_autokar_dalekobiezny_nie_idzie_przez_prog():
    priced = pricing.price_bus_leg(_local_leg(300.0, carrier="RegioJet", motis_mode="COACH"))
    assert priced.breakdown["powod_szacunku"] != pricing.LONG_LOCAL_LEG_REASON
