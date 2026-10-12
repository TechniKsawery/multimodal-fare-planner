"""Limit objazdu dla wariantu "Kolej przez <węzeł>" (VIA_HUB_STOPS, dziś Poznań Główny).

Regresja z testu na żywo: Kraków -> Gorlice (MOTIS bez bezpośredniej trasy) budował
Kraków -> Wrocław -> Poznań -> Wrocław -> Tarnów -> Stróże -> Gorlice (32 h, 5 przesiadek).
Próg VIA_HUB_MAX_DETOUR_RATIO i jego uzasadnienie: routing/variants.py. Współrzędne miast są
przybliżone (centra, do ok. 0,01°) — wystarczą do ratio, nie są danymi rozkładowymi."""

from datetime import UTC, datetime, timedelta

import pytest

from routing import motis_client, variants
from routing.demo_route import VIA_HUB_STOPS
from routing.model import Leg, LegMode, PricedLeg
from routing.motis_client import MotisError

KRAKOW = (50.0647, 19.9450)
GORLICE = (49.6553, 21.1597)
POZNAN = (52.4019, 16.9125)
WROCLAW = (51.0985, 17.0366)
TARNOW = (50.0121, 20.9858)
STROZE = (49.7500, 21.1000)
LUBLIN = (51.2465, 22.5684)
BERLIN = (52.5251, 13.3694)
SZCZECIN = (53.4285, 14.5528)
WARSZAWA = (52.2289, 21.0033)
GELSENKIRCHEN = (51.5049, 7.1022)
ZIELONA_GORA = (51.9356, 15.5062)


def _coords(xy):
    return f"{xy[0]},{xy[1]}"


# --- 1) Próg: testy graniczne i korytarze --------------------------------------------------


def test_prog_to_1_5():
    # jedyne miejsce, w którym próg jest zapisany liczbą; reszta testów liczy od stałej
    assert variants.VIA_HUB_MAX_DETOUR_RATIO == 1.5


@pytest.mark.parametrize(
    "via_lat, odrzucony",
    [
        (51.0 + 0.2500 - 0.0001, False),  # tuż pod progiem: path/direct = 1.4998
        (51.0 + 0.2500 + 0.0001, True),  # tuż nad progiem: path/direct = 1.5002
    ],
)
def test_granica_progu_na_poludniku(via_lat, odrzucony):
    """Punkty na jednym południku: origin (50,20), cel (51,20), węzeł za celem na (51+x,20).
    Wtedy origin->via + via->cel = (1 + 2x)° łuku, a bezpośrednio 1° — ratio = 1 + 2x, więc
    x = 0,25 daje dokładnie 1.5 (bez zależności od zaokrągleń haversine, bo testujemy ±0,0001°)."""
    reason = variants.via_hub_detour_reason((50.0, 20.0), (via_lat, 20.0), (51.0, 20.0))
    assert (reason is not None) is odrzucony
    if odrzucony:
        assert "objazd" in reason and "1.5x" in reason


def test_wezel_na_prostej_origin_cel_nie_jest_objazdem():
    assert variants.via_hub_detour_reason((50.0, 20.0), (50.5, 20.0), (51.0, 20.0)) is None


@pytest.mark.parametrize(
    "origin, destination",
    [
        (LUBLIN, BERLIN),  # 1.00 — Poznań leży po drodze
        (LUBLIN, GELSENKIRCHEN),  # 1.02 — korytarz, pod który dodano VIA_HUB_STOPS
        (WARSZAWA, BERLIN),  # 1.00
        (KRAKOW, BERLIN),  # 1.08
    ],
)
def test_poznan_po_drodze_zostaje(origin, destination):
    assert variants.via_hub_detour_reason(origin, POZNAN, destination) is None


@pytest.mark.parametrize(
    "origin, destination",
    [
        (KRAKOW, GORLICE),  # 7.74 — przypadek z testu na żywo
        (SZCZECIN, BERLIN),  # 3.40
        (ZIELONA_GORA, BERLIN),  # 2.19
        (KRAKOW, WARSZAWA),  # 2.44
    ],
)
def test_poznan_nie_po_drodze_odpada(origin, destination):
    reason = variants.via_hub_detour_reason(origin, POZNAN, destination)
    assert reason is not None and reason.startswith("Pominięty: objazd")


def test_brak_wspolrzednych_nie_filtruje():
    assert variants.via_hub_detour_reason(None, POZNAN, BERLIN) is None
    assert variants.via_hub_detour_reason(LUBLIN, None, BERLIN) is None
    assert variants.via_hub_detour_reason(LUBLIN, POZNAN, None) is None


# --- 2) Powrót tą samą stacją --------------------------------------------------------------


def _leg(origin, destination, origin_xy=None, destination_xy=None, *, mode=LegMode.RAIL, hour=6):
    depart = datetime(2026, 10, 20, hour, 0, tzinfo=UTC)
    extra = {}
    if origin_xy and destination_xy:
        extra = dict(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(hours=2),
        carrier_name="X",
        distance_km=100.0,
        extra=extra,
    )


