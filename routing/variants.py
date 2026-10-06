"""Generator wariantów trasy: łączy routing MOTIS (kolej) z lotami (flights/) w kilka
sensownych opcji podróży dla jednej pary miast/daty.

Huby lot<->kolej (HubConfig) są konfigurowane jako LISTA kandydatów (patrz `demo_route.py`)
— `generate_variants` buduje jeden wariant na hub, więc dodanie alternatywnego lotniska/miasta
przesiadkowego to tylko dopisanie kolejnego HubConfig do listy.

Sesja 6: analogiczny mechanizm dla wariantów czysto kolejowych. Warianty "tylko kolej"
(`build_rail_only_variants`) nadal biorą się z jednego zapytania origin->destination do MOTIS
(różne itineraria, które silnik i tak zwraca) — to dobrze pokrywa alternatywne PRZESIADKI
w obrębie trasy, którą MOTIS sam wybrał. Nie pokrywa jednak sytuacji, w której warto explicite
sprawdzić przejazd przez INNE miasto graniczne/węzeł niż to, które MOTIS domyślnie faworyzuje
w topowych itinerariach (np. Poznań/Rzepin zamiast Warszawa/Berlin), albo start z innego
dworca w tym samym mieście. Do tego służy `AlternativeStop` + `build_rail_via_stop_variant` /
`build_rail_from_alternative_origin_variant` / `build_rail_from_alternative_destination_variant`,
spinane w `generate_variants` przez `via_hub_stops` / `alternative_origin_stops` /
`alternative_destination_stops`. Wszystkie warianty kolejowe (główne zapytanie + alternatywy)
są odchudzane wspólnym dedup po sygnaturze trasy (sekwencja origin/destination nazw odcinków),
żeby ta sama trasa znaleziona dwiema drogami nie pojawiła się dwukrotnie.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fares.model import DiscountProfile

from . import motis_client, pricing
from .model import Itinerary, Leg, LegMode, SkippedVariant
from .motis_client import MotisError
from .scoring import build_itinerary
from .transfers import MIN_TRANSFER_MINUTES_WALK

try:
    from flights.travelpayouts import TravelpayoutsError
except ImportError:  # pragma: no cover
    TravelpayoutsError = RuntimeError

# Strefa, w której użytkownik podaje datę i godzinę wyjazdu (rozkłady PL/DE — czas lokalny).
LOCAL_TIMEZONE = ZoneInfo("Europe/Warsaw")


@dataclass
class RouteRequest:
    """Zapytanie o trasę: para miast (jako stopId MOTIS) + data wyjazdu."""

    origin_stop_id: str
    destination_stop_id: str
    origin_label: str
    destination_label: str
    date: str  # "YYYY-MM-DD", dzień wyjazdu
    departure_time: str = (
        "06:00:00"  # najwcześniejsza godzina wyjazdu brana pod uwagę w zapytaniach do MOTIS
    )
    discounts: DiscountProfile = field(default_factory=DiscountProfile)
    flight_currency: str = "PLN"

    @property
    def motis_time(self) -> str:
        # czas LOKALNY z offsetem (np. 2026-10-09T06:00:00+02:00) — wcześniej "…Z" traktowało
        # 06:00 jako UTC, czyli okno wyszukiwania zaczynało się o 08:00 czasu polskiego
        local = datetime.fromisoformat(f"{self.date}T{self.departure_time}")
        return local.replace(tzinfo=LOCAL_TIMEZONE).isoformat()


def request_from_addresses(
    origin_text: str, destination_text: str, date: str, **overrides
) -> RouteRequest:
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
    origin_rail_access_stop_id: (
        str | None
    )  # stacja przy lotnisku wylotu (np. "Warszawa Lotnisko Chopina")
    destination_rail_access_stop_id: (
        str  # stacja przy/blisko lotniska przylotu (np. "Dortmund Hbf")
    )


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


def _price_legs(legs: list[Leg], request: RouteRequest):
    return [pricing.price_leg(leg, request.discounts, request.flight_currency) for leg in legs]


def _departs_on_request_date(legs: list[Leg], request: RouteRequest) -> bool:
    """True, gdy pierwszy odcinek wariantu rusza w dniu wyszukiwania (czas lokalny).

    MOTIS szuka od podanego czasu bez górnej granicy, więc bez tego filtra w wynikach
    pojawiają się połączenia z dnia następnego (np. najtańszy wariant dla 2026-10-09 ruszał
    2026-10-10). Nocny przejazd, który rusza wieczorem dnia wyszukiwania, nadal przechodzi."""
    return legs[0].depart.astimezone(LOCAL_TIMEZONE).date().isoformat() == request.date


def _legs_signature(legs: list[Leg]) -> tuple[tuple[str, str], ...]:
    """Sygnatura trasy (sekwencja origin/destination nazw odcinków) do dedup: ta sama fizyczna
    trasa znaleziona przez różne zapytania (główne + alternatywne huby/dworce) liczy się raz."""
    return tuple((l.origin_name, l.destination_name) for l in legs)


def build_rail_only_variants(
    request: RouteRequest, max_variants: int = 30, seen_signatures: set | None = None
) -> list[Itinerary]:
    """Do max_variants (domyślnie wszystkie z 30 zwróconych) wariantów kolejowych z JEDNEGO zapytania do MOTIS (różne itineraria,
    które silnik i tak zwraca — nie przeszukujemy innych hubów).

    seen_signatures: opcjonalny współdzielony zbiór sygnatur tras (patrz `_legs_signature`) —
    pozwala `generate_variants` odchudzać wyniki z alternatywnych hubów/dworców względem
    już znalezionych tras, bez duplikatów. Zbiór jest modyfikowany w miejscu."""
    all_legs_options = motis_client.all_itineraries_as_legs(
        request.origin_stop_id, request.destination_stop_id, request.motis_time
    )

    if seen_signatures is None:
        seen_signatures = set()
    variants: list[Itinerary] = []
    for legs in sorted(all_legs_options, key=lambda ls: (ls[-1].arrive - ls[0].depart)):
        if not _departs_on_request_date(legs, request):
            continue
        signature = _legs_signature(legs)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        transit = [l for l in legs if l.mode is not LegMode.WALK]
        modes_used = sorted({l.extra.get("motis_mode", "RAIL") for l in transit})
        name = f"Tylko kolej ({'/'.join(modes_used).lower()}, {len(transit) - 1} przesiadki)"
        priced = _price_legs(legs, request)
        candidate = build_itinerary(name, priced)
        if candidate.is_infeasible:  # przesiadka poniżej absolutnego minimum — odrzucamy
            continue
        variants.append(candidate)

        if len(variants) >= max_variants:
            break

    return variants


@dataclass
class AlternativeStop:
    """Alternatywny przystanek/dworzec/węzeł do jawnego wypróbowania obok głównego origin/
    destination z RouteRequest — albo jako inny dworzec w tym samym mieście (start/koniec),
    albo jako miasto graniczne/węzeł pośredni, przez które MOTIS mógłby nie poprowadzić trasy
    w swoich topowych itinerariach dla zapytania origin->destination wprost."""

    label: str
    stop_id: str


def build_rail_via_stop_variant(request: RouteRequest, via: AlternativeStop) -> Itinerary:
    """Kolej: origin -> via -> destination jako DWA osobne zapytania do MOTIS, jawnie spięte
    przez węzeł pośredni `via` — zamiast polegać na tym, że MOTIS sam wybierze tę trasę w
    jednym zapytaniu origin->destination.

    Drugie zapytanie NIE startuje dokładnie od czasu przyjazdu pierwszego odcinka: bez bufora
    MOTIS łapie najbliższy odjazd, co potrafi dać przesiadkę na kilka minut (poniżej nawet
    absolutnego minimum wykonalności z transfers.py) — w jednym zapytaniu origin->destination
    MOTIS ma na to `additionalTransferTime`, tu robimy to samo ręcznie, przesuwając czas drugiego
    zapytania o MIN_TRANSFER_MINUTES_WALK (bezpieczny próg przesiadki z przejściem — patrz
    transfers.py). Przesiadka w węźle pośrednim między dwoma NIEZALEŻNIE zapytanymi odcinkami
    też jest jawnie oznaczona jako wymagająca przejścia (requires_walk), bo w przeciwieństwie
    do itinerary z jednego zapytania nie wiemy, czy to ten sam peron."""
    first_legs = motis_client.plan_leg(request.origin_stop_id, via.stop_id, request.motis_time)
    if not _departs_on_request_date(first_legs, request):
        raise MotisError(f"Brak połączenia do {via.label} w dniu {request.date}.")
    # bufor na przesiadkę w węźle via — bez niego MOTIS podaje odjazd tuż po przyjeździe
    # i wariant odpada jako fizycznie niewykonalny
    onward = first_legs[-1].arrive + timedelta(minutes=MIN_TRANSFER_MINUTES_WALK)
    onward_time = onward.isoformat().replace("+00:00", "Z")
    second_legs = motis_client.plan_leg(via.stop_id, request.destination_stop_id, onward_time)
    second_legs[0] = replace(second_legs[0], requires_walk=True)

    legs = first_legs + second_legs
    priced = _price_legs(legs, request)
    return build_itinerary(f"Kolej przez {via.label}", priced)


def build_rail_from_alternative_origin_variants(
    request: RouteRequest, alt: AlternativeStop, max_variants: int = 10
) -> list[Itinerary]:
    """Warianty kolejowe zaczynające się z alternatywnego dworca (np. inny dworzec w tym samym
    mieście niż domyślnie skonfigurowany/geokodowany origin_stop_id) — tą samą metodą co
    `build_rail_only_variants`, tylko dla przestawionego origin."""
    alt_request = replace(
        request, origin_stop_id=alt.stop_id, origin_label=f"{request.origin_label} ({alt.label})"
    )
    return build_rail_only_variants(alt_request, max_variants=max_variants)


def build_rail_from_alternative_destination_variants(
    request: RouteRequest, alt: AlternativeStop, max_variants: int = 10
) -> list[Itinerary]:
    """Jak `build_rail_from_alternative_origin_variants`, ale dla alternatywnego dworca
    docelowego."""
    alt_request = replace(
        request,
        destination_stop_id=alt.stop_id,
        destination_label=f"{request.destination_label} ({alt.label})",
    )
    return build_rail_only_variants(alt_request, max_variants=max_variants)


HUB_LEG_ALTERNATIVES = 3  # ile alternatywnych itinerariów MOTIS sprawdzamy dla KAŻDEGO
# dojazdu/odjazdu z huba (patrz _best_overall) — nie tylko najszybszy fragment


def _best_overall(itineraries: list[Itinerary]) -> Itinerary:
    """Spośród kilku pełnych itinerariów, różniących się tylko wyborem dojazdu/odjazdu z huba,
    wybiera najlepszy CAŁOŚCIOWO: wykonalne przed niewykonalnymi, a wśród wykonalnych najniższy
    value_score (cena + czas + kary za ryzykowne przesiadki, patrz model.py::Itinerary.value_score).
    Najszybszy POJEDYNCZY fragment (dojazd albo odjazd) czasem ma ciaśniejszą/ryzykowną
    przesiadkę albo droższy bilet niż odrobinę wolniejsza alternatywa, która wygrywa całościowo."""
    return min(itineraries, key=lambda it: (it.is_infeasible, it.value_score))


def build_rail_flight_rail_variant(request: RouteRequest, hub: HubConfig) -> Itinerary:
    """Kolej (origin -> lotnisko wylotu) + lot + kolej (lotnisko przylotu -> destination).

    Dojazd i odjazd z huba sprawdzają po HUB_LEG_ALTERNATIVES alternatywnych itinerariów MOTIS
    (patrz plan_leg_candidates) zamiast brać automatycznie najszybszy, i spośród wszystkich
    zbudowanych kombinacji wybierają najlepszą całościowo (_best_overall)."""
    legs: list[Leg] = []
    if hub.origin_rail_access_stop_id:
        access_options = motis_client.plan_leg_candidates(
            request.origin_stop_id,
            hub.origin_rail_access_stop_id,
            request.motis_time,
            max_candidates=HUB_LEG_ALTERNATIVES,
        )
        access_options = [o for o in access_options if _departs_on_request_date(o, request)]
        if not access_options:
            raise MotisError(
                f"Brak dojazdu do {hub.origin_rail_access_stop_id} w dniu {request.date}."
            )
    else:
        access_options = [[]]  # brak dojazdu kolejowego do lotniska — jedna "pusta" opcja

    candidates: list[Itinerary] = []
    for access_legs in access_options:
        if access_legs:
            flight_depart = access_legs[-1].arrive + timedelta(
                minutes=150
            )  # bufor: odprawa/security
        else:
            flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))

        flight_leg = build_flight_leg(hub.origin_iata, hub.destination_iata, flight_depart)
        onward_time = (flight_leg.arrive + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
        onward_options = motis_client.plan_leg_candidates(
            hub.destination_rail_access_stop_id,
            request.destination_stop_id,
            onward_time,
            max_candidates=HUB_LEG_ALTERNATIVES,
        )
        for onward_legs in onward_options:
            legs = list(access_legs) + [flight_leg] + onward_legs
            priced = _price_legs(legs, request)
            candidates.append(build_itinerary(f"Kolej + lot ({hub.label}) + kolej lokalna", priced))

    return _best_overall(candidates)


def build_flight_regional_variant(request: RouteRequest, hub: HubConfig) -> Itinerary:
    """Lot (z lotniska blisko origin, bez kolei dojazdowej) + kolej lokalna do destination.

    Odjazd z huba sprawdza po HUB_LEG_ALTERNATIVES alternatywnych itinerariów MOTIS (patrz
    build_rail_flight_rail_variant) zamiast brać automatycznie najszybszy."""
    flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))
    flight_leg = build_flight_leg(hub.origin_iata, hub.destination_iata, flight_depart)

    onward_time = (flight_leg.arrive + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
    onward_options = motis_client.plan_leg_candidates(
        hub.destination_rail_access_stop_id,
        request.destination_stop_id,
        onward_time,
        max_candidates=HUB_LEG_ALTERNATIVES,
    )

    candidates = []
    for onward_legs in onward_options:
        priced = _price_legs([flight_leg] + onward_legs, request)
        candidates.append(build_itinerary(f"Lot ({hub.label}) + transport regionalny", priced))

    return _best_overall(candidates)


def _infeasible_reason(itinerary: Itinerary) -> str:
    reasons = "; ".join(w.reason for w in itinerary.transfer_warnings if w.infeasible)
    return f"Odrzucony: przesiadka niewykonalna fizycznie. {reasons}"


def generate_variants(
    request: RouteRequest,
    rail_flight_rail_hubs: list[HubConfig] | None = None,
    flight_regional_hubs: list[HubConfig] | None = None,
    via_hub_stops: list[AlternativeStop] | None = None,
    alternative_origin_stops: list[AlternativeStop] | None = None,
    alternative_destination_stops: list[AlternativeStop] | None = None,
) -> tuple[list[Itinerary], list[SkippedVariant]]:
    """Generuje wszystkie warianty dla request + skonfigurowane huby/alternatywy. Warianty,
    których nie udało się zbudować (np. brak tokena Travelpayouts, MOTIS nie znalazł
    połączenia), lądują w SkippedVariant z powodem, zamiast przerywać cały proces.

    rail_flight_rail_hubs: huby dla wariantu "kolej + lot + kolej lokalna" (wymagają dojazdu
    kolejowego do lotniska wylotu, hub.origin_rail_access_stop_id).
    flight_regional_hubs: huby dla wariantu "lot + transport regionalny" (lotnisko wylotu
    zakładane jako dostępne bez dalekiego dojazdu kolejowego z origin_stop_id).
    via_hub_stops: alternatywne miasta graniczne/węzły do jawnego przejechania (origin -> via
    -> destination), gdyby MOTIS w jednym zapytaniu origin->destination nie faworyzował takiej
    trasy w topowych itinerariach.
    alternative_origin_stops / alternative_destination_stops: alternatywne dworce startu/mety
    (np. inny dworzec w tym samym mieście niż domyślnie skonfigurowany).

    Wszystkie warianty kolejowe (główne zapytanie + via_hub_stops + alternatywne dworce) są
    odchudzane WSPÓLNYM dedup po trasie (patrz `_legs_signature`), więc ta sama fizyczna trasa
    znaleziona kilkoma drogami trafia do wyniku tylko raz.
    """
    built: list[Itinerary] = []
    skipped: list[SkippedVariant] = []
    seen_rail_signatures: set = set()

    try:
        built.extend(build_rail_only_variants(request, seen_signatures=seen_rail_signatures))
    except MotisError as exc:
        skipped.append(SkippedVariant("Tylko kolej", str(exc)))

    for via in via_hub_stops or []:
        label = f"Kolej przez {via.label}"
        try:
            candidate = build_rail_via_stop_variant(request, via)
            signature = _legs_signature([pl.leg for pl in candidate.legs])
            if signature in seen_rail_signatures:
                continue
            seen_rail_signatures.add(signature)
            if candidate.is_infeasible:
                skipped.append(SkippedVariant(label, _infeasible_reason(candidate)))
            else:
                built.append(candidate)
        except MotisError as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    for alt in alternative_origin_stops or []:
        label = f"Tylko kolej (start: {alt.label})"
        try:
            for candidate in build_rail_from_alternative_origin_variants(request, alt):
                signature = _legs_signature([pl.leg for pl in candidate.legs])
                if signature in seen_rail_signatures:
                    continue
                seen_rail_signatures.add(signature)
                built.append(candidate)
        except MotisError as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    for alt in alternative_destination_stops or []:
        label = f"Tylko kolej (koniec: {alt.label})"
        try:
            for candidate in build_rail_from_alternative_destination_variants(request, alt):
                signature = _legs_signature([pl.leg for pl in candidate.legs])
                if signature in seen_rail_signatures:
                    continue
                seen_rail_signatures.add(signature)
                built.append(candidate)
        except MotisError as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    for hub in rail_flight_rail_hubs or []:
        label = f"Kolej + lot ({hub.label}) + kolej lokalna"
        try:
            candidate = build_rail_flight_rail_variant(request, hub)
            if candidate.is_infeasible:
                skipped.append(SkippedVariant(label, _infeasible_reason(candidate)))
            else:
                built.append(candidate)
        except (MotisError, TravelpayoutsError) as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    for hub in flight_regional_hubs or []:
        label = f"Lot ({hub.label}) + transport regionalny"
        try:
            candidate = build_flight_regional_variant(request, hub)
            if candidate.is_infeasible:
                skipped.append(SkippedVariant(label, _infeasible_reason(candidate)))
            else:
                built.append(candidate)
        except (MotisError, TravelpayoutsError) as exc:
            skipped.append(SkippedVariant(label, str(exc)))

    return built, skipped
