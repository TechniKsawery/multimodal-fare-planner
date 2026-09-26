"""Agregacja odcinków w Itinerary i wybór czterech rekomendacji.

Metoda scoringu "najlepszy stosunek ceny do czasu": cena_pln / czas_w_godzinach (PLN/h),
niżej = lepiej. To jedna prosta, znormalizowana miara łącząca oba kryteria bez wag do
ręcznego ustawiania — patrz README.md po dłuższe wyjaśnienie i alternatywy.
"""
from typing import Dict, List

from .currency import to_pln
from .model import Itinerary, PricedLeg
from .transfers import check_all_transfers

RECOMMENDATION_LABELS = {
    "najtansza": "Najtańsza",
    "najszybsza": "Najszybsza",
    "najmniej_przesiadek": "Najmniej przesiadek",
    "najlepszy_stosunek_ceny_do_czasu": "Najlepszy stosunek cena/czas",
}


def build_itinerary(variant_name: str, priced_legs: List[PricedLeg]) -> Itinerary:
    if not priced_legs:
        raise ValueError(f"wariant '{variant_name}': brak odcinków")

    total_price_pln = sum(to_pln(pl.amount, pl.currency) for pl in priced_legs)
    total_duration_min = (
        priced_legs[-1].leg.arrive - priced_legs[0].leg.depart
    ).total_seconds() / 60
    legs_only = [pl.leg for pl in priced_legs]

    return Itinerary(
        variant_name=variant_name,
        legs=priced_legs,
        total_price_pln=round(total_price_pln, 2),
        total_duration_min=total_duration_min,
        num_transfers=len(priced_legs) - 1,
        transfer_warnings=check_all_transfers(legs_only),
    )


def pick_recommendations(itineraries: List[Itinerary]) -> Dict[str, Itinerary]:
    """Wybiera 4 rekomendacje z listy wariantów. Może się zdarzyć, że ten sam wariant wygra
    w kilku kategoriach naraz (np. jest jednocześnie najtańszy i najszybszy) — to nie błąd."""
    if not itineraries:
        raise ValueError("brak wariantów do wyboru rekomendacji")

    return {
        "najtansza": min(itineraries, key=lambda i: i.total_price_pln),
        "najszybsza": min(itineraries, key=lambda i: i.total_duration_min),
        "najmniej_przesiadek": min(itineraries, key=lambda i: i.num_transfers),
        "najlepszy_stosunek_ceny_do_czasu": min(itineraries, key=lambda i: i.price_per_hour),
    }
