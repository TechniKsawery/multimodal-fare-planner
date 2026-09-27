"""Sugestia BahnCard dla konkretnego wariantu trasy (Itinerary) — łączy fares/cards.py z
odcinkami kolejowymi DB w wariancie, żeby demo.py/app.py mogły pokazać "kup kartę, zaoszczędzisz X"
bez ręcznego wyciągania dystansu DB przez wywołującego."""
from typing import List, Optional

from fares.cards import CardSuggestion, suggest_bahncard
from fares.model import Carrier

from .model import Itinerary, LegMode
from .pricing import infer_rail_carrier


def db_distance_km(itinerary: Itinerary) -> float:
    """Suma dystansów odcinków DB Fernverkehr (Flexpreis) w wariancie — 0, jeśli wariant nie
    zawiera żadnego odcinka DB (np. sama kolej PL, sam FlixBus, sam lot)."""
    return sum(
        pl.leg.distance_km or 0.0
        for pl in itinerary.legs
        if pl.leg.mode is LegMode.RAIL and infer_rail_carrier(pl.leg.carrier_name) is Carrier.DB
    )


def suggest_bahncard_for_itinerary(
    itinerary: Itinerary, age: Optional[int] = None, journeys_per_year: int = 2,
) -> List[CardSuggestion]:
    """Sugestie BahnCard dla odcinków DB w tym wariancie. Pusta lista, jeśli wariant nie ma
    żadnego odcinka DB Fernverkehr (BahnCard obniża tylko Flexpreis DB, nie inne przewoźniki)."""
    distance = db_distance_km(itinerary)
    if distance <= 0:
        return []
    return suggest_bahncard(distance, journeys_per_year=journeys_per_year, age=age)
