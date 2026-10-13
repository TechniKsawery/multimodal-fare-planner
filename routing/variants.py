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
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

from fares.model import DiscountProfile
from i18n import Joined, Msg, exc_text, transport_mode_name

from . import motis_client, pricing
from .currency import normalize_currency
from .model import Itinerary, Leg, LegMode, OtherDayVariant, SkippedVariant
from .motis_client import MotisError, StopRef
from .scoring import build_itinerary
from .transfers import (
    MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT,
    MIN_TRANSFER_MINUTES_WALK,
    flight_to_rail_minimum,
)

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
    checked_baggage: bool = True  # True = bagaż rejestrowany (w cenie lotu, dłuższy bufor po
    # lądowaniu); False = tylko podręczny (bez opłaty za bagaż, krótszy bufor)

    def __post_init__(self) -> None:
        # waluta bez kursu = od razu UnsupportedCurrencyError, a nie błąd w głębi wyceny lotu
        self.flight_currency = normalize_currency(self.flight_currency)

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
        str | StopRef | None
    )  # stacja przy lotnisku wylotu (np. StopRef("Warszawa Lotnisko Chopina", ...))
    destination_rail_access_stop_id: (
        str | StopRef  # stacja przy/blisko lotniska przylotu (np. StopRef("Dortmund Hbf", ...))
    )


def build_flight_leg(
    origin_iata: str, destination_iata: str, depart_at: datetime, checked_baggage: bool = True
) -> Leg:
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
            "checked_baggage": checked_baggage,
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


# Sekcja "Najbliższe połączenia w innym dniu" (patrz OtherDayVariant): maks. tyle wariantów i tylko
# z dni odległych od zapytanej daty o nie więcej niż tyle dni — to podpowiedź, nie przeszukiwanie
# kalendarza.
OTHER_DAY_MAX_VARIANTS = 3
OTHER_DAY_MAX_DAYS = 3


def _other_day_variants(
    request: RouteRequest, other_day_options: list[list[Leg]]
) -> list[OtherDayVariant]:
    """Do OTHER_DAY_MAX_VARIANTS najbliższych (wg odjazdu) wykonalnych połączeń z dni innych niż
    zapytany, nie dalszych niż OTHER_DAY_MAX_DAYS dni od niego. Cena i wykonalność liczone tą samą
    drogą co dla głównych wariantów (`_price_legs` + `build_itinerary`)."""
    requested = date_cls.fromisoformat(request.date)
    found: list[OtherDayVariant] = []
    for legs in sorted(other_day_options, key=lambda ls: ls[0].depart):
        day = legs[0].depart.astimezone(LOCAL_TIMEZONE).date()
        offset = (day - requested).days
        if offset == 0 or abs(offset) > OTHER_DAY_MAX_DAYS:
            continue
        transit = [l for l in legs if l.mode is not LegMode.WALK]
        if not transit:  # sam spacer w innym dniu nie jest "połączeniem"
            continue
        name = _rail_only_name(transit)
        candidate = build_itinerary(name, _price_legs(legs, request))
        if candidate.is_infeasible:
            continue
        found.append(OtherDayVariant(candidate, day.isoformat(), request.date, offset))
        if len(found) >= OTHER_DAY_MAX_VARIANTS:
            break
    return found


def _rail_only_name(transit: list[Leg]) -> Msg:
    """Nazwa wariantu kolejowego z RODZAJAMI transportu (tłumaczonymi), a nie surowymi kluczami
    MOTIS typu `regional_rail`."""
    modes_used = sorted({l.extra.get("motis_mode", "RAIL") for l in transit})
    return Msg(
        "variant.rail_only",
        modes=Joined((transport_mode_name(m) for m in modes_used), "/"),
        transfers=len(transit) - 1,
    )


