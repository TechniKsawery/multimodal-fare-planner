"""Wycena pojedynczego odcinka: dispatch do fares/ (kolej) albo flights/ (lot)."""

import re

from fares import estimate_price as fares_estimate_price
from fares.international_pkp import estimate_pkp_offer, spi_range_for_segment
from fares.model import Carrier, DiscountProfile, PriceEstimate, PriceType, Segment
from flights import ExtrasProfile, FlightSegment
from flights import estimate_price as flights_estimate_price
from flights.extras import get_baggage_by_airline
from flights.extras import get_extras as flights_get_extras

from .currency import convert as convert_currency
from .model import Leg, LegMode, PricedLeg
from .motis_client import haversine_km

GENERIC_FALLBACK_PLN_PER_KM = 0.35
"""Bardzo zgrubny szacunek na km, używany TYLKO gdy żaden moduł taryf nie obejmuje przewoźnika
(nieznana nazwa agencji z MOTIS) albo kalkulator odrzucił segment — patrz README.md."""

DEFAULT_BAGGAGE_ESTIMATE_PLN = 150.0
"""Szacunkowy koszt pierwszego bagażu rejestrowanego, gdy relacja nie ma wpisu w
flights/data/extras_placeholder.json — typowa cena bagażu rejestrowanego do ok. 20 kg u
tanich linii (Ryanair/Wizz Air) na trasach PL-DE, SZACUNEK, nie oficjalny cennik."""


def _flight_baggage_only_extras(origin: str, destination: str, currency: str) -> ExtrasProfile:
    """Tylko koszt bagażu rejestrowanego (z placeholderowej tabeli flights/, albo szacunek
    domyślny gdy relacja nieznana) — BEZ dojazdu na lotnisko / transferu z lotniska.

    W wariantach mieszanych (kolej + lot + kolej) dojazd na lotnisko i transfer z lotniska do
    miasta docelowego są już osobnymi, realnie wycenionymi odcinkami kolejowymi (patrz
    build_rail_flight_rail_variant w variants.py) — doliczenie ich tu drugi raz z tabeli
    flights/ podwójnie liczyłoby ten sam koszt."""
    table_entry = flights_get_extras(origin, destination)
    if table_entry.baggage_cost:
        return ExtrasProfile(
            baggage_cost=table_entry.baggage_cost,
            currency=currency,
            note="Koszt bagażu z placeholderowej tabeli flights/ — nie oficjalny cennik przewoźnika.",
        )
    return ExtrasProfile(
        baggage_cost=DEFAULT_BAGGAGE_ESTIMATE_PLN,
        currency=currency,
        note=(
            f"Brak danych o bagażu dla tej relacji w tabeli flights/ — szacunek domyślny "
            f"({DEFAULT_BAGGAGE_ESTIMATE_PLN:.0f} PLN, typowa cena bagażu rejestrowanego u tanich linii)."
        ),
    )


ZTM_LUBLIN_KEYWORDS = ("lublin", "zditm", "ztm lublin")
"""Nazwy (CAŁE słowa, patrz _matches_any_word) wskazujące na komunikację miejską ZTM Lublin.

Używane TYLKO, gdy odcinek nie ma współrzędnych obu końców — wtedy o mieście decyduje
geografia (CITY_TARIFF_AREAS), a nie nazwa (zob. _city_carrier_for_leg)."""

ZTM_WARSZAWA_KEYWORDS = ("warszawa", "ztm warszawa", "wtp")
MPK_KRAKOW_KEYWORDS = ("kraków", "krakow", "krakowie", "ztp kraków", "ztp krakow", "kmk")
ZTM_POZNAN_KEYWORDS = ("poznań", "poznan", "ztm poznań", "ztm poznan")
MPK_WROCLAW_KEYWORDS = ("wrocław", "wroclaw", "mpk wrocław", "mpk wroclaw")
BVG_BERLIN_KEYWORDS = ("berlin", "bvg")
HVV_KEYWORDS = ("hamburg", "hvv")
MVV_KEYWORDS = ("münchen", "muenchen", "munchen", "mvv")
VRS_KOLN_KEYWORDS = ("köln", "koeln", "koln", "kvb")
"""Słowa kluczowe miast: dopasowywane jako CAŁE słowa (granice słów Unicode), nie fragmenty —
"Krakowskie Przedmieście" (ulica w Warszawie i w Lublinie) NIE pasuje do "krakow", "Berliner
Straße" nie pasuje do "berlin", "Poznańska" nie pasuje do "poznań" (błąd S4 z audytu). Usunięte
nazwy związków obejmujących wiele miast o różnych taryfach: "vbb" (cała Brandenburgia, np.
Cottbus, Frankfurt (Oder)) i "vrs" (m.in. Bonn) — ich obecność w nazwie przewoźnika nie znaczy, że
przejazd jest w Berlinie/Kolonii. Słowa kluczowe są TYLKO fallbackiem, gdy odcinek nie ma
współrzędnych obu końców; normalnie decyduje CITY_TARIFF_AREAS."""


CITY_TARIFF_AREAS: dict[Carrier, tuple[float, float, float]] = {
    Carrier.ZTM_LUBLIN: (51.2465, 22.5684, 12.0),
    Carrier.ZTM_WARSZAWA: (52.2297, 21.0122, 15.0),
    Carrier.MPK_KRAKOW: (50.0614, 19.9366, 13.0),
    Carrier.ZTM_POZNAN: (52.4064, 16.9252, 11.0),
    Carrier.MPK_WROCLAW: (51.1079, 17.0385, 11.0),
    Carrier.BVG_BERLIN: (52.5200, 13.4050, 20.0),
    Carrier.HVV: (53.5511, 9.9937, 12.0),
    Carrier.MVV: (48.1374, 11.5755, 11.0),
    Carrier.VRS_KOLN: (50.9375, 6.9603, 12.0),
}
"""Obszar, w którym stosujemy taryfę miejską danego kalkulatora: (lat, lon) centrum miasta i
promień w km. To PRZYBLIŻENIE granic miasta (koło zamiast granicy administracyjnej/strefy
taryfowej), nie mapa stref — kalkulatory i tak liczą najniższą/miejską strefę (patrz
fares/README.md). Odcinek dostaje taryfę miejską tylko, gdy OBA końce leżą w tym samym kole;
w przeciwnym razie (np. podmiejski autobus) nie zgadujemy strefy i wynik jest oznaczony jako
niepotwierdzony szacunek."""

