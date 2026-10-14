"""Klient silnika routingu MOTIS (Sesja 2): zapytania /api/v6/plan i parsowanie odcinków.

MOTIS musi być uruchomiony lokalnie (scripts/run_motis.sh|ps1 server) — domyślnie
http://localhost:8080, konfigurowalne przez zmienną środowiskową MOTIS_BASE_URL.
"""

import math
import os
from dataclasses import dataclass
from datetime import datetime

import requests

from i18n import Msg

from .model import Leg, LegMode

MOTIS_BASE_URL = os.environ.get("MOTIS_BASE_URL", "http://localhost:8080")


TRANSFER_BUFFER_MINUTES = (
    10  # additionalTransferTime: MOTIS szuka przesiadek z zapasem, zamiast najkrótszych "na styk"
)
MAIN_QUERY_ITINERARIES = (
    30  # ~6 s na zapytanie; domyślne ~5 wyników gubiło proste trasy (np. przez Berlin)
)
MAX_WALK_SECONDS = 3600  # do godziny pieszo do/z pierwszego/ostatniego przystanku


class MotisError(RuntimeError):
    """Błąd komunikacji z MOTIS albo brak połączenia dla podanej relacji/daty. Komunikat może być
    `i18n.Msg` (UI renderuje go w wybranym języku przez `i18n.exc_text` + `tm`)."""


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


def decode_polyline(points: str, precision: int = 6) -> list[tuple[float, float]]:
    """Dekoduje Google encoded polyline (tak MOTIS koduje `legGeometry`) na listę (lat, lon).

    `precision` pochodzi z odpowiedzi (MOTIS v2+/API v6: 6 cyfr po przecinku)."""
    factor = 10.0**precision
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    while index < len(points):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                chunk = ord(points[index]) - 63
                index += 1
                result |= (chunk & 0x1F) << shift
                shift += 5
                if chunk < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))
    return coords


def _path_km(path: list[tuple[float, float]]) -> float:
    return sum(haversine_km(*a, *b) for a, b in zip(path, path[1:], strict=False))


# Etykiety źródła kilometrów po torach (trafiają do Segment.distance_source i breakdown ceny).
TRACK_KM_GEOMETRY = "geometria odcinka z MOTIS (legGeometry)"
TRACK_KM_STOPS = "suma odległości między przystankami pośrednimi z MOTIS (intermediateStops)"

# Koniec geometrii musi leżeć blisko stacji końcowej odcinka; dalszy kształt to nie ta trasa.
GEOMETRY_ENDPOINT_TOLERANCE_KM = 2.0


def _geometry_path(raw: dict) -> list[tuple[float, float]] | None:
    """Punkty `legGeometry` odcinka transitu albo None, gdy MOTIS nie dał użytecznego kształtu
    (pusta polilinia przy detailedLegs=false, tylko 2 punkty = zwykła prosta, końce nie pasują)."""
    geometry = raw.get("legGeometry") or {}
    if not geometry.get("points"):
        return None
    path = decode_polyline(geometry["points"], geometry.get("precision") or 6)
    if len(path) < 3:
        return None
    origin, destination = raw["from"], raw["to"]
    if (
        haversine_km(*path[0], origin["lat"], origin["lon"]) > GEOMETRY_ENDPOINT_TOLERANCE_KM
        or haversine_km(*path[-1], destination["lat"], destination["lon"])
        > GEOMETRY_ENDPOINT_TOLERANCE_KM
    ):
        return None
    return path


def _stops_path(raw: dict) -> list[tuple[float, float]] | None:
    """from -> intermediateStops -> to jako łamana albo None (brak przystanków pośrednich albo
    któryś bez współrzędnych)."""
    stops = raw.get("intermediateStops") or []
    if not stops:
        return None
    points = [raw["from"], *stops, raw["to"]]
    if any(p.get("lat") is None or p.get("lon") is None for p in points):
        return None
    return [(p["lat"], p["lon"]) for p in points]


