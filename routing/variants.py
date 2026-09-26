"""Generator wariantów trasy: łączy routing MOTIS (kolej) z lotami (flights/) w kilka
sensownych opcji podróży dla jednej pary miast/daty.

Świadome ograniczenie zakresu (Sesja 4, patrz README.md): węzły przesiadkowe (np. które
lotnisko/dworzec pośredni) są ustalone raz w HubConfig, NIE przeszukujemy alternatywnych
hubów (to Sesja 6). Warianty "tylko kolej" korzystają z wielu itinerariów, które MOTIS
i tak zwraca dla jednego zapytania (różne trasy/liczby przesiadek), a nie z przeszukiwania.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from fares.model import DiscountProfile

from . import motis_client, pricing
from .model import Itinerary, Leg, LegMode, SkippedVariant
from .motis_client import MotisError
from .scoring import build_itinerary

try:
    from flights.travelpayouts import TravelpayoutsError
except ImportError:  # pragma: no cover
    TravelpayoutsError = RuntimeError


@dataclass
class RouteRequest:
    """Zapytanie o trasę: para miast (jako stopId MOTIS) + data wyjazdu."""

    origin_stop_id: str
    destination_stop_id: str
    origin_label: str
    destination_label: str
    date: str                       # "YYYY-MM-DD", dzień wyjazdu
    departure_time: str = "06:00:00"  # najwcześniejsza godzina wyjazdu brana pod uwagę w zapytaniach do MOTIS
    discounts: DiscountProfile = field(default_factory=DiscountProfile)
    flight_currency: str = "PLN"

    @property
    def motis_time(self) -> str:
        return f"{self.date}T{self.departure_time}Z"


def request_from_addresses(origin_text: str, destination_text: str, date: str, **overrides) -> RouteRequest:
    """RouteRequest od adresu do adresu (geocoding OSM w MOTIS, Sesja 4b): MOTIS sam dokłada
    dojście piesze z adresu do przystanku i z przystanku do adresu docelowego."""
    o_lat, o_lon, o_name = motis_client.geocode(origin_text)
    d_lat, d_lon, d_name = motis_client.geocode(destination_text)
    kwargs = dict(
        origin_stop_id=motis_client.coords_place(o_lat, o_lon),
        destination_stop_id=motis_client.coords_place(d_lat, d_lon),
        origin_label=o_name,
        destination_label=d_name,
        date=date,
    )
    kwargs.update(overrides)
    return RouteRequest(**kwargs)


@dataclass
class HubConfig:
    """Jeden ustalony węzeł przesiadkowy lot<->kolej: lotnisko wylotu/przylotu + stacje kolejowe
    po obu stronach. origin_rail_access_stop_id może być None, jeśli lotnisko wylotu nie wymaga
    dojazdu kolejowego z origin_stop_id (np. lot bezpośrednio z lotniska w mieście początkowym)."""

    label: str
    origin_iata: str
    destination_iata: str
    origin_rail_access_stop_id: Optional[str]   # stacja przy lotnisku wylotu (np. "Warszawa Lotnisko Chopina")
    destination_rail_access_stop_id: str        # stacja przy/blisko lotniska przylotu (np. "Dortmund Hbf")


def build_flight_leg(origin_iata: str, destination_iata: str, depart_at: datetime) -> Leg:
    """Leg lotu ze SZTYWNYM czasem trwania placeholderem (2h) — nie mamy rozkładu lotów,
    tylko cenę (flights/travelpayouts.py zwraca cenę, nie godziny odlotu/przylotu w naszym
    zapytaniu). To wystarcza do liczenia bufora przesiadki, ale nie jest realną godziną lotu."""
    duration = timedelta(hours=2)
    return Leg(
        mode=LegMode.FLIGHT,
        origin_name=origin_iata,
        destination_name=destination_iata,
        depart=depart_at,
        arrive=depart_at + duration,
        carrier_name="lot",
        distance_km=None,
        requires_walk=True,
        extra={
            "origin_iata": origin_iata,
            "destination_iata": destination_iata,
            "depart_date": depart_at.strftime("%Y-%m-%d"),
        },
    )


def _price_legs(legs: List[Leg], request: RouteRequest):
    return [pricing.price_leg(leg, request.discounts, request.flight_currency) for leg in legs]


def build_rail_only_variants(request: RouteRequest, max_variants: int = 2) -> List[Itinerary]:
    """Do max_variants wariantów kolejowych z JEDNEGO zapytania do MOTIS (różne itineraria,
    które silnik i tak zwraca — nie przeszukujemy innych hubów)."""
    all_legs_options = motis_client.all_itineraries_as_legs(
        request.origin_stop_id, request.destination_stop_id, request.motis_time
    )

    seen_signatures = set()
    variants: List[Itinerary] = []
    for legs in sorted(all_legs_options, key=lambda ls: (ls[-1].arrive - ls[0].depart)):
        signature = tuple((l.origin_name, l.destination_name) for l in legs)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        transit = [l for l in legs if l.mode is not LegMode.WALK]
        modes_used = sorted({l.extra.get("motis_mode", "RAIL") for l in transit})
        name = f"Tylko kolej ({'/'.join(modes_used).lower()}, {len(transit) - 1} przesiadki)"
        priced = _price_legs(legs, request)
        variants.append(build_itinerary(name, priced))

        if len(variants) >= max_variants:
            break

    return variants


def build_rail_flight_rail_variant(request: RouteRequest, hub: HubConfig) -> Itinerary:
    """Kolej (origin -> lotnisko wylotu) + lot + kolej (lotnisko przylotu -> destination)."""
    legs: List[Leg] = []

    if hub.origin_rail_access_stop_id:
        access_legs = motis_client.plan_leg(
            request.origin_stop_id, hub.origin_rail_access_stop_id, request.motis_time
        )
        legs.extend(access_legs)
        flight_depart = legs[-1].arrive + timedelta(minutes=150)  # bufor: odprawa/security
    else:
        flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))

    flight_leg = build_flight_leg(hub.origin_iata, hub.destination_iata, flight_depart)
    legs.append(flight_leg)

    onward_time = (flight_leg.arrive + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
    onward_legs = motis_client.plan_leg(
        hub.destination_rail_access_stop_id, request.destination_stop_id, onward_time
    )
    legs.extend(onward_legs)

    priced = _price_legs(legs, request)
    return build_itinerary(f"Kolej + lot ({hub.label}) + kolej lokalna", priced)


def build_flight_regional_variant(request: RouteRequest, hub: HubConfig) -> Itinerary:
    """Lot (z lotniska blisko origin, bez kolei dojazdowej) + kolej lokalna do destination."""
    flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))
    flight_leg = build_flight_leg(hub.origin_iata, hub.destination_iata, flight_depart)

    onward_time = (flight_leg.arrive + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
    onward_legs = motis_client.plan_leg(
        hub.destination_rail_access_stop_id, request.destination_stop_id, onward_time
    )
    legs = [flight_leg] + onward_legs

    priced = _price_legs(legs, request)
    return build_itinerary(f"Lot ({hub.label}) + transport regionalny", priced)


def generate_variants(
    request: RouteRequest,
    rail_flight_rail_hubs: Optional[List[HubConfig]] = None,
    flight_regional_hubs: Optional[List[HubConfig]] = None,
) -> Tuple[List[Itinerary], List[SkippedVariant]]:
    """Generuje wszystkie warianty dla request + skonfigurowane huby. Warianty, których nie
    udało się zbudować (np. brak tokena Travelpayouts, MOTIS nie znalazł połączenia), lądują
    w SkippedVariant z powodem, zamiast przerywać cały proces.

    rail_flight_rail_hubs: huby dla wariantu "kolej + lot + kolej lokalna" (wymagają dojazdu
    kolejowego do lotniska wylotu, hub.origin_rail_access_stop_id).
    flight_regional_hubs: huby dla wariantu "lot + transport regionalny" (lotnisko wylotu
    zakładane jako dostępne bez dalekiego dojazdu kolejowego z origin_stop_id).
    """
    built: List[Itinerary] = []
    skipped: List[SkippedVariant] = []

    try:
        built.extend(build_rail_only_variants(request))
    except MotisError as exc:
        skipped.append(SkippedVariant("Tylko kolej", str(exc)))

    for hub in rail_flight_rail_hubs or []:
        label = f"Kolej + lot ({hub.label}) + kolej lokalna"
        try:
            built.append(build_rail_flight_rail_variant(request, hub))
        except (MotisError, TravelpayoutsError) as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    for hub in flight_regional_hubs or []:
        label = f"Lot ({hub.label}) + transport regionalny"
        try:
            built.append(build_flight_regional_variant(request, hub))
        except (MotisError, TravelpayoutsError) as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    return built, skipped
