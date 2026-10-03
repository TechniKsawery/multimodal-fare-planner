"""Wspólny punkt wejścia do wyszukiwania trasy: generate_variants() + pick_recommendations()
w jednym wywołaniu, ze standardowym zestawem hubów lot<->kolej i węzłów pośrednich z
routing/demo_route.py.

Używane przez app.py (Streamlit) i api/ (FastAPI), żeby obie "fasady" wołały identyczną logikę
routingu i taryf, a nie duplikowały tę samą sekwencję wywołań. demo.py (CLI) ma własne testy
patchujące generate_variants() wprost i zostaje bez zmian — to nie jest fasada do podłączenia
pod inny frontend/klienta, tylko skrypt demonstracyjny.
"""
from dataclasses import dataclass
from typing import Dict, List

from .demo_route import FLIGHT_REGIONAL_HUBS, RAIL_FLIGHT_RAIL_HUBS, VIA_HUB_STOPS
from .model import Itinerary, SkippedVariant
from .scoring import pick_recommendations
from .variants import RouteRequest, generate_variants


@dataclass
class SearchResult:
    request: RouteRequest
    built: List[Itinerary]
    skipped: List[SkippedVariant]
    recommendations: Dict[str, Itinerary]


def search(request: RouteRequest) -> SearchResult:
    """Generuje warianty dla `request` + rekomendacje, jeśli znalazł się choć jeden wykonalny
    wariant (recommendations == {} gdy built jest puste — pick_recommendations() na pustej
    liście podnosi błąd, więc wywołujący nie musi go łapać osobno).

    UWAGA: alternative_destination_stops celowo NIE jest tu przekazywane — dla zapytań
    adres->adres podmieniłoby rzeczywisty adres docelowy na sztywny dworzec (patrz
    routing/demo_route.py::ALTERNATIVE_DESTINATION_STOPS i demo.py).
    """
    built, skipped = generate_variants(
        request,
        rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
        flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
        via_hub_stops=VIA_HUB_STOPS,
    )
    recommendations = pick_recommendations(built) if built else {}
    return SearchResult(request=request, built=built, skipped=skipped, recommendations=recommendations)