def _objazd_krakow_gorlice():
    return [
        _leg("Kraków Główny", "Wrocław Główny", KRAKOW, WROCLAW, hour=6),
        _leg("Wrocław Główny", "Poznań Główny", WROCLAW, POZNAN, hour=9),
        _leg("Poznań Główny", "Wrocław Główny", POZNAN, WROCLAW, hour=12),
        _leg("Wrocław Główny", "Tarnów", WROCLAW, TARNOW, hour=15),
        _leg("Tarnów", "Stróże", TARNOW, STROZE, hour=18),
        _leg("Stróże", "Gorlice", STROZE, GORLICE, hour=20),
    ]


def test_powrot_przez_wroclaw_odpada():
    reason = variants.revisited_station_reason(_objazd_krakow_gorlice())
    assert reason is not None and "Wrocław Główny" in reason and "dwa razy" in reason


def test_ta_sama_stacja_ze_wspolrzednymi_o_200_m_to_nadal_powrot():
    legs = _objazd_krakow_gorlice()
    blisko = (WROCLAW[0] + 0.0018, WROCLAW[1])  # ok. 200 m
    assert motis_client.haversine_km(*WROCLAW, *blisko) < variants.SAME_STATION_RADIUS_KM
    legs[3] = _leg("Wrocław Gł.", "Tarnów", blisko, TARNOW, hour=15)
    assert variants.revisited_station_reason(legs) is not None


def test_bez_wspolrzednych_powrot_wykrywany_po_nazwie():
    legs = [
        _leg("Kraków", "Wrocław"),
        _leg("Wrocław", "Poznań"),
        _leg("Poznań", " wrocław "),
    ]
    assert variants.revisited_station_reason(legs) is not None


def test_przesiadka_w_jednym_miejscu_to_nie_powrot():
    legs = [
        _leg("Lublin", "Warszawa Centralna", LUBLIN, WARSZAWA, hour=6),
        _leg("Warszawa Centralna", "Poznań Główny", WARSZAWA, POZNAN, hour=9),
        _leg("Poznań Główny", "Berlin Hbf", POZNAN, BERLIN, hour=12),
    ]
    assert variants.revisited_station_reason(legs) is None


def test_dwa_dworce_w_jednym_miescie_to_nie_powrot():
    berlin_ostbahnhof = (52.5103, 13.4344)  # ok. 5 km od Hbf
    legs = [
        _leg("Poznań Główny", "Berlin Ostbahnhof", POZNAN, berlin_ostbahnhof, hour=6),
        _leg("Berlin Hbf", "Gelsenkirchen Hbf", BERLIN, GELSENKIRCHEN, hour=10),
    ]
    assert variants.revisited_station_reason(legs) is None


def test_dojscia_piesze_nie_licza_sie_do_powrotu():
    legs = [
        _leg("start", "Kraków Główny", mode=LegMode.WALK),
        _leg("Kraków Główny", "Poznań Główny", KRAKOW, POZNAN, hour=7),
        _leg("Poznań Główny", "cel", mode=LegMode.WALK, hour=11),
    ]
    assert variants.revisited_station_reason(legs) is None


def test_same_walk_albo_pusta_trasa_bez_bledu():
    assert variants.revisited_station_reason([]) is None
    assert variants.revisited_station_reason([_leg("a", "b", mode=LegMode.WALK)]) is None


# --- 3) generate_variants: Kraków -> Gorlice trafia do skipped ------------------------------


def _flat_price(monkeypatch):
    monkeypatch.setattr(
        variants.pricing,
        "price_leg",
        lambda leg, discounts, currency="PLN": PricedLeg(leg, 10.0, "PLN", "szacunek"),
    )


def _request(origin_id, destination_id, origin_label, destination_label):
    return variants.RouteRequest(
        origin_stop_id=origin_id,
        destination_stop_id=destination_id,
        origin_label=origin_label,
        destination_label=destination_label,
        date="2026-10-20",
    )


def _no_direct_route(monkeypatch):
    def brak(*a, **kw):
        raise MotisError("Brak połączenia (test).")

    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", brak)
    monkeypatch.setattr(variants.motis_client, "stop_id", lambda value: "poznan_glowny")


def test_krakow_gorlice_ze_wspolrzednymi_nie_buduje_objazdu_i_nie_pyta_motis(monkeypatch):
    _no_direct_route(monkeypatch)
    _flat_price(monkeypatch)
    calls = []
    monkeypatch.setattr(variants.motis_client, "plan_leg", lambda *a, **kw: calls.append(a) or [])
    request = _request(_coords(KRAKOW), _coords(GORLICE), "Kraków", "Gorlice")

    built, skipped = variants.generate_variants(request, via_hub_stops=VIA_HUB_STOPS)

    assert built == []
    assert calls == []  # odrzucone na współrzędnych, zanim poszło jakiekolwiek zapytanie
    via = next(s for s in skipped if s.variant_name == "Kolej przez Poznań Główny")
    assert "objazd" in via.reason and "km w linii prostej" in via.reason


