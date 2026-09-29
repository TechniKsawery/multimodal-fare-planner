"""Sugestia BahnCard dla konkretnego wariantu trasy (Itinerary) — łączy fares/cards.py z
odcinkami kolejowymi DB w wariancie, żeby demo.py/app.py mogły pokazać "kup kartę, zaoszczędzisz X"
bez ręcznego wyciągania dystansu DB przez wywołującego."""
from typing import List, Optional

from fares.cards import CardSuggestion, suggest_bahncard_for_total_price
from fares.db import flexpreis_upper_bound
from fares.model import Carrier

from .model import Itinerary, LegMode
from .pricing import infer_rail_carrier


def _db_legs(itinerary: Itinerary):
    return [
        pl for pl in itinerary.legs
        if pl.leg.mode is LegMode.RAIL and infer_rail_carrier(pl.leg.carrier_name) is Carrier.DB
    ]


def db_distance_km(itinerary: Itinerary) -> float:
    """Suma dystansów odcinków DB Fernverkehr (Flexpreis) w wariancie — 0, jeśli wariant nie
    zawiera żadnego odcinka DB (np. sama kolej PL, sam FlixBus, sam lot). Używane TYLKO do
    sprawdzenia, czy wariant w ogóle zawiera DB — do liczenia ceny patrz
    db_flexpreis_upper_bound_total() (suma dystansów nie jest tu poprawną podstawą ceny, bo
    pasma Flexpreis są nieliniowe)."""
    return sum(
        pl.leg.distance_km or 0.0
        for pl in _db_legs(itinerary)
    )


def db_flexpreis_upper_bound_total(itinerary: Itinerary) -> float:
    """Suma cen Flexpreis (bez karty) POSZCZEGÓLNYCH biletów DB w wariancie — każdy bilet
    liczony ze swojego własnego pasma odległości, tak jak realnie jest sprzedawany (patrz
    routing/pricing.py::price_rail_leg, gdzie każdy odcinek DB ma osobny bilet). Zbanowanie
    SUMY dystansów jako jednego "megaodcinka" (poprzedni, błędny sposób) zaniżało łączną cenę,
    bo pasma Flexpreis są płaskie powyżej ok. 600 km — dwa bilety po 131 EUR i 80 EUR (razem
    211 EUR) dawały błędnie zsumowany dystans wpadający w pasmo 600-800 km = 182 EUR."""
    return round(sum(
        flexpreis_upper_bound(pl.leg.distance_km)
        for pl in _db_legs(itinerary)
        if pl.leg.distance_km and pl.leg.distance_km > 0
    ), 2)


def suggest_bahncard_for_itinerary(
    itinerary: Itinerary,
    age: Optional[int] = None,
    journeys_per_year: int = 2,
    existing_bahncard: Optional[str] = None,
) -> List[CardSuggestion]:
    """Sugestie BahnCard dla odcinków DB w tym wariancie. Pusta lista, jeśli wariant nie ma
    żadnego odcinka DB Fernverkehr (BahnCard obniża tylko Flexpreis DB, nie inne przewoźniki),
    albo jeśli user już ma kartę z rabatem równym lub lepszym niż każdy dostępny wariant.

    existing_bahncard: karta już zadeklarowana przez usera w formularzu ("25"/"50"/"100"/None) —
    przekazywana dalej, żeby nie sugerować kupna karty, którą user już ma."""
    total_upper_bound = db_flexpreis_upper_bound_total(itinerary)
    if total_upper_bound <= 0:
        return []
    return suggest_bahncard_for_total_price(
        total_upper_bound, journeys_per_year=journeys_per_year, age=age, existing_bahncard=existing_bahncard,
    )