def _legs_signature(legs: list[Leg]) -> tuple[tuple[str, str], ...]:
    """Sygnatura trasy (sekwencja origin/destination nazw odcinków) do dedup: ta sama fizyczna
    trasa znaleziona przez różne zapytania (główne + alternatywne huby/dworce) liczy się raz."""
    return tuple((l.origin_name, l.destination_name) for l in legs)


def build_rail_only_variants(
    request: RouteRequest,
    max_variants: int = 30,
    seen_signatures: set | None = None,
    other_day_out: list[OtherDayVariant] | None = None,
) -> list[Itinerary]:
    """Do max_variants (domyślnie wszystkie z 30 zwróconych) wariantów kolejowych z JEDNEGO zapytania do MOTIS (różne itineraria,
    które silnik i tak zwraca — nie przeszukujemy innych hubów).

    seen_signatures: opcjonalny współdzielony zbiór sygnatur tras (patrz `_legs_signature`) —
    pozwala `generate_variants` odchudzać wyniki z alternatywnych hubów/dworców względem
    już znalezionych tras, bez duplikatów. Zbiór jest modyfikowany w miejscu.

    other_day_out: opcjonalna lista wyjściowa (modyfikowana w miejscu). Gdy MOTIS zwrócił
    połączenia, ale WSZYSTKIE w innym dniu niż zapytany, trafiają tu najbliższe z nich (patrz
    `_other_day_variants`); poza tym przypadkiem lista zostaje nietknięta. Te warianty NIE są
    częścią zwracanego wyniku."""
    all_legs_options = motis_client.all_itineraries_as_legs(
        request.origin_stop_id, request.destination_stop_id, request.motis_time
    )

    if seen_signatures is None:
        seen_signatures = set()
    variants: list[Itinerary] = []
    other_day = infeasible = duplicates = 0
    other_day_options: list[list[Leg]] = []
    for legs in sorted(all_legs_options, key=lambda ls: (ls[-1].arrive - ls[0].depart)):
        if not _departs_on_request_date(legs, request):
            other_day += 1
            other_day_options.append(legs)
            continue
        signature = _legs_signature(legs)
        if signature in seen_signatures:
            duplicates += 1
            continue
        seen_signatures.add(signature)

        transit = [l for l in legs if l.mode is not LegMode.WALK]
        # bez odcinków z taborem MOTIS `direct`: cały dystans pieszo (punkty w tym samym mieście)
        name = _rail_only_name(transit) if transit else Msg("variant.walk")
        priced = _price_legs(legs, request)
        candidate = build_itinerary(name, priced)
        if candidate.is_infeasible:  # przesiadka poniżej absolutnego minimum — odrzucamy
            infeasible += 1
            continue
        variants.append(candidate)

        if len(variants) >= max_variants:
            break

    all_in_other_day = bool(all_legs_options) and other_day == len(all_legs_options)
    if other_day_out is not None and all_in_other_day:
        other_day_out.extend(_other_day_variants(request, other_day_options))
    if not variants and not duplicates:
        raise MotisError(_no_rail_reason(request, len(all_legs_options), other_day, infeasible))
    return variants


def _no_rail_reason(request: RouteRequest, total: int, other_day: int, infeasible: int) -> Msg:
    """Jawny powód pustego wyniku zapytania origin->destination (zamiast cichej pustej listy)."""
    if total == 0:
        return Msg("skip.no_connections_at_all", time=request.departure_time, date=request.date)
    parts = []
    if other_day:
        parts.append(Msg("skip.part_other_day", n=other_day, date=request.date))
    if infeasible:
        parts.append(Msg("skip.part_infeasible", n=infeasible))
    return Msg("skip.no_usable_connections", total=total, parts=Joined(parts))


@dataclass
class AlternativeStop:
    """Alternatywny przystanek/dworzec/węzeł do jawnego wypróbowania obok głównego origin/
    destination z RouteRequest — albo jako inny dworzec w tym samym mieście (start/koniec),
    albo jako miasto graniczne/węzeł pośredni, przez które MOTIS mógłby nie poprowadzić trasy
    w swoich topowych itinerariach dla zapytania origin->destination wprost."""

    label: str
    stop_id: str | StopRef


