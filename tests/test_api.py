"""Testy REST API (api/main.py) — mockują MOTIS na tym samym poziomie co tests/test_routing.py
(routing/variants.py::motis_client), bez wymagania działającego MOTIS ani sieci."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api.main import app
from routing import variants
from routing.model import Leg, LegMode
from routing.motis_client import MotisError

client = TestClient(app)


def _dt(hour, minute=0, day=5):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_route_endpoint_zwraca_wynik_dla_trasy_testowej_lublin_gelsenkirchen(monkeypatch):
    """Trasa testowa usera (Lublin -> Gelsenkirchen) przez cały stos HTTP: geocoding +
    routing MOTIS są mockowane (jak w tests/test_routing.py), ale request idzie przez
    prawdziwy endpoint FastAPI /route, więc to sprawdza cały łańcuch request -> response JSON."""

    def fake_geocode(text):
        if "lublin" in text.lower():
            return 51.23, 22.57, "Lublin Główny"
        return 51.52, 7.1, "Gelsenkirchen Hbf"

    monkeypatch.setattr(variants.motis_client, "geocode", fake_geocode)
    monkeypatch.setattr(variants.motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")

    rail_leg = Leg(
        mode=LegMode.RAIL,
        origin_name="Lublin Główny",
        destination_name="Gelsenkirchen Hbf",
        depart=_dt(6, 25),
        arrive=_dt(16, 0),
        carrier_name="PKP Intercity",
        distance_km=900.0,
        requires_walk=False,
    )
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **k: [[rail_leg]]
    )
    # Warianty via-hub/lot+kolej/lot-regionalny wymagają dodatkowych zapytań plan_leg —
    # w tym teście interesuje nas tylko główny wariant "tylko kolej", więc resztę pomijamy
    # (ląduje w SkippedVariant, nie przerywa budowania głównego wariantu).
    monkeypatch.setattr(
        variants.motis_client,
        "plan_leg",
        lambda *a, **k: (_ for _ in ()).throw(MotisError("brak połączenia (mock)")),
    )

    response = client.post(
        "/route",
        json={
            "origin": "Krakowskie Przedmieście 50, Lublin",
            "destination": "Bahnhofstraße, Gelsenkirchen",
            "date": "2026-10-05",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["origin_label"] == "Lublin Główny"
    assert body["destination_label"] == "Gelsenkirchen Hbf"
    assert len(body["built"]) >= 1
    assert body["built"][0]["legs"][0]["leg"]["carrier_name"] == "PKP Intercity"
    assert "najtansza" in body["recommendations"]
    assert "najszybsza" in body["recommendations"]


def test_route_endpoint_motis_error_zwraca_502(monkeypatch):
    def fake_geocode(text):
        raise MotisError("MOTIS nieosiągalny (mock)")

    monkeypatch.setattr(variants.motis_client, "geocode", fake_geocode)

    response = client.post(
        "/route",
        json={"origin": "Gdziekolwiek", "destination": "Gdzie indziej", "date": "2026-10-05"},
    )

    assert response.status_code == 502
    assert "MOTIS nieosiągalny" in response.json()["detail"]


def test_route_endpoint_nieobslugiwana_waluta_lotow_zwraca_422_a_nie_500(monkeypatch):
    """flight_currency=GBP: wcześniej ValueError z routing/currency.py wylatywał jako HTTP 500."""

    def must_not_be_called(*a, **k):
        raise AssertionError("walidacja waluty powinna zadziałać przed geokodowaniem")

    monkeypatch.setattr(variants.motis_client, "geocode", must_not_be_called)

    response = client.post(
        "/route",
        json={"origin": "A", "destination": "B", "date": "2026-10-05", "flight_currency": "GBP"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "flight_currency"]
    assert "GBP" in detail[0]["msg"]
    assert "EUR, PLN" in detail[0]["msg"]


def test_route_endpoint_przekazuje_walute_lotow_znormalizowana(monkeypatch):
    captured = {}

    def fake_request_from_addresses(origin_text, destination_text, date, **overrides):
        captured.update(overrides)
        return variants.RouteRequest(
            origin_stop_id="a",
            destination_stop_id="b",
            origin_label="A",
            destination_label="B",
            date=date,
            flight_currency=overrides["flight_currency"],
        )

    monkeypatch.setattr("api.main.request_from_addresses", fake_request_from_addresses)
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **k: [])

    response = client.post(
        "/route",
        json={"origin": "A", "destination": "B", "date": "2026-10-05", "flight_currency": "eur"},
    )

    assert response.status_code == 200
    assert captured["flight_currency"] == "EUR"


def test_route_endpoint_przekazuje_discounts_do_wyceny(monkeypatch):
    """BahnCard/ulga PKP z requestu trafiają do DiscountProfile użytego przy wycenie — sprawdzamy
    to przez request_from_addresses (routing/variants.py), wołane z api/main.py."""
    captured = {}

    def fake_request_from_addresses(origin_text, destination_text, date, **overrides):
        captured.update(overrides)
        return variants.RouteRequest(
            origin_stop_id="a",
            destination_stop_id="b",
            origin_label="A",
            destination_label="B",
            date=date,
            discounts=overrides.get("discounts"),
        )

    monkeypatch.setattr("api.main.request_from_addresses", fake_request_from_addresses)
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **k: [])

    response = client.post(
        "/route",
        json={
            "origin": "A",
            "destination": "B",
            "date": "2026-10-05",
            "discounts": {"bahncard": "50", "pkp_ulga_kod": "ulgowy"},
        },
    )

    assert response.status_code == 200
    assert captured["discounts"].bahncard == "50"
    assert captured["discounts"].pkp_ulga_kod == "ulgowy"
    assert response.json()["built"] == []
    assert response.json()["recommendations"] == {}


def test_attractions_endpoint():
    # Pobranie wszystkich atrakcji
    res = client.get("/attractions")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 15

    # Filtrowanie po mieście i kategorii sport
    res_berlin_sport = client.get("/attractions?city=Berlin&category=sport")
    assert res_berlin_sport.status_code == 200
    berlin_sports = res_berlin_sport.json()
    assert len(berlin_sports) >= 2
    assert all(a["city"] == "berlin" and a["category"] == "sport" for a in berlin_sports)


def test_city_cards_endpoint():
    res = client.get("/city-cards?city=Berlin")
    assert res.status_code == 200
    cards = res.json()
    assert len(cards) == 1
    assert cards[0]["id"] == "berlin_welcomecard"
    assert len(cards[0]["variants"]) >= 4


def test_city_cards_evaluate_endpoint():
    res = client.post(
        "/city-cards/evaluate",
        json={
            "city": "Berlin",
            "attraction_ids": ["berlin_fernsehturm", "berlin_olympiastadion", "berlin_museumsinsel"],
            "estimated_transit_cost": 20.0,
        },
    )
    assert res.status_code == 200
    evals = res.json()
    assert len(evals) >= 4
    # Fernsehturm/Olympiastadion mają zniżkę ze źródłem; Museumsinsel dla Classic to jawne 0%
    # (znany brak zniżki, kontrola krzyżowa 2026-10-12) -> bez flagi niezweryfikowanej zniżki.
    for e in evals:
        assert e["unverified_discount_attraction_ids"] == []


def test_city_cards_evaluate_unknown_city_returns_400():
    res = client.post(
        "/city-cards/evaluate",
        json={
            "city": "NowhereLand",
            "attraction_ids": [],
            "estimated_transit_cost": 0.0,
        },
    )
    assert res.status_code == 400
    assert "Nie rozpoznano obsługiwanego miasta" in res.json()["detail"]



def test_attractions_unknown_category_is_400():
    assert client.get("/attractions", params={"category": "zla"}).status_code == 400


def test_attractions_and_cards_unknown_city_is_400():
    assert client.get("/attractions", params={"city": "nieistnieje"}).status_code == 400
    assert client.get("/city-cards", params={"city": "nieistnieje"}).status_code == 400


def test_attractions_known_city_and_category_ok():
    r = client.get("/attractions", params={"city": "Berlin", "category": "turystyka_kultura"})
    assert r.status_code == 200 and r.json()
