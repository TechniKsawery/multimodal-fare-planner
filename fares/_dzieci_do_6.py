"""Bezpłatny przejazd dzieci poniżej 6 lat w lokalnym transporcie HVV/MVV/VRS/BVG/VRR.

Reguła wieku jest w `fares/data/<przewoźnik>.json::dzieci_ponizej_6_lat_bezplatnie` (źródło,
cytat, data weryfikacji). Wiek bierzemy z `DiscountProfile.age`; brak wieku = brak reguły.
"""

from .model import PriceEstimate, PriceType, Segment

WIEK_GRANICA = 6


def dziecko_ponizej_6(segment: Segment) -> bool:
    age = segment.discounts.age
    return age is not None and age < WIEK_GRANICA


def bezplatne_dziecko(segment: Segment, tabela: dict) -> PriceEstimate:
    regula = tabela["dzieci_ponizej_6_lat_bezplatnie"]
    return PriceEstimate(
        carrier=segment.carrier,
        amount=0.0,
        currency=tabela["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "bezpłatny (dziecko poniżej 6 lat)",
        },
        notes=f"Dziecko poniżej 6 lat jedzie bezpłatnie. Warunek: {regula['warunek']} "
        f"Źródło: {regula['zrodlo_url']} (zweryfikowano {regula['data_weryfikacji']}).",
    )