# Limit objazdu dla wariantu "Kolej przez <węzeł>" (VIA_HUB_STOPS, dziś Poznań Główny). Bez niego
# zapytanie bez bezpośredniej trasy w MOTIS (Kraków -> Gorlice) budowało absurd: Kraków ->
# Wrocław -> Poznań -> Wrocław -> Tarnów -> Stróże -> Gorlice, 32 h i 5 przesiadek, bo "przez
# Poznań" to dwa niezależne zapytania spięte węzłem i nikt nie pytał, czy węzeł jest po drodze.
#
# Próg 1.5: (origin->via + via->destination w linii prostej) <= 1.5 x origin->destination.
# Skąd: współczynniki dla Poznania na realnych korytarzach (haversine, centra miast):
#   Lublin->Berlin 1.00, Lublin->Gelsenkirchen 1.02, Warszawa->Berlin 1.00, Kraków->Berlin 1.08,
#   Katowice->Berlin 1.12, Gdańsk->Berlin 1.20, Wrocław->Gelsenkirchen 1.19, Wrocław->Berlin 1.29
#   — to trasy, na których Poznań leży po drodze albo jest uczciwym lekkim łukiem (maks. 1.29).
#   Objazdy bez sensu: Zielona Góra->Berlin 2.19, Kraków->Warszawa 2.44, Szczecin->Berlin 3.40,
#   Kraków->Gorlice 7.74. Próg 1.5 siedzi w luce między jednymi a drugimi (z zapasem ~0.2 nad
#   najgorszą sensowną trasą) i jest ten sam co HUB_MAX_DETOUR_RATIO dla hubów lotniczych, więc
#   obie reguły "objazdu" mają jedną skalę. Świadomy koszt: Gdańsk->Szczecin (1.53) odpada
#   z wariantu przez Poznań — tę relację i tak pokrywa główne zapytanie origin->destination do MOTIS.
VIA_HUB_MAX_DETOUR_RATIO = 1.5
# Dwa punkty trasy bliżej niż tyle uznajemy za TĘ SAMĄ stację (np. dwa wejścia/perony tego samego
# dworca mają nieco inne współrzędne w GTFS); różne dworce w dużym mieście są od siebie dalej.
SAME_STATION_RADIUS_KM = 0.5


def via_hub_detour_reason(origin, via, destination) -> Msg | None:
    """Powód odrzucenia wariantu przez węzeł `via`, gdy origin->via->destination w linii prostej
    przekracza VIA_HUB_MAX_DETOUR_RATIO x origin->destination; None, gdy węzeł jest sensowny.
    Brak któregokolwiek ze współrzędnych = nie filtrujemy (jak `hub_is_detour`)."""
    if not (origin and via and destination):
        return None
    h = motis_client.haversine_km
    direct = h(*origin, *destination)
    path = h(*origin, *via) + h(*via, *destination)
    if path > VIA_HUB_MAX_DETOUR_RATIO * max(direct, 1.0):
        return Msg(
            "skip.via_detour",
            path=f"{path:.0f}",
            direct=f"{direct:.0f}",
            ratio=VIA_HUB_MAX_DETOUR_RATIO,
        )
    return None


def _transit_points(legs: list[Leg]) -> list[tuple[str, tuple[float, float] | None]]:
    """Kolejne punkty trasy po odcinkach z taborem (bez dojść): start pierwszego odcinka, potem
    koniec każdego. Zwraca (nazwa, współrzędne albo None)."""
    transit = [leg for leg in legs if leg.mode is not LegMode.WALK]
    if not transit:
        return []

    def coords(leg: Leg, prefix: str):
        lat, lon = leg.extra.get(f"{prefix}_lat"), leg.extra.get(f"{prefix}_lon")
        return (lat, lon) if lat is not None and lon is not None else None

    points = [(transit[0].origin_name, coords(transit[0], "origin"))]
    points += [(leg.destination_name, coords(leg, "destination")) for leg in transit]
    return points