def test_krakow_gorlice_ze_stopid_odrzucony_po_zbudowaniu_odcinkow(monkeypatch):
    """Zapytanie z samymi stopId MOTIS (bez współrzędnych): objazd wychodzi dopiero ze
    współrzędnych odcinków — ten sam 32-godzinny przejazd, który użytkownik widział na żywo."""
    _no_direct_route(monkeypatch)
    _flat_price(monkeypatch)
    objazd = _objazd_krakow_gorlice()
    do_poznania, z_poznania = objazd[:2], objazd[2:]

    def plan_leg(origin, destination, time, **kw):
        return do_poznania if destination == "poznan_glowny" else z_poznania

    monkeypatch.setattr(variants.motis_client, "plan_leg", plan_leg)
    request = _request("krakow_glowny", "gorlice", "Kraków", "Gorlice")

    built, skipped = variants.generate_variants(request, via_hub_stops=VIA_HUB_STOPS)

    assert built == []
    via = next(s for s in skipped if s.variant_name == "Kolej przez Poznań Główny")
    assert via.reason.startswith("Pominięty: objazd")


def test_objazd_z_powrotem_ta_sama_stacja_odpada_nawet_gdy_ratio_przechodzi(monkeypatch):
    """Lublin -> Berlin przez Poznań ma ratio 1.00, ale gdyby trasa wracała przez tę samą stację
    (Poznań -> Warszawa -> Poznań), i tak odpada jako powrót."""
    _no_direct_route(monkeypatch)
    _flat_price(monkeypatch)
    do_poznania = [
        _leg("Lublin", "Warszawa Centralna", LUBLIN, WARSZAWA, hour=6),
        _leg("Warszawa Centralna", "Poznań Główny", WARSZAWA, POZNAN, hour=9),
        _leg("Poznań Główny", "Warszawa Centralna", POZNAN, WARSZAWA, hour=12),
    ]
    z_poznania = [_leg("Warszawa Centralna", "Berlin Hbf", WARSZAWA, BERLIN, hour=16)]

    monkeypatch.setattr(
        variants.motis_client,
        "plan_leg",
        lambda origin, destination, time, **kw: (
            do_poznania if destination == "poznan_glowny" else z_poznania
        ),
    )
    request = _request(_coords(LUBLIN), _coords(BERLIN), "Lublin", "Berlin")

    built, skipped = variants.generate_variants(request, via_hub_stops=VIA_HUB_STOPS)

    assert built == []
    via = next(s for s in skipped if s.variant_name == "Kolej przez Poznań Główny")
    assert "Warszawa Centralna" in via.reason and "dwa razy" in via.reason


def test_lublin_berlin_przez_poznan_nadal_sie_buduje(monkeypatch):
    """Poznań po drodze Lublin -> Berlin nie może zostać wycięty przez nowy limit."""
    _no_direct_route(monkeypatch)
    _flat_price(monkeypatch)
    do_poznania = [_leg("Lublin", "Poznań Główny", LUBLIN, POZNAN, hour=6)]
    z_poznania = [_leg("Poznań Główny", "Berlin Hbf", POZNAN, BERLIN, hour=14)]
    monkeypatch.setattr(
        variants.motis_client,
        "plan_leg",
        lambda origin, destination, time, **kw: (
            do_poznania if destination == "poznan_glowny" else z_poznania
        ),
    )
    request = _request(_coords(LUBLIN), _coords(BERLIN), "Lublin", "Berlin")

    built, skipped = variants.generate_variants(request, via_hub_stops=VIA_HUB_STOPS)

    assert [i.variant_name for i in built] == ["Kolej przez Poznań Główny"]
    assert not [s for s in skipped if "Poznań" in s.variant_name]


def test_szczecin_berlin_ze_wspolrzednymi_odrzuca_poznan_przed_zapytaniem(monkeypatch):
    _no_direct_route(monkeypatch)
    _flat_price(monkeypatch)
    calls = []
    monkeypatch.setattr(variants.motis_client, "plan_leg", lambda *a, **kw: calls.append(a) or [])
    request = _request(_coords(SZCZECIN), _coords(BERLIN), "Szczecin", "Berlin")

    built, skipped = variants.generate_variants(request, via_hub_stops=VIA_HUB_STOPS)

    assert built == [] and calls == []
    assert any("objazd" in s.reason for s in skipped)


def _empty_rail_request():
    from routing.variants import RouteRequest

    return RouteRequest(
        origin_stop_id="a", destination_stop_id="b", origin_label="A", destination_label="B",
        date="2026-10-17",
    )


def test_pusty_wynik_motis_ma_jawny_powod(monkeypatch):
    from routing import motis_client, variants

    monkeypatch.setattr(motis_client, "all_itineraries_as_legs", lambda *a, **k: [])
    built, skipped = variants.generate_variants(_empty_rail_request())
    assert built == []
    reason = next(s.reason for s in skipped if s.variant_name == "Tylko kolej")
    assert "nie zwrócił żadnego połączenia" in reason
