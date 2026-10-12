"""Dynamiczny dobór hubów lot<->kolej: lotniska w pobliżu miasta startu i celu zamiast
sztywnej listy z demo_route.py.

Tabela routing/data/airports.json to lotniska PL+DE (współrzędne z OpenFlights/OurAirports);
NIE mówi, czy z danego lotniska latają jakiekolwiek rejsy. Lot bezpośredni między parą lotnisk
jest potwierdzany dopiero na żywo w Travelpayouts (wpis z 0 przesiadek) — bez tego pary nie
dodajemy, żeby nie sugerować nieistniejącego połączenia (patrz demo_route.py, UWAGA o LUZ-DTM).
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import motis_client
from .demo_route import (
    DORTMUND_HBF_STOP,
    DUSSELDORF_HBF_STOP,
    KRAKOW_LOTNISKO_STOP,
    WARSZAWA_LOTNISKO_CHOPINA_STOP,
)
from .variants import HubConfig

_AIRPORTS = json.loads((Path(__file__).parent / "data" / "airports.json").read_text("utf-8"))

AIRPORT_RADIUS_KM = 200.0  # lotnisko startowe/docelowe do tylu km od miasta
MAX_PAIRS = 16  # tyle najmniej objazdowych par lotnisk sprawdzamy w Travelpayouts (równolegle)
MAX_DETOUR_RATIO = 1.5


# Dane konfiguracyjne (NIE lista par tras): stacja kolejowa, z której/do której liczymy dojazd,
# gdy samo lotnisko nie ma przystanku w MOTIS pod własną nazwą. Dla pozostałych lotnisk
# używamy współrzędnych lotniska i MOTIS dobiera najbliższy przystanek.
AIRPORT_STATIONS = {
    "WAW": WARSZAWA_LOTNISKO_CHOPINA_STOP,
    "KRK": KRAKOW_LOTNISKO_STOP,
    "DTM": DORTMUND_HBF_STOP,
    "DUS": DUSSELDORF_HBF_STOP,
}


def access_place(airport: "Airport"):
    return AIRPORT_STATIONS.get(airport.iata) or motis_client.coords_place(airport.lat, airport.lon)


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    lat: float
    lon: float


def airports_near(lat: float, lon: float, radius_km: float = AIRPORT_RADIUS_KM) -> list[Airport]:
    found = [
        (motis_client.haversine_km(lat, lon, a["lat"], a["lon"]), Airport(a["iata"], a["name"], a["lat"], a["lon"]))
        for a in _AIRPORTS
    ]
    return [a for km, a in sorted(found, key=lambda t: t[0]) if km <= radius_km]


def candidate_airport_pairs(origin, destination) -> list[tuple[Airport, Airport]]:
    """Pary (lotnisko wylotu, lotnisko przylotu) bez objazdu: przylot bliżej celu niż wylot i
    łączna droga (start->wylot->przylot->cel, linia prosta) <= MAX_DETOUR_RATIO x bezpośrednia."""
    h = motis_client.haversine_km
    direct = max(h(*origin, *destination), 1.0)
    scored = []
    for a in airports_near(*origin):
        for b in airports_near(*destination):
            if a.iata == b.iata:
                continue
            if h(b.lat, b.lon, *destination) >= h(a.lat, a.lon, *destination):
                continue
            path = h(*origin, a.lat, a.lon) + h(a.lat, a.lon, b.lat, b.lon) + h(b.lat, b.lon, *destination)
            if path <= MAX_DETOUR_RATIO * direct:
                scored.append((path, a, b))
    return [(a, b) for _, a, b in sorted(scored, key=lambda t: t[0])[:MAX_PAIRS]]


def direct_flight_status(origin_iata: str, destination_iata: str, date: str) -> tuple[bool, str]:
    """(jest lot bezpośredni, powód). Pytamy Travelpayouts o bilety z direct=true (dokładna data,
    potem cały miesiąc). Pusty wynik znaczy tylko brak biletu bezpośredniego w cache, nie dowód
    braku lotu. Błąd API dla pary daje (False, powód) zamiast wyjątku."""
    from flights import travelpayouts

    try:
        for when in (date, date[:7]):
            if travelpayouts.fetch_direct_tickets(origin_iata, destination_iata, when):
                return True, ""
    except Exception as exc:  # brak tokena, sieć, błąd API
        return False, f"błąd Travelpayouts: {exc}"
    return False, (
        "brak biletu bezpośredniego w cache Travelpayouts (data ani miesiąc); "
        "to nie dowodzi braku lotu, tylko braku potwierdzenia"
    )


def has_direct_flight(origin_iata: str, destination_iata: str, date: str) -> bool:
    return direct_flight_status(origin_iata, destination_iata, date)[0]


def discover_hubs(origin, destination, date: str, skip: set | None = None):
    """Huby lot<->kolej dla pary współrzędnych (lat, lon): tylko pary z potwierdzonym lotem
    bezpośrednim. `skip` = pary (IATA, IATA) już obsłużone ręcznie skonfigurowanymi hubami.
    Stacje dojazdowe to współrzędne lotniska — MOTIS dobiera najbliższy przystanek.

    Zwraca (huby, odrzucone), gdzie odrzucone to lista (etykieta pary, powód) do UI."""
    pairs = [
        (a, b)
        for a, b in candidate_airport_pairs(origin, destination)
        if not (skip and (a.iata, b.iata) in skip)
    ]
    rejected: list[tuple[str, str]] = []
    if not pairs:
        rejected.append(("Lotniska", "brak par lotnisk w promieniu bez objazdu (tabela lotnisk PL+DE)"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda ab: direct_flight_status(ab[0].iata, ab[1].iata, date), pairs))
    hubs = []
    by_reason: dict[str, list[str]] = {}
    for (a, b), (ok, reason) in zip(pairs, results):
        if not ok:
            by_reason.setdefault(reason, []).append(f"{a.iata}→{b.iata}")
            continue
        hubs.append(
            HubConfig(
                label=f"{a.iata}-{b.iata}",
                origin_iata=a.iata,
                destination_iata=b.iata,
                origin_rail_access_stop_id=access_place(a),
                destination_rail_access_stop_id=access_place(b),
            )
        )
    for reason, labels in by_reason.items():
        rejected.append((f"Loty bez potwierdzenia ({len(labels)} par)", f"{reason}. Pary: {', '.join(labels)}"))
    return hubs, rejected