def track_distance_km(raw: dict) -> tuple[float, str] | None:
    """Długość odcinka transitu mierzona wzdłuż trasy pociągu (nie w linii prostej), z tego, co
    MOTIS faktycznie zwraca: kształtu `legGeometry` albo łamanej przez `intermediateStops`.

    Zwraca (km, etykieta źródła) albo None, gdy odpowiedź nie niesie nic ponad linię prostą.
    MOTIS NIE zwraca `shape_dist_traveled` z GTFS. Obie metody to suma odcinków prostych (między
    punktami kształtu / przystankami), więc są dolnym ograniczeniem długości toru, ale nie tak
    zaniżonym jak jedna cięciwa początek-koniec. Przy obu wiarygodnych źródłach bierzemy
    dłuższe (bliższe torom); bez żadnego współczynnika korygującego."""
    candidates = []
    for path, label in (
        (_geometry_path(raw), TRACK_KM_GEOMETRY),
        (_stops_path(raw), TRACK_KM_STOPS),
    ):
        if path:
            candidates.append((_path_km(path), label))
    return max(candidates, key=lambda c: c[0]) if candidates else None


def _geocode_raw(text: str) -> list[dict]:
    """Surowa odpowiedź /api/v1/geocode (z polami type/id, jeśli MOTIS je zwraca)."""
    try:
        response = requests.get(
            f"{MOTIS_BASE_URL}/api/v1/geocode", params={"text": text}, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise MotisError(Msg("err.motis_geocode", url=MOTIS_BASE_URL, error=str(exc))) from exc


def geocode_suggestions(text: str, limit: int = 5) -> list[dict]:
    """Podpowiedzi adresów przez /api/v1/geocode: lista {lat, lon, name} do wyboru w UI.

    Pusty tekst albo brak dopasowań -> pusta lista (nie jest to błąd, w przeciwieństwie
    do geocode(), bo UI ma po prostu nic nie podpowiedzieć zamiast wywalić wyjątek).
    """
    if not text or not text.strip():
        return []
    results = _geocode_raw(text)
    out = []
    for r in results[:limit]:
        suggestion = {"lat": r["lat"], "lon": r["lon"], "name": r.get("name") or text}
        # typ miejsca (STOP / ADDRESS / PLACE) i ewentualna kategoria służą UI do odsiania śmieci
        # (np. stron WWW z nazwą w OSM); dokładamy je tylko wtedy, gdy MOTIS je zwrócił
        for field in ("type", "category"):
            if r.get(field):
                suggestion[field] = r[field]
        out.append(suggestion)
    return out


@dataclass(frozen=True)
class StopRef:
    """Przystanek opisany nazwą i współrzędnymi zamiast zaszytego stopId MOTIS.

    stopId z GTFS (np. "defv_344028") zmienia się przy każdym odświeżeniu paczki danych, więc
    zamiast niego trzymamy nazwę i miejsce stacji; właściwe ID rozwiązuje `find_stop_id`."""

    name: str
    lat: float
    lon: float


# Maksymalna odległość między współrzędnymi StopRef a znalezionym przystankiem MOTIS. Większa
# wartość oznacza, że MOTIS nie ma tam stacji o tej nazwie — wtedy wolimy błąd niż zły przystanek.
STOP_MATCH_RADIUS_KM = 5.0

_STOP_ID_CACHE: dict[StopRef, str] = {}


def find_stop_id(ref: StopRef) -> str:
    """Rozwiązuje StopRef na stopId MOTIS: najbliższy wynik typu STOP do podanych współrzędnych.

    Wynik jest cache'owany w pamięci procesu (jedno zapytanie na przystanek). Zapytanie idzie
    przez /api/v1/geocode po nazwie, więc działa z każdą paczką GTFS bez zmian w kodzie."""
    cached = _STOP_ID_CACHE.get(ref)
    if cached is not None:
        return cached

    best_id, best_km = None, STOP_MATCH_RADIUS_KM
    for result in _geocode_raw(ref.name):
        if result.get("type") != "STOP" or not result.get("id"):
            continue
        km = haversine_km(ref.lat, ref.lon, result["lat"], result["lon"])
        if km <= best_km:
            best_id, best_km = result["id"], km

    if best_id is None:
        raise MotisError(
            Msg(
                "err.motis_stop_not_found",
                name=repr(ref.name),
                radius=STOP_MATCH_RADIUS_KM,
                lat=ref.lat,
                lon=ref.lon,
            )
        )
    _STOP_ID_CACHE[ref] = best_id
    return best_id


def stop_id(value: str | StopRef) -> str:
    """Zwraca stopId MOTIS: wartość już podaną jako string przechodzi bez zmian (np. współrzędne
    "lat,lon" albo ręcznie podane ID), StopRef jest rozwiązywany przez `find_stop_id`."""
    return find_stop_id(value) if isinstance(value, StopRef) else value


def geocode(text: str) -> tuple:
    """Adres/nazwa -> (lat, lon, nazwa) przez /api/v1/geocode (OSM od Sesji 4b).

    Zwraca pierwszy wynik MOTIS; podaj dokładny adres z miastem, np.
    "Krakowskie Przedmieście 50, Lublin".
    """
    results = geocode_suggestions(text, limit=1)
    if not results:
        raise MotisError(Msg("err.motis_address_not_found", text=repr(text)))
    best = results[0]
    return best["lat"], best["lon"], best["name"]


def coords_place(lat: float, lon: float) -> str:
    """Format miejsca dla /plan: współrzędne (MOTIS sam dołoży dojście piesze do przystanku)."""
    return f"{lat},{lon}"


def plan(
    from_place: str,
    to_place: str,
    time: str,
    max_transfers: int = 4,
    num_itineraries: int | None = None,
) -> dict:
    """GET /api/v6/plan — surowa odpowiedź MOTIS, zwalidowana pod kątem obecności itinerariów."""
    extra = (
        {"numItineraries": num_itineraries, "additionalTransferTime": TRANSFER_BUFFER_MINUTES}
        if num_itineraries
        else {}
    )
    try:
        response = requests.get(
            f"{MOTIS_BASE_URL}/api/v6/plan",
            params={
                **extra,
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
        if getattr(response, "status_code", None) == 400:
            # MOTIS zwraca {"error": "..."} np. gdy data jest poza wczytanym rozkładem jazdy
            try:
                detail = response.json().get("error")
            except ValueError:
                detail = None
            if detail:
                raise MotisError(Msg("err.motis_rejected", detail=detail))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MotisError(Msg("err.motis_request", url=MOTIS_BASE_URL, error=str(exc))) from exc

    payload = response.json()
    if not _all_itineraries(payload):
        raise MotisError(
            Msg(
                "err.motis_no_itinerary",
                origin=from_place,
                destination=to_place,
                time=time,
                minutes=MAX_WALK_SECONDS // 60,
            )
        )
    return payload


def _all_itineraries(payload: dict) -> list[dict]:
    """Itineraria z transitem ORAZ bezpośrednie (`direct`, czysty marsz door-to-door).

    MOTIS trzyma dojście pieszo w osobnej liście `direct`; pomijanie jej sprawiało, że dla
    dwóch punktów w tym samym mieście (np. Plac Defilad -> Warszawa Centralna, ~500 m) zostawały
    wyłącznie absurdalne trasy koleją (7,3 h przez Poznań) zamiast kilku minut pieszo."""
    return [*payload.get("itineraries", []), *payload.get("direct", [])]


def fastest_itinerary(payload: dict) -> dict:
    return min(_all_itineraries(payload), key=lambda it: it["duration"])


def fewest_transfers_itinerary(payload: dict) -> dict:
    return min(_all_itineraries(payload), key=lambda it: (it.get("transfers", 0), it["duration"]))


def itinerary_to_legs(itinerary: dict) -> list[Leg]:
    """Zamienia itinerary MOTIS na listę Leg.

    Odcinki WALK na początku i końcu (dojście z adresu / do adresu) stają się legami
    LegMode.WALK; WALK między odcinkami transitu są tylko oznaczeniem requires_walk
    (przesiadka wymagająca przejścia). Tryb BUS z MOTIS -> LegMode.BUS, reszta transitu -> RAIL.
    """
    raw_legs = itinerary["legs"]
    legs: list[Leg] = []
    preceded_by_walk = False
    last_index = len(raw_legs) - 1

    for idx, raw in enumerate(raw_legs):
        origin = raw["from"]
        destination = raw["to"]
        distance_km = haversine_km(
            origin["lat"], origin["lon"], destination["lat"], destination["lon"]
        )
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
                        extra={
                            "motis_mode": "WALK",
                            "walk_role": "dojscie" if access else "dojscie_do_celu",
                            "walk_distance_m": raw.get("distance"),
                        },
                        **common,
                    )
                )
            else:
                preceded_by_walk = True
            continue

        mode = (
            LegMode.RAIL if "RAIL" in raw["mode"] or raw["mode"] == "TRAIN" else LegMode.BUS
        )  # tramwaj/metro/autobus = transport lokalny; SUBURBAN (SKM, S-Bahn) też trafia do BUS,
        # ale wycenia go osobna ścieżka (pricing.is_suburban_leg), nie ryczałt autobusowy
        has_prev_transit = any(l.mode is not LegMode.WALK for l in legs)
        extra = {
            "motis_mode": raw["mode"],
            "route_short_name": raw.get("routeShortName"),
            "origin_stop_id": origin.get("stopId"),
            "destination_stop_id": destination.get("stopId"),
            "origin_lat": origin.get("lat"),
            "origin_lon": origin.get("lon"),
            "destination_lat": destination.get("lat"),
            "destination_lon": destination.get("lon"),
        }
        track = track_distance_km(raw)
        if track is not None:
            extra["distance_along_track_km"], extra["distance_along_track_source"] = track
        legs.append(
            Leg(
                mode=mode,
                carrier_name=raw.get("agencyName") or raw.get("routeShortName") or "",
                requires_walk=preceded_by_walk if has_prev_transit else False,
                extra=extra,
                **common,
            )
        )
        preceded_by_walk = False

    return legs


def plan_leg(from_place: str, to_place: str, time: str, *, pick: str = "fastest") -> list[Leg]:
    """Zapytanie do MOTIS + wybór jednego itinerary (fastest/fewest_transfers) -> lista Leg.

    To NIE przeszukuje alternatywnych węzłów przesiadkowych — from_place/to_place są ustalone
    przez wywołującego (patrz routing/demo_route.py), wybieramy tylko między itinerariami,
    które MOTIS zwrócił dla TEJ SAMEJ relacji.
    """
    payload = plan(from_place, to_place, time)
    picker = fastest_itinerary if pick == "fastest" else fewest_transfers_itinerary
    return itinerary_to_legs(picker(payload))


def plan_leg_candidates(
    from_place: str, to_place: str, time: str, max_candidates: int = 3
) -> list[list[Leg]]:
    """Jak `plan_leg`, ale zwraca do `max_candidates` alternatywnych itinerariów (posortowanych
    rosnąco wg czasu trwania) zamiast automatycznie wybierać tylko najszybszy.

    Używane przez warianty hubowe lot<->kolej (routing/variants.py::build_rail_flight_rail_variant
    / build_flight_regional_variant): dojazd/odjazd z huba NIE zawsze powinien być najszybszym
    pojedynczym fragmentem MOTIS-a — czasem ma ciaśniejszą/ryzykowną przesiadkę albo droższy
    bilet niż odrobinę wolniejsza alternatywa, która wypada lepiej w CAŁYM wariancie (patrz
    `routing/variants.py::_best_overall`)."""
    payload = plan(
        from_place, to_place, time, max_transfers=5, num_itineraries=max(max_candidates, 1)
    )
    itineraries = sorted(_all_itineraries(payload), key=lambda it: it["duration"])[:max_candidates]
    return [itinerary_to_legs(it) for it in itineraries]


def all_itineraries_as_legs(from_place: str, to_place: str, time: str) -> list[list[Leg]]:
    """Wszystkie itineraria zwrócone przez MOTIS dla jednej relacji/daty, każde jako lista Leg."""
    payload = plan(
        from_place, to_place, time, max_transfers=5, num_itineraries=MAIN_QUERY_ITINERARIES
    )
    return [itinerary_to_legs(it) for it in _all_itineraries(payload)]
