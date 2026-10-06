"""Regresja na ŻYWYCH danych MOTIS dla trasy demo (Sesja 2026-10-09, pitch na żywo):
Skubiszewskiego 22, Lublin -> Buerer Straße 8, Gelsenkirchen.

W przeciwieństwie do tests/test_routing.py / tests/test_demo_route.py (unit testy z mockami),
te testy wymagają uruchomionego lokalnie MOTIS (patrz README.md) i naprawdę go odpytują — bez
tego cały moduł jest pomijany (patrz `_motis_reachable`), żeby reszta `pytest tests/` nie
wymagała Dockera.

Znane, zaakceptowane ograniczenie: defekt danych GTFS Berlin->Gelsenkirchen w oknie robót do
2026-10-09 (patrz pamięć projektu) może odrzucać/pomijać konkretne warianty wokół tej daty —
to jest oczekiwane i NIE jest tu łapane jako regresja, dopóki silnik nadal zwraca przynajmniej
jeden wykonalny wariant."""

import pytest
import requests

from fares.model import DiscountProfile
from routing import pricing
from routing.motis_client import MOTIS_BASE_URL
from routing.variants import generate_variants, request_from_addresses

DEMO_FROM = "Skubiszewskiego 22, Lublin"
DEMO_TO = "Buerer Straße 8, Gelsenkirchen"

# Pitch na żywo 2026-10-09 (patrz demo.py) — sprawdzamy kilka dni wokół, żeby złapać
# niespodzianki typu defekt danych GTFS tylko na konkretny dzień.
DEMO_DATES = ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11"]


def _motis_reachable() -> bool:
    try:
        requests.get(f"{MOTIS_BASE_URL}/api/v1/geocode", params={"text": "Lublin"}, timeout=3)
        return True
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(
    not _motis_reachable(), reason="wymaga lokalnie uruchomionego MOTIS (patrz README.md)"
)


@pytest.mark.parametrize("date", DEMO_DATES)
def test_demo_route_buduje_przynajmniej_jeden_wariant(date):
    """Dla każdej daty wokół pitchu silnik musi zwrócić przynajmniej jeden wykonalny wariant —
    bez wyjątku i bez pustej listy (nawet jeśli znany defekt GTFS Berlin->Gelsenkirchen
    pomija część wariantów w tym oknie)."""
    from routing.demo_route import FLIGHT_REGIONAL_HUBS, RAIL_FLIGHT_RAIL_HUBS, VIA_HUB_STOPS

    request = request_from_addresses(DEMO_FROM, DEMO_TO, date)
    built, skipped = generate_variants(
        request,
        rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
        flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
        via_hub_stops=VIA_HUB_STOPS,
    )

    assert (
        built
    ), f"Brak żadnego wykonalnego wariantu dla {date}; pominięte: {[s.reason for s in skipped]}"
    for itinerary in built:
        assert itinerary.total_price_pln > 0
        assert itinerary.total_duration_min > 0
        assert not itinerary.is_infeasible


@pytest.fixture(scope="module")
def demo_date_itineraries():
    """Jedno żywe zapytanie do MOTIS (data pitchu) — odcinki (Leg) ponownie wyceniane dla
    różnych DiscountProfile w testach poniżej, bez wielokrotnego odpytywania MOTIS."""
    from routing.demo_route import FLIGHT_REGIONAL_HUBS, RAIL_FLIGHT_RAIL_HUBS, VIA_HUB_STOPS

    request = request_from_addresses(DEMO_FROM, DEMO_TO, "2026-10-09")
    built, _skipped = generate_variants(
        request,
        rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
        flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
        via_hub_stops=VIA_HUB_STOPS,
    )
    assert built, "Brak wariantów dla daty pitchu 2026-10-09 — fixture wymaga przynajmniej jednego"
    return built


DISCOUNT_PROFILES = [
    ("brak_ulg", DiscountProfile()),
    ("pkp_student", DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat")),
    ("bahncard_25", DiscountProfile(bahncard="25")),
    ("bahncard_50", DiscountProfile(bahncard="50")),
    ("bahncard_100", DiscountProfile(bahncard="100")),
    (
        "pkp_student_i_bahncard_25",
        DiscountProfile(
            pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat",
            bahncard="25",
        ),
    ),
]


@pytest.mark.parametrize(
    "label, discounts", DISCOUNT_PROFILES, ids=[p[0] for p in DISCOUNT_PROFILES]
)
def test_wycena_dla_profilu_ulg_nie_wywala_sie_i_jest_sensowna(
    demo_date_itineraries, label, discounts
):
    """Dla każdego profilu ulg: ponowna wycena REALNYCH odcinków (z żywego MOTIS, data pitchu)
    nie podnosi wyjątku, a łączna cena wariantu jest dodatnia i w rozsądnym przedziale (nie
    ujemna, nie absurdalnie wysoka — górny próg dobrany z marginesem na warianty z lotem lub
    kilkoma FlixBusami w cenie EUR)."""
    for itinerary in demo_date_itineraries:
        raw_legs = [pl.leg for pl in itinerary.legs]
        repriced = [pricing.price_leg(leg, discounts, "PLN") for leg in raw_legs]

        for priced in repriced:
            assert (
                priced.amount >= 0
            ), f"[{label}] ujemna cena odcinka {priced.leg.origin_name}->{priced.leg.destination_name}"
            assert (
                priced.amount < 5000
            ), f"[{label}] absurdalnie wysoka cena odcinka: {priced.amount} {priced.currency}"

        total_pln = sum(
            (
                p.amount if p.currency == "PLN" else p.amount * 4.5
            )  # górny szacunek kursu, tylko do sanity-check
            for p in repriced
        )
        assert total_pln > 0
        assert (
            total_pln < 20000
        ), f"[{label}] absurdalnie wysoka cena całkowita wariantu: {total_pln}"


def test_bahncard_100_nie_jest_drozsza_niz_brak_ulgi_na_odcinkach_db(demo_date_itineraries):
    """BahnCard 100 (100% rabatu na Flexpreis DB) nie może dać WYŻSZEJ ceny niż bez żadnej karty
    na tym samym odcinku DB — podstawowa spójność silnika rabatów."""
    from fares.model import Carrier
    from routing.pricing import infer_rail_carrier, is_cross_border_pl_de

    found_db_leg = False
    for itinerary in demo_date_itineraries:
        for pl in itinerary.legs:
            leg = pl.leg
            if infer_rail_carrier(leg.carrier_name) is not Carrier.DB or is_cross_border_pl_de(leg):
                continue
            found_db_leg = True
            bez_ulgi = pricing.price_leg(leg, DiscountProfile(), "PLN")
            z_bahncard_100 = pricing.price_leg(leg, DiscountProfile(bahncard="100"), "PLN")
            assert z_bahncard_100.amount <= bez_ulgi.amount

    if not found_db_leg:
        pytest.skip("żaden zbudowany wariant dla daty pitchu nie zawiera odcinka DB Fernverkehr")