def revisited_station_reason(legs: list[Leg]) -> Msg | None:
    """Powód odrzucenia, gdy trasa przejeżdża dwa razy przez tę samą stację (np. Kraków ->
    Wrocław -> Poznań -> Wrocław -> ...: powrót tą samą drogą zamiast jazdy do przodu).
    Ta sama stacja = te same współrzędne w promieniu SAME_STATION_RADIUS_KM, a bez współrzędnych —
    ta sama nazwa. Przesiadka w jednym miejscu (koniec odcinka i start następnego) to nie powrót."""
    points = _transit_points(legs)
    for j in range(1, len(points)):
        for i in range(j):
            name_i, xy_i = points[i]
            name_j, xy_j = points[j]
            if xy_i and xy_j:
                same = motis_client.haversine_km(*xy_i, *xy_j) <= SAME_STATION_RADIUS_KM
            else:
                same = name_i.strip().casefold() == name_j.strip().casefold()
            if same:
                return Msg("skip.revisited", station=name_j)
    return None


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
    do itinerary z jednego zapytania nie wiemy, czy to ten sam peron.

    Objazd (węzeł nie po drodze albo powrót tą samą stacją) kończy się MotisError z powodem —
    `generate_variants` wpisuje go do `skipped`. Limit sprawdzamy najpierw ze współrzędnych
    zapytania (bez wołania MOTIS), a po zbudowaniu odcinków jeszcze raz ze współrzędnych
    odcinków, bo przy zapytaniu z samymi stopId MOTIS współrzędnych zapytania nie znamy."""
    via_xy = _coords_of(via.stop_id)
    origin_xy = _coords_of(request.origin_stop_id)
    dest_xy = _coords_of(request.destination_stop_id)
    reason = via_hub_detour_reason(origin_xy, via_xy, dest_xy)
    if reason:
        raise MotisError(reason)

    via_id = motis_client.stop_id(via.stop_id)
    first_legs = motis_client.plan_leg(request.origin_stop_id, via_id, request.motis_time)
    if not _departs_on_request_date(first_legs, request):
        raise MotisError(Msg("skip.no_via_connection", stop=via.label, date=request.date))
    # bufor na przesiadkę w węźle via — bez niego MOTIS podaje odjazd tuż po przyjeździe
    # i wariant odpada jako fizycznie niewykonalny
    onward = first_legs[-1].arrive + timedelta(minutes=MIN_TRANSFER_MINUTES_WALK)
    onward_time = onward.isoformat().replace("+00:00", "Z")
    second_legs = motis_client.plan_leg(via_id, request.destination_stop_id, onward_time)
    second_legs[0] = replace(second_legs[0], requires_walk=True)

    legs = first_legs + second_legs
    points = _transit_points(legs)
    if points:
        # współrzędne z odcinków uzupełniają to, czego nie dało się wyczytać z samego zapytania
        origin_xy = origin_xy or points[0][1]
        dest_xy = dest_xy or points[-1][1]
        first_points = _transit_points(first_legs)
        via_xy = via_xy or (first_points[-1][1] if first_points else None)
    reason = via_hub_detour_reason(origin_xy, via_xy, dest_xy) or revisited_station_reason(legs)
    if reason:
        raise MotisError(reason)

    priced = _price_legs(legs, request)
    return build_itinerary(Msg("variant.via", via=via.label), priced)


def build_rail_from_alternative_origin_variants(
    request: RouteRequest, alt: AlternativeStop, max_variants: int = 10
) -> list[Itinerary]:
    """Warianty kolejowe zaczynające się z alternatywnego dworca (np. inny dworzec w tym samym
    mieście niż domyślnie skonfigurowany/geokodowany origin_stop_id) — tą samą metodą co
    `build_rail_only_variants`, tylko dla przestawionego origin."""
    alt_request = replace(
        request,
        origin_stop_id=motis_client.stop_id(alt.stop_id),
        origin_label=f"{request.origin_label} ({alt.label})",
    )
    return build_rail_only_variants(alt_request, max_variants=max_variants)


def build_rail_from_alternative_destination_variants(
    request: RouteRequest, alt: AlternativeStop, max_variants: int = 10
) -> list[Itinerary]:
    """Jak `build_rail_from_alternative_origin_variants`, ale dla alternatywnego dworca
    docelowego."""
    alt_request = replace(
        request,
        destination_stop_id=motis_client.stop_id(alt.stop_id),
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
    destination_access_id = motis_client.stop_id(hub.destination_rail_access_stop_id)
    if hub.origin_rail_access_stop_id:
        origin_access_id = motis_client.stop_id(hub.origin_rail_access_stop_id)
        access_options = motis_client.plan_leg_candidates(
            request.origin_stop_id,
            origin_access_id,
            request.motis_time,
            max_candidates=HUB_LEG_ALTERNATIVES,
        )
        access_options = [o for o in access_options if _departs_on_request_date(o, request)]
        if not access_options:
            raise MotisError(Msg("skip.no_access", stop=origin_access_id, date=request.date))
    else:
        access_options = [[]]  # brak dojazdu kolejowego do lotniska — jedna "pusta" opcja

    candidates: list[Itinerary] = []
    for access_legs in access_options:
        if access_legs:
            flight_depart = access_legs[-1].arrive + timedelta(
                minutes=MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT
            )  # bufor: odprawa/security
        else:
            flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))

        flight_leg = build_flight_leg(
            hub.origin_iata, hub.destination_iata, flight_depart, request.checked_baggage
        )
        landing_buffer = timedelta(minutes=flight_to_rail_minimum(request.checked_baggage))
        onward_time = (flight_leg.arrive + landing_buffer).isoformat().replace("+00:00", "Z")
        onward_options = motis_client.plan_leg_candidates(
            destination_access_id,
            request.destination_stop_id,
            onward_time,
            max_candidates=HUB_LEG_ALTERNATIVES,
        )
        for onward_legs in onward_options:
            legs = list(access_legs) + [flight_leg] + onward_legs
            priced = _price_legs(legs, request)
            candidates.append(
                build_itinerary(Msg("variant.rail_flight_rail", hub=hub.label), priced)
            )

    return _best_overall(candidates)


def build_flight_regional_variant(request: RouteRequest, hub: HubConfig) -> Itinerary:
    """Lot (z lotniska blisko origin, bez kolei dojazdowej) + kolej lokalna do destination.

    Odjazd z huba sprawdza po HUB_LEG_ALTERNATIVES alternatywnych itinerariów MOTIS (patrz
    build_rail_flight_rail_variant) zamiast brać automatycznie najszybszy."""
    flight_depart = datetime.fromisoformat(request.motis_time.replace("Z", "+00:00"))
    flight_leg = build_flight_leg(
            hub.origin_iata, hub.destination_iata, flight_depart, request.checked_baggage
        )

    landing_buffer = timedelta(minutes=flight_to_rail_minimum(request.checked_baggage))
    onward_time = (flight_leg.arrive + landing_buffer).isoformat().replace("+00:00", "Z")
    onward_options = motis_client.plan_leg_candidates(
        motis_client.stop_id(hub.destination_rail_access_stop_id),
        request.destination_stop_id,
        onward_time,
        max_candidates=HUB_LEG_ALTERNATIVES,
    )

    candidates = []
    for onward_legs in onward_options:
        priced = _price_legs([flight_leg] + onward_legs, request)
        candidates.append(build_itinerary(Msg("variant.flight_regional", hub=hub.label), priced))

    return _best_overall(candidates)


# Huby lot<->kolej są konfigurowane na stałe (demo_route.py, pod Lublin->Gelsenkirchen), a
# generate_variants stosuje je do KAŻDEGO zapytania. Bez filtra geograficznego Warszawa->Düsseldorf
# trafiała też do trasy Lublin->Berlin (lot na zachód, potem pociąg 326 min z powrotem na wschód).
HUB_MAX_DETOUR_RATIO = 1.5  # dojazd + lot + odjazd (linia prosta) <= 1.5 x origin->destination


def _coords_of(place: str | StopRef) -> tuple[float, float] | None:
    if isinstance(place, StopRef):
        return place.lat, place.lon
    try:
        lat, lon = (float(x) for x in place.split(","))
        return lat, lon
    except (ValueError, AttributeError):
        return None


def _endpoints(request: RouteRequest, built: list[Itinerary]):
    """Współrzędne origin/destination: z "lat,lon" w request albo z odcinków wariantów kolejowych
    (zbudowanych wcześniej z TEGO samego zapytania). None, gdy nie da się ustalić."""
    origin = _coords_of(request.origin_stop_id)
    dest = _coords_of(request.destination_stop_id)
    for it in built:
        transit = [pl.leg for pl in it.legs if pl.leg.extra.get("origin_lat") is not None]
        if not transit:
            continue
        origin = origin or (transit[0].extra["origin_lat"], transit[0].extra["origin_lon"])
        dest = dest or (transit[-1].extra["destination_lat"], transit[-1].extra["destination_lon"])
        break
    return origin, dest


def hub_is_detour(origin, destination, hub: HubConfig) -> bool:
    """True, gdy hub lot<->kolej jest ewidentnym objazdem względem linii origin->destination:
    lotnisko przylotu nie jest bliżej celu niż lotnisko wylotu, albo łączna droga w linii
    prostej przekracza HUB_MAX_DETOUR_RATIO x bezpośrednią. Brak współrzędnych = nie filtrujemy."""
    air_from = _coords_of(hub.origin_rail_access_stop_id) if hub.origin_rail_access_stop_id else None
    air_to = _coords_of(hub.destination_rail_access_stop_id)
    if not (origin and destination and air_to):
        return False
    h = motis_client.haversine_km
    direct = h(*origin, *destination)
    start = air_from or origin
    if h(*air_to, *destination) >= h(*start, *destination):
        return True
    path = h(*origin, *start) + h(*start, *air_to) + h(*air_to, *destination)
    return path > HUB_MAX_DETOUR_RATIO * max(direct, 1.0)


def _infeasible_reason(itinerary: Itinerary) -> Msg:
    reasons = Joined((w.reason for w in itinerary.transfer_warnings if w.infeasible), "; ")
    return Msg("skip.infeasible", reasons=reasons)


def generate_variants(
    request: RouteRequest,
    rail_flight_rail_hubs: list[HubConfig] | None = None,
    flight_regional_hubs: list[HubConfig] | None = None,
    via_hub_stops: list[AlternativeStop] | None = None,
    alternative_origin_stops: list[AlternativeStop] | None = None,
    alternative_destination_stops: list[AlternativeStop] | None = None,
    hub_discovery=None,
    other_day_out: list[OtherDayVariant] | None = None,
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

    other_day_out: opcjonalna lista wyjściowa (modyfikowana w miejscu) na sekcję "Najbliższe
    połączenia w innym dniu". Wypełniana tylko, gdy wynik jest pusty (`built == []`), a zapytanie
    kolejowe origin->destination zwróciło połączenia wyłącznie w innych dniach niż zapytany.
    Te warianty nigdy nie trafiają do `built`, więc nie wchodzą do żadnego rankingu.
    """
    built: list[Itinerary] = []
    skipped: list[SkippedVariant] = []
    seen_rail_signatures: set = set()
    rail_other_day: list[OtherDayVariant] = []

    try:
        built.extend(
            build_rail_only_variants(
                request, seen_signatures=seen_rail_signatures, other_day_out=rail_other_day
            )
        )
    except MotisError as exc:
        skipped.append(SkippedVariant(Msg("variant.rail_only_plain"), exc_text(exc)))

    for via in via_hub_stops or []:
        label = Msg("variant.via", via=via.label)
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
            skipped.append(SkippedVariant(label, exc_text(exc)))

    for alt in alternative_origin_stops or []:
        label = Msg("variant.rail_start", stop=alt.label)
        try:
            for candidate in build_rail_from_alternative_origin_variants(request, alt):
                signature = _legs_signature([pl.leg for pl in candidate.legs])
                if signature in seen_rail_signatures:
                    continue
                seen_rail_signatures.add(signature)
                built.append(candidate)
        except MotisError as exc:
            skipped.append(SkippedVariant(label, exc_text(exc)))

    for alt in alternative_destination_stops or []:
        label = Msg("variant.rail_end", stop=alt.label)
        try:
            for candidate in build_rail_from_alternative_destination_variants(request, alt):
                signature = _legs_signature([pl.leg for pl in candidate.legs])
                if signature in seen_rail_signatures:
                    continue
                seen_rail_signatures.add(signature)
                built.append(candidate)
        except MotisError as exc:
            skipped.append(SkippedVariant(label, exc_text(exc)))

    origin_ll, dest_ll = _endpoints(request, built)

    # hub_discovery(origin_ll, dest_ll, skip_pairs) -> huby z lotniskami dobranymi do miast
    # startu/celu (routing/airports.py::discover_hubs); błąd API lotów = brak dynamicznych hubów.
    discovered: list[HubConfig] = []
    if hub_discovery and not (origin_ll and dest_ll):
        skipped.append(
            SkippedVariant(Msg("variant.airport_selection"), Msg("skip.no_coordinates"))
        )
    elif hub_discovery:
        static_pairs = {(h.origin_iata, h.destination_iata) for h in rail_flight_rail_hubs or []}
        try:
            discovered, rejected = hub_discovery(origin_ll, dest_ll, static_pairs)
            for name, reason in rejected:
                skipped.append(SkippedVariant(name, Msg("skip.skipped", reason=reason)))
        except Exception as exc:  # np. błąd tabeli lotnisk
            skipped.append(
                SkippedVariant(
                    Msg("variant.airport_selection"), Msg("skip.discovery_failed", error=str(exc))
                )
            )
    rail_flight_rail_hubs = list(rail_flight_rail_hubs or []) + discovered

    for hub in rail_flight_rail_hubs or []:
        label = Msg("variant.rail_flight_rail", hub=hub.label)
        if hub_is_detour(origin_ll, dest_ll, hub):
            skipped.append(SkippedVariant(label, Msg("skip.hub_detour")))
            continue
        try:
            candidate = build_rail_flight_rail_variant(request, hub)
            if candidate.is_infeasible:
                skipped.append(SkippedVariant(label, _infeasible_reason(candidate)))
            else:
                built.append(candidate)
        except MotisError as exc:
            reason = exc_text(exc)
            if hub in discovered:
                reason = Msg(
                    "skip.no_transit_access",
                    origin=hub.origin_iata,
                    destination=hub.destination_iata,
                    reason=reason,
                )
            skipped.append(SkippedVariant(label, reason))
        except TravelpayoutsError as exc:
            skipped.append(SkippedVariant(label, exc_text(exc)))

    for hub in flight_regional_hubs or []:
        label = Msg("variant.flight_regional", hub=hub.label)
        if hub_is_detour(origin_ll, dest_ll, hub):
            skipped.append(SkippedVariant(label, Msg("skip.hub_detour")))
            continue
        try:
            candidate = build_flight_regional_variant(request, hub)
            if candidate.is_infeasible:
                skipped.append(SkippedVariant(label, _infeasible_reason(candidate)))
            else:
                built.append(candidate)
        except (MotisError, TravelpayoutsError) as exc:
            skipped.append(SkippedVariant(label, exc_text(exc)))

    if other_day_out is not None and not built:
        other_day_out.extend(rail_other_day)
    return built, skipped
