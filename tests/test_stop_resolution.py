"""Rozwiązywanie przystanków MOTIS po nazwie i współrzędnych (StopRef) zamiast zaszytych stopId.

Mockujemy /api/v1/geocode, więc testy nie wymagają uruchomionego MOTIS. Test z podmienionymi
ID symuluje świeżą paczkę GTFS (np. Gelsenkirchen Hbf z derv_344028 na defv_381192)."""

import pytest

from routing import demo_route, motis_client, variants
from routing.motis_client import MotisError, StopRef


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _czysty_cache():
    motis_client._STOP_ID_CACHE.clear()
    yield
    motis_client._STOP_ID_CACHE.clear()


def _fake_geocode(monkeypatch, results_by_text):
    """Podmienia /api/v1/geocode; zwraca listę zapytanych tekstów (do sprawdzenia cache)."""
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(params["text"])
        return FakeResponse(results_by_text.get(params["text"], []))

    monkeypatch.setattr(motis_client.requests, "get", fake_get)
    return calls


def _stop(id_, name, lat, lon):
    return {"type": "STOP", "id": id_, "name": name, "lat": lat, "lon": lon}


def _place(id_, name, lat, lon):
    return {"type": "PLACE", "id": id_, "name": name, "lat": lat, "lon": lon}


def test_find_stop_id_wybiera_najblizszy_przystanek_typu_stop(monkeypatch):
    ref = StopRef("Dortmund Hbf", 51.5172, 7.4595)
    _fake_geocode(
        monkeypatch,
        {
            "Dortmund Hbf": [
                _place("node/1", "Hauptbahnhof Dortmund", 51.5168, 7.4593),  # PLACE: pomijamy
                _stop("defv_999", "Dortmund Hbf (daleko)", 51.60, 7.20),  # STOP, ale 15 km
                _stop("defv_64583", "Dortmund Hbf", 51.5172, 7.4595),
            ]
        },
    )
    assert motis_client.find_stop_id(ref) == "defv_64583"


def test_find_stop_id_cache_nie_odpytuje_motis_drugi_raz(monkeypatch):
    ref = StopRef("Essen Hbf", 51.4515, 7.0131)
    calls = _fake_geocode(
        monkeypatch, {"Essen Hbf": [_stop("defv_351643", "Essen Hbf", 51.45, 7.01)]}
    )
    assert motis_client.find_stop_id(ref) == "defv_351643"
    assert motis_client.find_stop_id(ref) == "defv_351643"
    assert calls == ["Essen Hbf"]


def test_find_stop_id_brak_przystanku_w_promieniu_podnosi_blad(monkeypatch):
    ref = StopRef("Warszawa Lotnisko Chopina", 52.1657, 20.9671)
    _fake_geocode(monkeypatch, {"Warszawa Lotnisko Chopina": [_stop("pl_1", "Inny", 50.0, 19.0)]})
    with pytest.raises(MotisError):
        motis_client.find_stop_id(ref)


def test_stop_id_przepuszcza_stringi_bez_zapytania(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("string stopId nie powinien odpytywać MOTIS")

    monkeypatch.setattr(motis_client.requests, "get", boom)
    assert motis_client.stop_id("defv_1") == "defv_1"
    assert motis_client.stop_id("51.0,22.0") == "51.0,22.0"


def test_lublin_gelsenkirchen_request_uzywa_id_z_biezacej_paczki(monkeypatch):
    """Świeża paczka GTFS: Gelsenkirchen Hbf ma inne ID — kod nie wymaga zmian, bo ID
    jest rozwiązywane z nazwy i współrzędnych."""
    _fake_geocode(
        monkeypatch,
        {
            "Lublin Główny": [_stop("pl_50500", "Lublin Główny", 51.2314, 22.5692)],
            "Gelsenkirchen Hbf": [_stop("defv_381192", "Gelsenkirchen Hbf", 51.5049, 7.1022)],
        },
    )
    request = demo_route.lublin_gelsenkirchen_request("2026-10-09")
    assert request.origin_stop_id == "pl_50500"
    assert request.destination_stop_id == "defv_381192"


def test_hub_rozwiazuje_przystanki_przed_zapytaniem_do_plan(monkeypatch):
    """Huby z StopRef: zapytania do MOTIS /plan dostają ID z geocodingu, nie zaszyte."""
    _fake_geocode(
        monkeypatch,
        {
            "Warszawa Lotnisko Chopina": [_stop("pl_241994", "WAW", 52.1657, 20.9671)],
            "Dortmund Hbf": [_stop("defv_381000", "Dortmund Hbf", 51.5172, 7.4595)],
        },
    )
    hub = variants.HubConfig(
        label="test",
        origin_iata="WAW",
        destination_iata="DTM",
        origin_rail_access_stop_id=demo_route.WARSZAWA_LOTNISKO_CHOPINA_STOP,
        destination_rail_access_stop_id=demo_route.DORTMUND_HBF_STOP,
    )
    seen = []

    def fake_candidates(from_place, to_place, time, max_candidates=3):
        seen.append((from_place, to_place))
        raise MotisError("stop przechwycony")

    monkeypatch.setattr(motis_client, "plan_leg_candidates", fake_candidates)
    request = variants.RouteRequest(
        origin_stop_id="pl_50500",
        destination_stop_id="defv_381192",
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date="2026-10-09",
    )
    with pytest.raises(MotisError, match="stop przechwycony"):
        variants.build_rail_flight_rail_variant(request, hub)
    assert seen[0] == ("pl_50500", "pl_241994")
