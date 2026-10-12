"""Wycena segmentu FlixBus: REALNA cena z (nieoficjalnego, publicznego) API FlixBusa dla
konkretnej daty przejazdu (patrz fares/_flixbus_api.py), z fallbackiem do zgrubnego szacunku
PLN/km gdy API jest niedostępne (np. sieć środowiska Claude blokuje global.api.flixbus.com —
patrz README.md) albo nie zwróciło wyniku dla danej relacji/daty.

Cena z API i cena z fallbacku są OBIE oznaczone jako PriceType.ESTIMATE ("szacunek") — tak samo
jak ceny lotów z Travelpayouts w flights/ — bo FlixBus, podobnie jak linie lotnicze, nie publikuje
stałego cennika: ceny są dynamiczne (yield management), więc nawet realna cena z API to migawka
w czasie, nie "oficjalna taryfa" w rozumieniu tego, co OFFICIAL oznacza dla PKP/DB/VRR. Żeby mimo
to dało się odróżnić realną cenę od zgrubnego fallbacku, breakdown["zrodlo"] jest zawsze
"api_flixbus_live" albo "fallback_km".

Fallback po km jest dodatkowo oznaczony breakdown["price_verified"] = False (ten sam klucz, co
przy innych cenach niepotwierdzonych, patrz routing/pricing.py): to zgrubne 0,27 PLN/km, a nie
cena z oferty, więc UI i demo.py dopisują "cena niepotwierdzona", a wariant z takim odcinkiem
nie wygrywa rankingu "Najtańsza" z wariantem o potwierdzonej cenie. Cena z live API nie dostaje
tej flagi — pozostaje bez zmian.
"""

import re

from . import _flixbus_api
from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_FALLBACK = load("flixbus_fallback.json")

_STATION_NOISE = re.compile(
    r"\b(Hauptbahnhof|Fernbusterminal|Bus Station|Railway Station|Busbahnhof|ZOB|Hbf|Bhf)\b.*$",
    re.IGNORECASE,
)
_BRACKETED = re.compile(r"\[[^\]]*\]")
_PARENTHESIZED = re.compile(r"\(([^)]+)\)")


def _clean_city_name(station_name: str) -> str:
    """Wyciąga nazwę miasta z nazwy przystanku/dworca GTFS (np. 'Berlin ZOB [Fernbus]' -> 'Berlin',
    'S Südkreuz Bhf (Berlin)' -> 'Berlin', 'Lodz, Bus Station' -> 'Lodz'), bo API FlixBusa
    (find_city_id) szuka miast, nie konkretnych przystanków — surowa nazwa GTFS zwykle nie
    trafia w żadne miasto (albo trafia w przypadkowe, np. 'Florence Bus Station' w USA)."""
    paren_match = _PARENTHESIZED.search(station_name)
    if paren_match:
        return paren_match.group(1).strip()

    city = station_name.split(",")[0]
    city = _BRACKETED.sub("", city)
    city = _STATION_NOISE.sub("", city)
    return city.strip() or station_name


def _fallback_estimate(segment: Segment, reason: str) -> PriceEstimate:
    if segment.distance_km is None:
        raise ValueError(
            "FlixBus: distance_km jest wymagane (do fallbacku po km, gdy API niedostępne)"
        )

    pln_per_km = _FALLBACK["pln_per_km"]
    amount = round(pln_per_km * segment.distance_km, 2)

    return PriceEstimate(
        carrier=Carrier.FLIXBUS,
        amount=amount,
        currency="PLN",
        price_type=PriceType.ESTIMATE,
        breakdown={
            "zrodlo": "fallback_km",
            "price_verified": False,
            "pln_per_km": pln_per_km,
            "odleglosc_km": segment.distance_km,
        },
        notes=(
            f"{reason} Fallback: {pln_per_km} PLN/km x {segment.distance_km:.0f} km "
            "(bardzo zgrubny szacunek, patrz fares/data/flixbus_fallback.json)."
        ),
    )


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.FLIXBUS:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora FlixBus: {segment.carrier}")

    if not segment.travel_date:
        return _fallback_estimate(
            segment, "Brak travel_date w segmencie — API FlixBus wymaga konkretnej daty przejazdu."
        )

    try:
        from_id = _flixbus_api.find_city_id(_clean_city_name(segment.origin))
        to_id = _flixbus_api.find_city_id(_clean_city_name(segment.destination))
        trip = _flixbus_api.fetch_cheapest_trip(from_id, to_id, segment.travel_date, currency="EUR")
    except _flixbus_api.FlixbusApiError as exc:
        return _fallback_estimate(segment, f"API FlixBus niedostępne/bez wyniku ({exc})")

    try:
        amount = round(float(trip["price"]["total"]), 2)
        currency = trip["price"].get("currency", "EUR")
    except (KeyError, TypeError) as exc:
        return _fallback_estimate(segment, f"Nieoczekiwana odpowiedź API FlixBus ({exc})")

    return PriceEstimate(
        carrier=Carrier.FLIXBUS,
        amount=amount,
        currency=currency,
        price_type=PriceType.ESTIMATE,
        breakdown={
            "zrodlo": "api_flixbus_live",
            "relacja": f"{segment.origin} -> {segment.destination}",
            "data": segment.travel_date,
            "przesiadki": trip.get("transfer_count"),
        },
        notes=(
            "Realna cena z publicznego (nieoficjalnego) API FlixBusa dla podanej daty. Oznaczona "
            "jako 'szacunek' (nie 'oficjalna_taryfa'), bo ceny FlixBusa są dynamiczne jak w "
            "lotnictwie, nie ma stałego cennika — patrz breakdown['zrodlo'] = 'api_flixbus_live' "
            "żeby odróżnić od zgrubnego fallbacku po km."
        ),
    )