_CITY_KEYWORDS: tuple[tuple[tuple[str, ...], Carrier], ...] = (
    (ZTM_LUBLIN_KEYWORDS, Carrier.ZTM_LUBLIN),
    (ZTM_WARSZAWA_KEYWORDS, Carrier.ZTM_WARSZAWA),
    (MPK_KRAKOW_KEYWORDS, Carrier.MPK_KRAKOW),
    (ZTM_POZNAN_KEYWORDS, Carrier.ZTM_POZNAN),
    (MPK_WROCLAW_KEYWORDS, Carrier.MPK_WROCLAW),
    (BVG_BERLIN_KEYWORDS, Carrier.BVG_BERLIN),
    (HVV_KEYWORDS, Carrier.HVV),
    (MVV_KEYWORDS, Carrier.MVV),
    (VRS_KOLN_KEYWORDS, Carrier.VRS_KOLN),
)

_DE_CITY_RAIL_CARRIERS = (Carrier.BVG_BERLIN, Carrier.HVV, Carrier.MVV, Carrier.VRS_KOLN)
"""Związki, których taryfa obejmuje też S-Bahn/pociągi regionalne w obrębie miasta (Verbundtarif),
więc stosujemy je również do odcinków, które MOTIS sklasyfikował jako RAIL."""


BER_AIRPORT_AREA = (52.3644, 13.5108, 2.5)
"""Lotnisko BER: (lat, lon) stacji Flughafen BER (Terminal 1-2) i promień w km. BER leży poza
granicą Berlina, w strefie C taryfy VBB (fares/data/bvg_berlin.json::_uwaga: "ABC (z lotniskiem
BER)"), ale w kole BVG_BERLIN z CITY_TARIFF_AREAS — bez tego rozróżnienia odcinek BER ->
centrum dostawał bilet AB (4,00 EUR, który na BER nie obowiązuje) zamiast ABC (5,00 EUR).
Promień celowo mały (granica Berlina jest ok. 3-4 km na północ), więc pozostałe przystanki
strefy C w tym kole (np. Schönefeld, Waßmannsdorf, Teltow) nadal dostają AB — znane
ograniczenie, patrz routing/README.md."""

BER_AIRPORT_KEYWORDS = (
    "flughafen ber",
    "ber airport",
    "airport ber",
    "flughafen berlin brandenburg",
)
"""Nazwy (całe słowa) lotniska BER — używane tylko, gdy odcinek nie ma współrzędnych."""


def _matches_any_word(text: str, keywords: tuple[str, ...]) -> bool:
    """Czy któreś słowo kluczowe występuje w tekście jako CAŁE słowo (nie fragment innego)."""
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text) for k in keywords)


