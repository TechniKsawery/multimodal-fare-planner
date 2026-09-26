"""Klient silnika routingu MOTIS (Sesja 2): zapytania /api/v6/plan i parsowanie odcinków.

MOTIS musi być uruchomiony lokalnie (scripts/run_motis.sh|ps1 server) — domyślnie
http://localhost:8080, konfigurowalne przez zmienną środowiskową MOTIS_BASE_URL.
"""
import math
import os
from datetime import datetime
from typing import List, Optional

import requests

from .model import Leg, LegMode

MOTIS_BASE_URL = os.environ.get("MOTIS_BASE_URL", "http://localhost:8080")


MAX_WALK_SECONDS = 3600  # do godziny pieszo do/z pierwszego/ostatniego przystanku


class MotisError(RuntimeError):
    """Błąd komunikacji z MOTIS albo brak połączenia dla podanej relacji/daty."""


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Odległość w linii prostej (great-circle) w km — używana jako distance_km dla fares."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode(text: str) -> tuple:
    """Adres/nazwa -> (lat, lon, nazwa) przez /api/v1/geocode (OSM od Sesji 4b).

    Zwraca pierwszy wynik MOTIS; podaj dokładny adres z miastem, np.
    "Krakowskie Przedmieście 50, Lublin".
    """
    try:
        response = requests.get(f"{MOTIS_BASE_URL}/api/v1/geocode", params={"text": text}, timeout=30)
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        raise MotisError(f"Błąd geocodingu w MOTIS ({MOTIS_BASE_URL}): {exc}") from exc
    if not results:
        raise MotisError(f"MOTIS nie znalazł adresu: {text!r}")
    best = results[0]
    return best["lat"], best["lon"], best.get("name") or text


def coords_place(lat: float, lon: float) -> str:
    """Format miejsca dla /plan: współrzędne (MOTIS sam dołoży dojście piesze do przystanku)."""
    return f"{lat},{lon}"


def plan(from_place: str, to_place: str, time: str, max_transfers: int = 4) -> dict:
    """GET /api/v6/plan — surowa odpowiedź MOTIS, zwalidowana pod kątem obecności itinerariów."""
    try:
        response = requests.get(
            f"{MOTIS_BASE_URL}/api/v6/plan",
            params={
                "fromPlace": from_place,
                "toPlace": to_place,
                "time": time,
                "maxTransfers": max_transfers,
                # domyślny limit dojścia pieszego w MOTIS jest krótki (kilkanaście minut) — dla
                # adresów daleko od stacji (np. Gelsenkirchen-Buer, ~7 km od Hbf) dawał 0 wyników
                "maxPreTransitTime": MAX_WALK_SECONDS,
                "maxPostTransitTime": MAX_WALK_SECONDS,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MotisError(
            f"Błąd zapytania do MOTIS ({MOTIS_BASE_URL}): {exc}. "
            "Sprawdź, czy serwer jest uruchomiony (scripts/run_motis.sh|ps1 server)."
        ) from exc

    payload = response.json()
    if not payload.get("itineraries"):
        raise MotisError(
            f"MOTIS nie znalazł żadnego połączenia {from_place} -> {to_place} dla time={time}."
        )
    return payload


def fastest_itinerary(payload: dict) -> dict:
    return min(payload["itineraries"], key=lambda it: it["duration"])


def fewest_transfers_itinerary(payload: dict) -> dict:
    return min(payload["itineraries"], key=lambda it: (it["transfers"], it["duration"]))


def itinerary_to_legs(itinerary: dict) -> List[Leg]:
    """Zamienia itinerary MOTIS na listę Leg.

    Odcinki WALK na początku i końcu (dojście z adresu / do adresu) stają się legami
    LegMode.WALK; WALK między odcinkami transitu są tylko oznaczeniem requires_walk
    (przesiadka wymagająca przejścia). Tryb BUS z MOTIS -> LegMode.BUS, reszta transitu -> RAIL.
    """
    raw_legs = itinerary["legs"]
    legs: List[Leg] = []
    preceded_by_walk = False
    last_index = len(raw_legs) - 1

    for idx, raw in enumerate(raw_legs):
        origin = raw["from"]
        destination = raw["to"]
        distance_km = haversine_km(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
        common = dict(
            origin_name=origin["name"],
            destination_name=destination["name"],
            depart=_parse_time(raw["startTime"]),
            arrive=_parse_time(raw["endTime"]),
            distance_km=distance_km,
        )

        if raw["mode"] == "WALK":
            if idx == 0 or idx == last_index:
                access = idx == 0
                legs.append(
                    Leg(
                        mode=LegMode.WALK,
                        carrier_name="pieszo",
                        requires_walk=False,
                        extra={"motis_mode": "WALK", "walk_role": "dojscie" if access else "dojscie_do_celu",
                               "walk_distance_m": raw.get("distance")},
                        **common,
                    )
                )
            else:
                preceded_by_walk = True
            continue

        mode = LegMode.RAIL if "RAIL" in raw["mode"] or raw["mode"] == "TRAIN" else LegMode.BUS  # tramwaj/metro/autobus = transport lokalny
        has_prev_transit = any(l.mode is not LegMode.WALK for l in legs)
        legs.append(
            Leg(
                mode=mode,
                carrier_name=raw.get("agencyName") or raw.get("routeShortName") or "",
                requires_walk=preceded_by_walk if has_prev_transit else False,
                extra={
                    "motis_mode": raw["mode"],
                    "route_short_name": raw.get("routeShortName"),
                    "origin_stop_id": origin.get("stopId"),
                    "destination_stop_id": destination.get("stopId"),
                },
                **common,
            )
        )
        preceded_by_walk = False

    return legs


def plan_leg(from_place: str, to_place: str, time: str, *, pick: str = "fastest") -> List[Leg]:
    """Zapytanie do MOTIS + wybór jednego itinerary (fastest/fewest_transfers) -> lista Leg.

    To NIE przeszukuje alternatywnych węzłów przesiadkowych — from_place/to_place są ustalone
    przez wywołującego (patrz routing/demo_route.py), wybieramy tylko między itinerariami,
    które MOTIS zwrócił dla TEJ SAMEJ relacji.
    """
    payload = plan(from_place, to_place, time)
    picker = fastest_itinerary if pick == "fastest" else fewest_transfers_itinerary
    return itinerary_to_legs(picker(payload))


def all_itineraries_as_legs(from_place: str, to_place: str, time: str) -> List[List[Leg]]:
    """Wszystkie itineraria zwrócone przez MOTIS dla jednej relacji/daty, każde jako lista Leg."""
    payload = plan(from_place, to_place, time)
    return [itinerary_to_legs(it) for it in payload["itineraries"]]