def _leg_endpoints(leg: Leg) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Współrzędne obu końców odcinka z leg.extra (ustawiane przez motis_client) albo None."""
    coords = [leg.extra.get(k) for k in ("origin_lat", "origin_lon", "destination_lat", "destination_lon")]
    if any(c is None for c in coords):
        return None
    o_lat, o_lon, d_lat, d_lon = coords
    return (o_lat, o_lon), (d_lat, d_lon)


def _city_carrier_for_leg(leg: Leg, carriers: tuple[Carrier, ...] | None = None) -> Carrier | None:
    """Taryfa miejska dla odcinka: gdy znamy współrzędne obu końców — WYŁĄCZNIE geografia (oba
    końce w tym samym obszarze z CITY_TARIFF_AREAS); bez współrzędnych — nazwy przewoźnika i
    przystanków dopasowane jako całe słowa. None, gdy nie da się tego ustalić."""
    allowed = carriers or tuple(CITY_TARIFF_AREAS)
    endpoints = _leg_endpoints(leg)
    if endpoints is not None:
        for carrier in allowed:
            lat, lon, radius_km = CITY_TARIFF_AREAS[carrier]
            if all(haversine_km(p_lat, p_lon, lat, lon) <= radius_km for p_lat, p_lon in endpoints):
                return carrier
        return None
    tekst = f"{leg.carrier_name} {leg.origin_name} {leg.destination_name}".lower()
    for keywords, carrier in _CITY_KEYWORDS:
        if carrier in allowed and _matches_any_word(tekst, keywords):
            return carrier
    return None


def _bvg_tariff_zone(leg: Leg) -> str | None:
    """Strefa "ABC", gdy któryś koniec odcinka BVG leży na lotnisku BER (strefa C), inaczej None."""
    endpoints = _leg_endpoints(leg)
    if endpoints is not None:
        lat, lon, radius_km = BER_AIRPORT_AREA
        at_ber = any(
            haversine_km(p_lat, p_lon, lat, lon) <= radius_km for p_lat, p_lon in endpoints
        )
    else:
        at_ber = _matches_any_word(
            f"{leg.origin_name} {leg.destination_name}".lower(), BER_AIRPORT_KEYWORDS
        )
    return "ABC" if at_ber else None


_NRW_INNER_BOXES = (
    # (lat_min, lat_max, lon_min, lon_max) — prostokąty CAŁKOWICIE wewnątrz NRW (z zapasem od
    # granic z NL/BE, Dolną Saksonią, Hesją i Nadrenią-Palatynatem), więc konserwatywne:
    {"lat_min": 50.95, "lat_max": 51.80, "lon_min": 6.40, "lon_max": 8.20},  # Ren-Ruhra, Düsseldorf, Wuppertal, Hamm
    {"lat_min": 51.80, "lat_max": 52.05, "lon_min": 7.20, "lon_max": 8.90},  # Münster, Bielefeld, Gütersloh
    {"lat_min": 51.50, "lat_max": 51.80, "lon_min": 8.20, "lon_max": 8.80},  # Paderborn, Lippstadt
    {"lat_min": 50.65, "lat_max": 50.95, "lon_min": 6.60, "lon_max": 7.20},  # Kolonia, Bonn, Euskirchen
    {"lat_min": 50.74, "lat_max": 50.83, "lon_min": 6.09, "lon_max": 6.60},  # Akwizgran, Düren
)
"""Obszar, w którym stosujemy taryfę eezy.nrw (fares/vrr.py). eezy.nrw to taryfa NRW — poza
Nadrenią Północną-Westfalią jej użycie jest bezpodstawne (błąd K2 z audytu: S-Bahn Berlin,
POLREGIO i DB Regio w całych Niemczech dostawały ceny Zagłębia Ruhry). Prostokąty są celowo
wewnątrz granic landu: stacja przy granicy NRW (np. Siegen, Minden, Gronau) dostaje
niepotwierdzony szacunek zamiast eezy.nrw — wolimy jawny brak pewności niż cudzą taryfę."""


def _in_nrw(lat: float, lon: float) -> bool:
    return any(
        b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]
        for b in _NRW_INNER_BOXES
    )


def is_leg_in_nrw(leg: Leg) -> bool:
    """Czy OBA końce odcinka leżą w NRW (_NRW_INNER_BOXES). Bez współrzędnych: False — nie
    zakładamy NRW tylko dlatego, że nie wiemy, gdzie jest przystanek."""
    endpoints = _leg_endpoints(leg)
    return endpoints is not None and all(_in_nrw(lat, lon) for lat, lon in endpoints)


PL_MOTIS_DATASETS = frozenset({"pl", "ztml", "ztmw", "krka", "krkm", "krkt"})
"""Prefiksy datasetów MOTIS (patrz motis/config*.yml, routing/README.md) obejmujące Polskę:
'pl' (PKP, PolishTrainsGTFS), 'ztml' (ZTM Lublin), 'ztmw' (ZTM Warszawa), 'krka'/'krkm'/'krkt'
(Kraków). UWAGA: prefiks datasetu to źródło FEEDU,
NIE kraj przystanku — feed 'pl' (PolishTrainsGTFS) dla połączeń międzynarodowych (np. Berlin-
Warszawa-Express) zawiera też przystanki fizycznie leżące w Niemczech pod prefiksem 'pl_'
(publikuje je PKP jako część własnego rozkładu tego kursu). Dlatego is_cross_border_pl_de()
NIE polega już na tym prefiksie jako głównym sygnale — patrz niżej."""

DE_MOTIS_DATASETS = frozenset({"defv", "derv", "denv", "dehvv", "demvv", "devrs"})
"""Prefiksy datasetów MOTIS obejmujące Niemcy: 'defv' (dalekobieżne), 'derv' (regionalne) i
'denv' (lokalne) — wszystkie trzy z gtfs.de dla CAŁYCH Niemiec (scripts/fetch_data.py), nie
tylko NRW — oraz miejskie 'dehvv'/'demvv'/'devrs' (Hamburg, Monachium, Kolonia)."""

# Przybliżone, celowo szerokie (nachodzące na siebie w pasie przygranicznym) skrzynki
# geograficzne — wystarczające, żeby odróżnić miasta odległe od granicy (Warszawa, Berlin,
# Lublin, Gelsenkirchen, ...). W pasie, gdzie skrzynki się nakładają (ok. 14.0-15.05°E),
# rozstrzyga linia granicy _PL_DE_BORDER_LINE.
_PL_BBOX = {"lat_min": 49.0, "lat_max": 54.9, "lon_min": 14.0, "lon_max": 24.2}
_DE_BBOX = {"lat_min": 47.2, "lat_max": 55.1, "lon_min": 5.8, "lon_max": 15.05}
"""lon_max 15.05 (było 14.9): Görlitz (ok. 14.98°E) i okolice leżą w Niemczech na wschód od
14.9°E — stara skrzynka uznawała je za Polskę (błąd S3 z audytu)."""

_PL_DE_BORDER_LINE = (
    (50.87, 14.82),  # trójstyk PL/DE/CZ koło Zittau
    (51.01, 14.94),  # Ostritz
    (51.08, 14.96),
    (51.15, 14.995),  # Görlitz/Zgorzelec (Nysa Łużycka)
    (51.20, 15.01),
    (51.27, 15.04),  # Zentendorf — najdalej na wschód wysunięty punkt Niemiec
    (51.40, 14.96),
    (51.47, 14.94),
    (51.55, 14.725),  # Bad Muskau/Łęknica
    (51.74, 14.655),  # Forst/Zasieki
    (51.95, 14.72),  # Guben/Gubin
    (52.07, 14.76),  # ujście Nysy do Odry
    (52.15, 14.69),
    (52.34, 14.557),  # Frankfurt (Oder)/Słubice
    (52.58, 14.635),  # Kostrzyn/Küstrin-Kietz
    (52.67, 14.45),
    (52.75, 14.32),
    (52.84, 14.14),
    (53.05, 14.32),  # Schwedt
    (53.20, 14.41),  # Gartz
    (53.30, 14.40),  # granica schodzi z Odry na zachód od Szczecina
    (53.45, 14.34),
    (53.55, 14.27),
    (53.70, 14.25),  # Zalew Szczeciński
    (53.93, 14.226),  # Świnoujście/Ahlbeck
)
"""Przybliżony przebieg granicy PL/DE (Odra-Nysa) jako łamana (lat, lon) z południa na północ —
punkty orientacyjne, NIE dokładna geometria granicy. Na danej szerokości: na zachód od linii
Niemcy, na wschód Polska. Szczecin (ok. 14.55°E) leży na ZACHÓD od Odry, ale na wschód od
granicy (ok. 14.35-14.40°E na tej szerokości) — dlatego to łamana, a nie stała długość."""

_BORDER_MARGIN_DEG = 0.01
"""Ok. 700 m: punkt bliżej łamanej niż ten margines (w długości geograficznej) uznajemy za
nierozstrzygnięty (None) — łamana jest przybliżona, więc tuż przy rzece nie zgadujemy kraju."""


def _border_lon_at(lat: float) -> float | None:
    """Długość geograficzna granicy PL/DE na danej szerokości (interpolacja liniowa łamanej)."""
    line = _PL_DE_BORDER_LINE
    if not line[0][0] <= lat <= line[-1][0]:
        return None
    for (lat1, lon1), (lat2, lon2) in zip(line, line[1:]):
        if lat1 <= lat <= lat2:
            t = 0.0 if lat2 == lat1 else (lat - lat1) / (lat2 - lat1)
            return lon1 + t * (lon2 - lon1)
    return None


def _country_from_latlon(lat: float | None, lon: float | None) -> str | None:
    """Kraj przystanku wg współrzędnych: skrzynki PL/DE, a w pasie, gdzie się nakładają —
    strona łamanej granicy _PL_DE_BORDER_LINE. None, gdy brak lat/lon, punkt leży poza obiema
    skrzynkami, poza zasięgiem łamanej (np. Czechy) albo bliżej granicy niż _BORDER_MARGIN_DEG."""
    if lat is None or lon is None:
        return None
    in_pl = (
        _PL_BBOX["lat_min"] <= lat <= _PL_BBOX["lat_max"]
        and _PL_BBOX["lon_min"] <= lon <= _PL_BBOX["lon_max"]
    )
    in_de = (
        _DE_BBOX["lat_min"] <= lat <= _DE_BBOX["lat_max"]
        and _DE_BBOX["lon_min"] <= lon <= _DE_BBOX["lon_max"]
    )
    if in_pl and not in_de:
        return "PL"
    if in_de and not in_pl:
        return "DE"
    if not (in_pl and in_de):
        return None
    border_lon = _border_lon_at(lat)
    if border_lon is None:
        return None
    if lon < border_lon - _BORDER_MARGIN_DEG:
        return "DE"
    if lon > border_lon + _BORDER_MARGIN_DEG:
        return "PL"
    return None


def _motis_dataset(stop_id: str | None) -> str | None:
    """Prefiks datasetu z stopId MOTIS (`<dataset>_<id>`, patrz routing/README.md) — None,
    jeśli stopId brakuje albo nie ma prefiksu (np. punkt ze współrzędnych, nie z GTFS)."""
    if not stop_id or "_" not in stop_id:
        return None
    return stop_id.split("_", 1)[0]


def _country_from_dataset(stop_id: str | None) -> str | None:
    """Kraj przystanku wg prefiksu datasetu MOTIS — FALLBACK, używany tylko gdy lat/lon
    niedostępne (patrz zastrzeżenie przy PL_MOTIS_DATASETS o feedzie 'pl' i stacjach w DE)."""
    dataset = _motis_dataset(stop_id)
    if dataset is None:
        return None
    if dataset in PL_MOTIS_DATASETS:
        return "PL"
    if dataset in DE_MOTIS_DATASETS:
        return "DE"
    return None


def _leg_endpoint_country(leg: Leg, prefix: str) -> str | None:
    """Kraj jednego końca odcinka ('origin'/'destination') — najpierw wg współrzędnych
    (rozstrzyga poprawnie nawet gdy stacja w Niemczech jest opublikowana w polskim feedzie
    GTFS dla kursu międzynarodowego), dopiero gdy lat/lon brak — wg prefiksu datasetu.
    Gdy współrzędne są, ale kraj nierozstrzygnięty (tuż przy granicy), NIE wracamy do
    prefiksu datasetu — ten mówi o źródle feedu, nie o kraju."""
    lat, lon = leg.extra.get(f"{prefix}_lat"), leg.extra.get(f"{prefix}_lon")
    if lat is not None and lon is not None:
        return _country_from_latlon(lat, lon)
    return _country_from_dataset(leg.extra.get(f"{prefix}_stop_id"))


BORDER_CROSSING_PL_DE = {"lat": 52.3454, "lon": 14.5583}
"""Przybliżony punkt granicy PL/DE na przejściu Frankfurt (Oder)/Słubice (trasa
Berlin-Warszawa-Express). Zachowany dla zgodności; german_portion_fraction() wybiera teraz
najbliższe przejście z BORDER_CROSSINGS_PL_DE."""

BORDER_CROSSINGS_PL_DE = (
    BORDER_CROSSING_PL_DE,  # Frankfurt (Oder)/Słubice
    {"lat": 53.33, "lon": 14.40},  # Tantow/Szczecin-Gumieńce
    {"lat": 51.15, "lon": 14.995},  # Görlitz/Zgorzelec
    {"lat": 51.74, "lon": 14.655},  # Forst/Zasieki
    {"lat": 51.95, "lon": 14.72},  # Guben/Gubin
    {"lat": 52.58, "lon": 14.635},  # Küstrin-Kietz/Kostrzyn
)
"""Przybliżone punkty kolejowych przejść granicznych PL/DE (na łamanej _PL_DE_BORDER_LINE),
używane WYŁĄCZNIE do szacowania, jaka część trasy międzynarodowej leży po stronie niemieckiej
(proporcjonalny rabat BahnCard, patrz fares/international.py). Wybieramy przejście dające
najkrótszą łamaną origin-przejście-destination — nie znamy geometrii realnej trasy kolejowej."""


def german_portion_fraction(leg: Leg) -> float | None:
    """Szacowany udział (0-1) niemieckiego odcinka trasy międzynarodowej w całym dystansie
    (linia prosta origin-przejście + przejście-destination, przez najbliższe przejście z
    BORDER_CROSSINGS_PL_DE), używany do proporcjonalnego naliczenia rabatu BahnCard (oficjalnie
    dotyczy tylko niemieckiego odcinka). None, gdy brakuje współrzędnych któregoś końca — wtedy
    fares/international.py nalicza rabat od całej ceny."""
    endpoints = _leg_endpoints(leg)
    if endpoints is None:
        return None
    (o_lat, o_lon), (d_lat, d_lon) = endpoints

    def legs_via(crossing: dict) -> tuple[float, float]:
        return (
            haversine_km(o_lat, o_lon, crossing["lat"], crossing["lon"]),
            haversine_km(crossing["lat"], crossing["lon"], d_lat, d_lon),
        )

    dist_origin_border, dist_border_dest = min(
        (legs_via(c) for c in BORDER_CROSSINGS_PL_DE), key=sum
    )
    total = dist_origin_border + dist_border_dest
    if total <= 0:
        return None
    if _leg_endpoint_country(leg, "origin") == "DE":
        return dist_origin_border / total  # kierunek DE -> PL: część niemiecka to origin->granica
    return dist_border_dest / total  # domyślnie: origin PL, część niemiecka to granica->destination


def is_cross_border_pl_de(leg: Leg) -> bool:
    """Czy ten odcinek kolejowy przekracza granicę PL/DE jednym ciągłym przejazdem (np.
    Berlin-Warszawa-Express) — wykryte GEOGRAFICZNIE (współrzędne stacji początkowej i
    końcowej), z prefiksem datasetu MOTIS jako fallbackiem gdy lat/lon niedostępne. Zwraca
    False, gdy kraju któregoś końca nie da się ustalić (brak danych, albo stacja tuż przy
    granicy) — bezpieczny wybór: leg trafia do zwykłej (krajowej) ścieżki wyceny
    zamiast fałszywie alarmować."""
    origin_country = _leg_endpoint_country(leg, "origin")
    destination_country = _leg_endpoint_country(leg, "destination")
    if origin_country is None or destination_country is None:
        return False
    return origin_country != destination_country


LONG_DISTANCE_RAIL_KEYWORDS = ("flix",)
"""Przewoźnicy kolejowi spoza taryf związkowych (np. FlixTrain nie honoruje eezy.nrw) — nawet
w NRW nie dostają taryfy VRR."""


def infer_rail_carrier(agency_name: str) -> Carrier | None:
    """Mapowanie agencyName z MOTIS na przewoźnika dalekobieżnego z modułu fares/ — TYLKO po
    nazwie: PKP Intercity albo DB Fernverkehr. Każdy inny przewoźnik (POLREGIO, DB Regio,
    S-Bahn, ODEG, Koleje Dolnośląskie, ...) zwraca None: taryfa regionalna zależy od MIEJSCA
    przejazdu, nie od nazwy przewoźnika, więc rozstrzyga ją price_rail_leg() geograficznie
    (taryfa miejska z CITY_TARIFF_AREAS, eezy.nrw tylko w NRW — is_leg_in_nrw()).

    Wcześniej każda nazwa z "regio"/"s-bahn" trafiała do VRR (eezy.nrw) z uzasadnieniem, że
    feed regionalny 'derv' obejmuje tylko NRW — to nieprawda: scripts/fetch_data.py pobiera
    gtfs.de rv_free/nv_free dla CAŁYCH Niemiec, a "regio" łapało też POLREGIO (błąd K2)."""
    name = (agency_name or "").lower()
    if "pkp intercity" in name:
        return Carrier.PKP_INTERCITY
    if "db fernverkehr" in name or "deutsche bahn" in name or name.strip() == "db":
        return Carrier.DB
    return None


PKP_PREMIUM_CATEGORIES = ("EIC", "EIP")
"""Kategorie PKP Intercity, których ceny w oficjalnym cenniku są ustalane per relacja, a nie wg
pasm odległości TLK/IC z fares/data/pkp_intercity.json (patrz fares/README.md)."""


def is_pkp_premium_train(leg: Leg) -> bool:
    """Czy odcinek to pociąg EIC/EIP (Express InterCity / Express InterCity Premium, Pendolino)
    — po routeShortName z MOTIS (np. "EIC", "EIP 1234") albo nazwie przewoźnika."""
    route = str(leg.extra.get("route_short_name") or "")
    tekst = f"{route} {leg.carrier_name}"
    return _matches_any_word(tekst.upper(), PKP_PREMIUM_CATEGORIES) or _matches_any_word(
        tekst.lower(), ("express intercity", "pendolino")
    )


def _fallback_priced_leg(leg: Leg, reason: str) -> PricedLeg:
    """Zgrubny szacunek PLN/km, gdy żaden moduł taryf nie obejmuje odcinka — zawsze
    price_type="szacunek" i breakdown["price_verified"]=False (cena niepotwierdzona)."""
    distance_km = leg.distance_km or 0.0
    amount = round(GENERIC_FALLBACK_PLN_PER_KM * distance_km, 2)
    return PricedLeg(
        leg=leg,
        amount=amount,
        currency="PLN",
        price_type="szacunek",
        notes=(
            f"{reason} Zgrubny szacunek: {GENERIC_FALLBACK_PLN_PER_KM} PLN/km x {distance_km:.0f} km "
            "— cena niepotwierdzona."
        ),
        breakdown={"price_verified": False, "powod_szacunku": reason},
    )


def _with_pkp_alternative(segment: Segment, db_result: PriceEstimate) -> PriceEstimate:
    """Dla biletu PL-DE dolicza WŁASNĄ ofertę PKP Intercity na tej samej relacji (zob.
    fares/international_pkp.py) i zwraca TAŃSZĄ z dwóch ofert jako wynik główny, z drugą
    (droższą) dołączoną w breakdown["alternatywna_oferta"] — pasażer może kupić bilet w
    KTÓRYMKOLWIEK z dwóch kanałów sprzedaży (PKP albo DB) na ten sam pociąg, więc pomijanie
    tańszej z dwóch ofert zawyżałoby "ile faktycznie zapłacisz". Gdy relacja nie jest rozpoznana
    w tabeli PKP (fares/data/international_pl_de_pkp.json), zwraca db_result bez zmian."""
    pkp_result = estimate_pkp_offer(segment)
    if pkp_result is None:
        return db_result

    if pkp_result.amount <= db_result.amount:
        main, alt, alt_label = pkp_result, db_result, "db"
    else:
        main, alt, alt_label = db_result, pkp_result, "pkp_oferta_polska_niemcy"

    main.breakdown["alternatywna_oferta"] = {
        "zrodlo": alt_label,
        "cena": alt.amount,
        "waluta": alt.currency,
    }
    main.notes = (
        f"{main.notes} Tańsza z dwóch dostępnych ofert na tę relację (PKP Intercity vs DB) — "
        f"alternatywa: {alt.amount:.2f} {alt.currency} ({'DB Super Sparpreis Europa' if alt_label == 'db' else 'PKP Oferta Polska-Niemcy'}). "
        f"{pkp_result.notes if main is db_result else db_result.notes}"
    )
    return main


def _with_spi_range(segment: Segment, result: PriceEstimate) -> PriceEstimate:
    """Dla biletu PL-DE dokłada przedział "od X do Y" wg cennika PKP Super Promo International
    (breakdown["zakres_cen"]). Dolna granica = min(poziom I SPI, cena główna, czyli tańsza z DB
    "od" i PKP regularnego); górna = min(poziom V SPI, cena regularna PKP, o ile jest w tabeli).
    Cena główna (`amount`) zostaje dolną granicą jak dotąd; górną widać w zakres_cen["do"].
    Poza cennikiem SPI (albo dla dziecka) wynik bez zmian."""
    spi = spi_range_for_segment(segment)
    if spi is None:
        return result
    pkp = estimate_pkp_offer(segment)
    gorna = spi["do"] if pkp is None else min(spi["do"], pkp.breakdown["cena_regularna"])
    od = min(spi["od"], result.amount)
    do = max(gorna, od)
    if spi["od"] <= result.amount:
        od_zrodlo = "SPI poziom I"
    elif result.breakdown.get("oferta") == "pkp_oferta_polska_niemcy":
        od_zrodlo = "PKP cennik regularny"
    else:
        od_zrodlo = "DB (cena od, bez górnej granicy w źródle)"
    do_zrodlo = (
        "SPI poziom V"
        if pkp is None or spi["do"] <= pkp.breakdown["cena_regularna"]
        else "PKP cennik regularny"
    )
    result.breakdown["zakres_cen"] = {
        "od": od,
        "do": do,
        "waluta": spi["waluta"],
        "od_zrodlo": od_zrodlo,
        "do_zrodlo": do_zrodlo,
        "spi_od": spi["od"],
        "spi_do": spi["do"],
        "pkp_cena_regularna": None if pkp is None else pkp.breakdown["cena_regularna"],
        "klasa": 2,
        "pociagi_spi": spi["pociagi"],
        "zrodlo": spi["zrodlo"],
        "zrodlo_url": spi["zrodlo_url"],
        "data_cennika": spi["data_cennika"],
    }
    result.notes = (
        f"{result.notes} Szacunek: od {od:.2f} ({od_zrodlo}) do {do:.2f} ({do_zrodlo}) {spi['waluta']}. "
        f"Przedział PKP Super Promo International: {spi['od']:.2f}-{spi['do']:.2f} {spi['waluta']} "
        f"(poziomy cenowe I-V, 2. klasa, dorosły; cennik od {spi['data_cennika']}). "
        f"Który poziom obowiązuje danego dnia, cennik nie podaje."
    )
    return result


def price_rail_leg(leg: Leg, discounts: DiscountProfile) -> PricedLeg:
    if leg.mode is not LegMode.RAIL:
        raise ValueError(f"price_rail_leg wymaga LegMode.RAIL, dostał {leg.mode}")

    name_carrier = infer_rail_carrier(leg.carrier_name)
    if is_cross_border_pl_de(leg):
        # Jeden ciągły odcinek PL<->DE (np. Berlin-Warszawa-Express) NIE jest ani krajowym
        # biletem PKP, ani krajowym biletem DB — ma własne sztywne kategorie cenowe i własne
        # (częściowe) zasady BahnCard (patrz fares/international.py i
        # [[international-pl-de-fare-gap]] w pamięci projektu). Te moduły opisują oferty PKP
        # Intercity/DB; przejazd transgraniczny przewoźnikiem regionalnym (np. Szczecin-Berlin,
        # Wrocław-Görlitz) nie ma u nas potwierdzonej taryfy, więc nie podstawiamy cudzej.
        if name_carrier is None and leg.carrier_name.strip():
            return _fallback_priced_leg(
                leg,
                f"Odcinek transgraniczny PL/DE przewoźnika '{leg.carrier_name}' — moduły taryf "
                "międzynarodowych obejmują tylko oferty PKP Intercity/DB, brak potwierdzonej "
                "taryfy dla tego przewoźnika.",
            )
        carrier: Carrier | None = Carrier.INTERNATIONAL_PL_DE
    else:
        carrier = name_carrier
        if carrier is None:
            # Taryfa regionalna zależy od miejsca, nie od nazwy przewoźnika. MOTIS klasyfikuje
            # część S-Bahnów jako RAIL (nie BUS — patrz komentarz w price_bus_leg), więc
            # sprawdzamy te same taryfy miejskie co price_bus_leg (Verbundtarif obejmuje też
            # S-Bahn/RE w obrębie miasta), a eezy.nrw (VRR) tylko dla odcinka w całości w NRW.
            carrier = _city_carrier_for_leg(leg, _DE_CITY_RAIL_CARRIERS)
            if (
                carrier is None
                and is_leg_in_nrw(leg)
                and not any(k in leg.carrier_name.lower() for k in LONG_DISTANCE_RAIL_KEYWORDS)
            ):
                carrier = Carrier.VRR
    if carrier is None:
        return _fallback_priced_leg(
            leg,
            f"Brak modułu taryf dla przewoźnika '{leg.carrier_name}' na tym odcinku "
            "(taryfa eezy.nrw/VRR obowiązuje tylko w NRW, taryfy miejskie tylko w obrębie miasta).",
        )

    try:
        segment = Segment(
            carrier=carrier,
            origin=leg.origin_name,
            destination=leg.destination_name,
            distance_km=leg.distance_km,
            ride_duration_min=leg.duration_min,
            discounts=discounts,
            travel_date=leg.depart.date().isoformat(),
            german_portion_fraction=(
                german_portion_fraction(leg) if carrier is Carrier.INTERNATIONAL_PL_DE else None
            ),
            tariff_zone=_bvg_tariff_zone(leg) if carrier is Carrier.BVG_BERLIN else None,
        )
        result = fares_estimate_price(segment)
        if carrier is Carrier.INTERNATIONAL_PL_DE:
            result = _with_pkp_alternative(segment, result)
            result = _with_spi_range(segment, result)
    except ValueError as exc:
        return _fallback_priced_leg(leg, f"Kalkulator {carrier.value} zwrócił błąd ({exc}).")

    price_type = result.price_type.value
    notes = result.notes
    breakdown = result.breakdown
    if carrier is Carrier.PKP_INTERCITY and is_pkp_premium_train(leg):
        # Cennik w fares/data/pkp_intercity.json to pasma TLK/IC; EIC/EIP mają ceny per relacja
        # (fares/README.md), których nie mamy. Kwota z pasm TLK/IC zostaje jako orientacyjny
        # szacunek, ale NIE jako oficjalna taryfa tego pociągu (błąd S2 z audytu).
        price_type = PriceType.ESTIMATE.value
        breakdown = {**breakdown, "price_verified": False, "kategoria_pociagu": "EIC/EIP"}
        notes = (
            "Pociąg EIC/EIP: cena NIEPOTWIERDZONA — szacunek wg cennika TLK/IC (pasma odległości), "
            "a EIC/EIP ma w cenniku PKP Intercity ceny ustalane per relacja, których nie mamy. "
            f"{notes}"
        )

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=price_type,
        notes=notes,
        breakdown=breakdown,
        carrier=carrier,
    )


def price_flight_leg(leg: Leg, currency: str = "PLN") -> PricedLeg:
    if leg.mode is not LegMode.FLIGHT:
        raise ValueError(f"price_flight_leg wymaga LegMode.FLIGHT, dostał {leg.mode}")

    origin_iata = leg.extra["origin_iata"]
    destination_iata = leg.extra["destination_iata"]
    checked_baggage = leg.extra.get("checked_baggage", True)
    extras = (
        _flight_baggage_only_extras(origin_iata, destination_iata, currency)
        if checked_baggage
        else ExtrasProfile(
            baggage_cost=0.0, currency=currency, note="Tylko bagaż podręczny: bez opłaty za rejestrowany."
        )
    )
    segment = FlightSegment(
        origin=origin_iata,
        destination=destination_iata,
        depart_date=leg.extra["depart_date"],
        currency=currency,
        extras=extras,
    )
    result = flights_estimate_price(
        segment
    )  # może podnieść TravelpayoutsError — obsługa wyżej (variants.py)

    # Dociągamy REALNY cennik bagażu wg linii z biletu (result.breakdown["linia"], np. "FR" dla
    # Ryanaira), jeśli go znamy — nadpisuje szacunek z tabeli relacji/domyślny użyty wyżej
    # w _flight_baggage_only_extras (ten nie znał jeszcze linii, bo poznajemy ją dopiero z
    # odpowiedzi Travelpayouts).
    airline_baggage = (
        get_baggage_by_airline(result.breakdown.get("linia")) if checked_baggage else None
    )
    if airline_baggage is not None:
        amount_native, currency_native, source_note = airline_baggage
        amount_in_currency = convert_currency(amount_native, currency_native, currency)
        old_baggage = result.breakdown.get("bagaz", 0.0)
        result.amount = round(result.amount - old_baggage + amount_in_currency, 2)
        result.breakdown["bagaz"] = round(amount_in_currency, 2)
        result.breakdown["bagaz_zrodlo"] = source_note
        result.notes = f"{result.notes} Bagaż wg realnego cennika przewoźnika: {source_note}."

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=result.price_type.value,
        notes=result.notes,
        breakdown=result.breakdown,
    )


LOCAL_BUS_FLAT_PLN = 4.0
"""PLACEHOLDER (NIE cena z cennika, bez źródła): wartość zastępcza za odcinek MOTIS spoza
RAIL/TRAIN (autobus, tramwaj), używana TYLKO gdy operator nie jest objęty żadnym modułem taryf
(odcinek poza obszarami CITY_TARIFF_AREAS i poza NRW). NIE dotyczy trybu SUBURBAN (SKM, S-Bahn):
to kolej, więc ma osobną ścieżkę — patrz price_suburban_leg. Wartość nie zależy od kraju ani
długości odcinka, więc w Niemczech i na dłuższych odcinkach zaniża koszt. Wynik zawsze ma price_type="szacunek", breakdown["price_verified"]=False i
breakdown["wartosc_zastepcza"]=True; wariant z takim odcinkiem nie wygrywa rankingu "Najtańsza"
z wariantem o potwierdzonej cenie (routing/scoring.py)."""


LONG_DISTANCE_COACH_KEYWORDS = ("flix", "regiojet", "blablabus")


def price_flixbus_leg(leg: Leg) -> PricedLeg:
    """FlixBus ma teraz własny moduł taryf (fares/flixbus.py): realna cena z (nieoficjalnego)
    API FlixBusa dla konkretnej daty, z fallbackiem do PLN/km gdy API niedostępne/bez wyniku."""
    try:
        segment = Segment(
            carrier=Carrier.FLIXBUS,
            origin=leg.origin_name,
            destination=leg.destination_name,
            distance_km=leg.distance_km,
            travel_date=leg.depart.date().isoformat(),
        )
        result = fares_estimate_price(segment)
    except ValueError as exc:
        return _fallback_priced_leg(leg, f"Kalkulator FlixBus zwrócił błąd ({exc}).")

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=result.price_type.value,
        notes=result.notes,
    )


SUBURBAN_MOTIS_MODE = "SUBURBAN"
"""Tryb MOTIS dla kolei podmiejskiej (SKM Trójmiasto/Szczecin, S-Bahn, ...). itinerary_to_legs
mapuje go na LegMode.BUS (każdy tryb inny niż RAIL/TRAIN), ale to POCIĄG — nie wolno go wyceniać
jak autobusu miejskiego (LOCAL_BUS_FLAT_PLN), bo odcinek bywa kilkudziesięciokilometrowy."""


def is_suburban_leg(leg: Leg) -> bool:
    """Czy MOTIS oznaczył odcinek trybem SUBURBAN (leg.extra["motis_mode"])."""
    return leg.extra.get("motis_mode") == SUBURBAN_MOTIS_MODE


def price_suburban_leg(leg: Leg) -> PricedLeg:
    """Kolej podmiejska (MOTIS: SUBURBAN) bez znanej taryfy: NIE ryczałt autobusowy, tylko
    jawnie niepotwierdzony szacunek PLN/km (_fallback_priced_leg), z dopiskiem w notes i
    breakdown["tryb_motis"]="SUBURBAN". Wołane z price_bus_leg dopiero PO sprawdzeniu taryf
    miejskich (np. S-Bahn Berlin w kole BVG dostaje bilet BVG) i eezy.nrw (S-Bahn w NRW).
    Ceny SKM Szczecin/Trójmiasto i innych kolei podmiejskich nie ma w fares/data/* — bez
    zweryfikowanego źródła nie podajemy kwoty jako pewnej."""
    priced = _fallback_priced_leg(
        leg,
        f"Kolej podmiejska (MOTIS: {SUBURBAN_MOTIS_MODE}) '{leg.carrier_name}' poza obszarami z "
        "potwierdzoną taryfą (taryfy miejskie z CITY_TARIFF_AREAS, eezy.nrw w NRW) — brak "
        "zweryfikowanej stawki w fares/data/*; to nie autobus, więc bez ryczałtu autobusowego.",
    )
    priced.breakdown["tryb_motis"] = SUBURBAN_MOTIS_MODE
    return priced


def price_bus_leg(leg: Leg, discounts: DiscountProfile | None = None) -> PricedLeg:
    """UWAGA (sprawdzone 2026-10-10, test realnym GTFS HVV/MVV/VRS w PR #49): ten kalkulator
    bywa wołany też dla legów, które MOTIS sklasyfikował jako "BUS" mimo że faktycznie są
    S-Bahn/U-Bahn obsługiwanym przez DB Regio (routing/motis_client.py::itinerary_to_legs
    mapuje każdy tryb MOTIS inny niż RAIL/TRAIN na LegMode.BUS, patrz komentarz tam). To NIE
    jest błąd do naprawy: HVV/MVV/Rheinlandtarif (VRS) to Verbundtarif obejmujący WSZYSTKIE
    lokalne środki transportu (S-Bahn, U-Bahn, tramwaj, autobus) w obrębie związku jedną,
    wspólną ceną zależną od strefy/relacji, niezależnie od operatora czy trybu — więc
    dopasowanie miasta (_city_carrier_for_leg: geograficznie po współrzędnych, a bez nich po
    nazwach jako CAŁYCH słowach) i wycena z taryfy związkowej jest poprawna, nawet gdy
    przewoźnik widoczny w danych to "DB Regio ..."."""
    discounts = discounts or DiscountProfile()

    is_coach = leg.extra.get("motis_mode") == "COACH" or any(
        k in leg.carrier_name.lower() for k in LONG_DISTANCE_COACH_KEYWORDS
    )
    if is_coach:
        if "flix" in leg.carrier_name.lower():
            return price_flixbus_leg(leg)
        return _fallback_priced_leg(leg, "Autokar dalekobieżny — brak modułu taryf.")

    carrier = _city_carrier_for_leg(leg)
    if carrier is not None:
        try:
            segment = Segment(
                carrier=carrier,
                origin=leg.origin_name,
                destination=leg.destination_name,
                ride_duration_min=leg.duration_min,
                discounts=discounts,
                tariff_zone=_bvg_tariff_zone(leg) if carrier is Carrier.BVG_BERLIN else None,
            )
            result = fares_estimate_price(segment)
            return PricedLeg(
                leg=leg,
                amount=result.amount,
                currency=result.currency,
                price_type=result.price_type.value,
                notes=result.notes,
                breakdown=result.breakdown,
                carrier=carrier,
            )
        except ValueError as exc:
            return _fallback_priced_leg(leg, f"Kalkulator {carrier.value} zwrócił błąd ({exc}).")

    # eezy.nrw (VRR) obejmuje cały transport lokalny NRW, ale TYLKO NRW — dane GTFS (gtfs.de nv)
    # obejmują całe Niemcy, więc nierozpoznany autobus/tramwaj poza NRW NIE dostaje tej taryfy.
    if is_leg_in_nrw(leg) and leg.distance_km is not None:
        try:
            segment = Segment(
                carrier=Carrier.VRR,
                origin=leg.origin_name,
                destination=leg.destination_name,
                distance_km=leg.distance_km,
                discounts=discounts,
            )
            result = fares_estimate_price(segment)
            return PricedLeg(
                leg=leg,
                amount=result.amount,
                currency=result.currency,
                price_type=result.price_type.value,
                notes=result.notes,
                breakdown=result.breakdown,
                carrier=Carrier.VRR,
            )
        except ValueError as exc:
            return _fallback_priced_leg(leg, f"Kalkulator VRR zwrócił błąd ({exc}).")

    if is_suburban_leg(leg):
        return price_suburban_leg(leg)

    return PricedLeg(
        leg=leg,
        amount=LOCAL_BUS_FLAT_PLN,
        currency="PLN",
        price_type="szacunek",
        notes=(
            f"Nieznany operator lokalny '{leg.carrier_name}' poza obsługiwanymi miastami i NRW — "
            f"placeholder {LOCAL_BUS_FLAT_PLN:.2f} PLN, cena niepotwierdzona (nie z cennika)."
        ),
        breakdown={
            "price_verified": False,
            "wartosc_zastepcza": True,
            "powod_szacunku": "nieznany operator lokalny",
        },
    )


def price_walk_leg(leg: Leg) -> PricedLeg:
    return PricedLeg(
        leg=leg, amount=0.0, currency="PLN", price_type="oficjalna_taryfa", notes="Dojście pieszo."
    )


def price_leg(leg: Leg, discounts: DiscountProfile, flight_currency: str = "PLN") -> PricedLeg:
    if leg.mode is LegMode.RAIL:
        return price_rail_leg(leg, discounts)
    if leg.mode is LegMode.FLIGHT:
        return price_flight_leg(leg, currency=flight_currency)
    if leg.mode is LegMode.BUS:
        return price_bus_leg(leg, discounts)
    if leg.mode is LegMode.WALK:
        return price_walk_leg(leg)
    raise ValueError(f"nieznany LegMode: {leg.mode}")
