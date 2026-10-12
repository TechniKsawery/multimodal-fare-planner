"""Wycena pojedynczego odcinka: dispatch do fares/ (kolej) albo flights/ (lot)."""

from fares import estimate_price as fares_estimate_price
from fares.international_pkp import estimate_pkp_offer, spi_range_for_segment
from fares.model import Carrier, DiscountProfile, PriceEstimate, Segment
from flights import ExtrasProfile, FlightSegment
from flights import estimate_price as flights_estimate_price
from flights.cabin_baggage import get_cabin_baggage
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


VRR_AREA_KEYWORDS = ("s bahn", "s-bahn", "vrr", "national express", "abellio", "regio")
"""Fragmenty agencyName traktowane jako przewoźnik w obszarze taryfowym VRR (Zagłębie Rury/NRW)."""

ZTM_LUBLIN_KEYWORDS = ("lublin", "zditm", "ztm_l")
"""Fragmenty agencyName/nazw przystanków traktowane jako komunikacja miejska ZTM Lublin.

Zwężone z samego "ztm" do "ztm_l": generyczne "ztm" dopasowywało się też do ZTM Warszawa/Poznań,
które teraz mają własne kalkulatory — zob. city_carriers w price_bus_leg poniżej."""

ZTM_WARSZAWA_KEYWORDS = ("warszawa", "ztm warszawa", "wtp")
MPK_KRAKOW_KEYWORDS = ("kraków", "krakow", "mpk kraków", "mpk krakow", "ztp kraków", "ztp krakow", "kmk")
ZTM_POZNAN_KEYWORDS = ("poznań", "poznan", "ztm poznań", "ztm poznan", "mpk poznań", "mpk poznan")
MPK_WROCLAW_KEYWORDS = ("wrocław", "wroclaw", "mpk wrocław", "mpk wroclaw")
BVG_BERLIN_KEYWORDS = ("berlin", "bvg", "vbb")
HVV_KEYWORDS = ("hamburg", "hvv")
MVV_KEYWORDS = ("münchen", "muenchen", "munchen", "mvv")
VRS_KOLN_KEYWORDS = ("köln", "koeln", "koln", "kvb", "vrs")
"""HVV/MVV/VRS_KOLN: od wprowadzenia pełnego GTFS miejskiego dla Hamburga/Monachium/Kolonii
(docker-compose.de-full-city-gtfs.yml) te słowa kluczowe są aktywnie używane — zarówno przez
city_carriers w price_bus_leg (legi sklasyfikowane przez MOTIS jako BUS), jak i przez dopasowanie
w price_rail_leg (legi S-Bahn/U-Bahn sklasyfikowane jako RAIL, które inaczej wpadłyby pod
generyczne VRR_AREA_KEYWORDS "s-bahn"/"regio" i policzyłyby się błędnie taryfą eezy.nrw/Ruhry —
zob. [[hvv-mvv-vrs-rail-leg-fare-gap]] w pamięci projektu, naprawione 2026-10-11)."""


PL_MOTIS_DATASETS = frozenset({"pl", "ztml"})
"""Prefiksy datasetów MOTIS (patrz motis/config.yml, routing/README.md) obejmujące Polskę:
'pl' (PKP, PolishTrainsGTFS) i 'ztml' (ZTM Lublin). UWAGA: prefiks datasetu to źródło FEEDU,
NIE kraj przystanku — feed 'pl' (PolishTrainsGTFS) dla połączeń międzynarodowych (np. Berlin-
Warszawa-Express) zawiera też przystanki fizycznie leżące w Niemczech pod prefiksem 'pl_'
(publikuje je PKP jako część własnego rozkładu tego kursu). Dlatego is_cross_border_pl_de()
NIE polega już na tym prefiksie jako głównym sygnale — patrz niżej."""

DE_MOTIS_DATASETS = frozenset({"defv", "derv"})
"""Prefiksy datasetów MOTIS obejmujące Niemcy: 'defv' (DB dalekobieżne) i 'derv' (regionalne NRW)."""

# Przybliżone, celowo szerokie (nachodzące na siebie w pasie przygranicznym) skrzynki
# geograficzne — wystarczające, żeby odróżnić miasta odległe od granicy (Warszawa, Berlin,
# Lublin, Gelsenkirchen, ...), zawodne tylko dla stacji leżących dosłownie przy granicy
# (Rzepin, Frankfurt/Oder i okolice) — tam i tak żaden prosty podział nie jest w 100% pewny.
_PL_BBOX = {"lat_min": 49.0, "lat_max": 54.9, "lon_min": 14.0, "lon_max": 24.2}
_DE_BBOX = {"lat_min": 47.2, "lat_max": 55.1, "lon_min": 5.8, "lon_max": 14.9}


def _country_from_latlon(lat: float | None, lon: float | None) -> str | None:
    """Kraj przystanku wg współrzędnych (skrzynka geograficzna) — None, gdy brak lat/lon albo
    punkt pasuje do obu/żadnej skrzynki (pas przygraniczny, ok. 14.0-14.9°E — tam nie zgadujemy)."""
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
    GTFS dla kursu międzynarodowego), dopiero gdy lat/lon brak — wg prefiksu datasetu."""
    lat, lon = leg.extra.get(f"{prefix}_lat"), leg.extra.get(f"{prefix}_lon")
    country = _country_from_latlon(lat, lon)
    if country is not None:
        return country
    return _country_from_dataset(leg.extra.get(f"{prefix}_stop_id"))


BORDER_CROSSING_PL_DE = {"lat": 52.3454, "lon": 14.5583}
"""Przybliżony punkt granicy PL/DE (Rzepin/Frankfurt (Oder) — główne przejście na trasie
Berlin-Warszawa-Express, dominującym korytarzu w naszych danych GTFS) używany WYŁĄCZNIE do
szacowania jaka część trasy międzynarodowej leży po stronie niemieckiej (dla proporcjonalnego
rabatu BahnCard, patrz fares/international.py). Dla realnych tras przez inne przejścia
(Szczecin, Zgorzelec/Görlitz, Kudowa...) to przybliżenie będzie mniej dokładne — nie mamy
danych geometrii realnej trasy kolejowej, tylko linię prostą między stacjami."""


def german_portion_fraction(leg: Leg) -> float | None:
    """Szacowany udział (0-1) niemieckiego odcinka trasy międzynarodowej w całym dystansie
    (linia prosta origin-border + border-destination), używany do proporcjonalnego naliczenia
    rabatu BahnCard (oficjalnie dotyczy tylko niemieckiego odcinka). None, gdy brakuje
    współrzędnych któregoś końca — wtedy fares/international.py nalicza rabat od całej ceny."""
    o_lat, o_lon = leg.extra.get("origin_lat"), leg.extra.get("origin_lon")
    d_lat, d_lon = leg.extra.get("destination_lat"), leg.extra.get("destination_lon")
    if o_lat is None or o_lon is None or d_lat is None or d_lon is None:
        return None
    b_lat, b_lon = BORDER_CROSSING_PL_DE["lat"], BORDER_CROSSING_PL_DE["lon"]
    dist_origin_border = haversine_km(o_lat, o_lon, b_lat, b_lon)
    dist_border_dest = haversine_km(b_lat, b_lon, d_lat, d_lon)
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
    False, gdy kraju któregoś końca nie da się ustalić (brak danych, albo stacja w pasie
    przygranicznym) — bezpieczny wybór: leg trafia do zwykłej (krajowej) ścieżki wyceny
    zamiast fałszywie alarmować."""
    origin_country = _leg_endpoint_country(leg, "origin")
    destination_country = _leg_endpoint_country(leg, "destination")
    if origin_country is None or destination_country is None:
        return False
    return origin_country != destination_country


def infer_rail_carrier(agency_name: str) -> Carrier | None:
    """Zgrubne mapowanie agencyName z MOTIS na przewoźnika z modułu fares/.

    To PRZYBLIŻENIE: każdy niemiecki regionalny przewoźnik poza DB Fernverkehr (S-Bahn,
    Abellio, National Express, ...) jest tu traktowany jak VRR, choć w rzeczywistości różne
    związki taryfowe (VRR, VRS, ...) obowiązują w różnych regionach Niemiec. W SZCZEGÓLNOŚCI
    "DB Regio" (spółka DB, ale obsługująca pociągi regionalne) też trafia tutaj do VRR, a NIE
    do Carrier.DB — to ZWERYFIKOWANE jako poprawne (nie błąd), z dwóch powodów: (1) nasz
    regionalny feed GTFS (dataset 'derv', patrz routing/README.md) obejmuje WYŁĄCZNIE region
    Nadrenii Północnej-Westfalii/VRR — każdy "DB Regio" w naszych danych fizycznie jeździ
    wewnątrz obszaru taryfowego VRR, gdzie obowiązuje taryfa związkowa niezależnie od tego, kto
    operuje pociągiem; (2) taryfa VRR/eezy.nrw (fares/vrr.py) w ogóle nie wspomina o BahnCard
    (sprawdzone na vrr.de, 2026-09-29) — w przeciwieństwie do biletów DB (Flexpreis/Sparpreis),
    które explicite opisują rabat BahnCard. Nie zmieniać bez nowych danych regionalnych spoza NRW.
    """
    name = (agency_name or "").lower()
    if "pkp intercity" in name:
        return Carrier.PKP_INTERCITY
    if "db fernverkehr" in name or "deutsche bahn" in name or name.strip() == "db":
        return Carrier.DB
    if any(k in name for k in VRR_AREA_KEYWORDS):
        return Carrier.VRR
    return None


def _fallback_priced_leg(leg: Leg, reason: str) -> PricedLeg:
    distance_km = leg.distance_km or 0.0
    amount = round(GENERIC_FALLBACK_PLN_PER_KM * distance_km, 2)
    return PricedLeg(
        leg=leg,
        amount=amount,
        currency="PLN",
        price_type="szacunek",
        notes=f"{reason} Zgrubny szacunek: {GENERIC_FALLBACK_PLN_PER_KM} PLN/km x {distance_km:.0f} km.",
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

    if is_cross_border_pl_de(leg):
        # Jeden ciągły odcinek PL<->DE (np. Berlin-Warszawa-Express) NIE jest ani krajowym
        # biletem PKP, ani krajowym biletem DB — ma własne sztywne kategorie cenowe i własne
        # (częściowe) zasady BahnCard. Wymuszamy Carrier.INTERNATIONAL_PL_DE PRZED
        # infer_rail_carrier(), żeby nie policzyć go błędnie z krajowej tabeli pasm (patrz
        # fares/international.py i [[international-pl-de-fare-gap]] w pamięci projektu).
        carrier: Carrier | None = Carrier.INTERNATIONAL_PL_DE
    else:
        carrier = infer_rail_carrier(leg.carrier_name)
        if carrier in (None, Carrier.VRR):
            # MOTIS klasyfikuje S-Bahn/U-Bahn w Hamburgu, Monachium i Kolonii jako RAIL (nie
            # BUS — patrz komentarz w price_bus_leg), więc infer_rail_carrier() (który zna
            # tylko nazwę przewoźnika, nie przystanki) łapie je generycznym dopasowaniem
            # "s-bahn"/"regio" z VRR_AREA_KEYWORDS i liczy taryfą eezy.nrw (Zagłębie Ruhry) —
            # błędną dla tych miast. Odkąd dataset 'defv' obejmuje też pełne GTFS miejskie dla
            # Hamburga/Monachium/Kolonii (patrz docker-compose.de-full-city-gtfs.yml), trzeba
            # tu sprawdzić to samo co city_carriers w price_bus_leg PRZED zaakceptowaniem
            # ogólnego dopasowania VRR — stacja "Köln Hbf"/"Köln Messe/Deutz Bf" nie ma "köln"
            # w nazwie przewoźnika ("DB Regio AG NRW"), więc patrzymy też na origin/destination.
            tekst = f"{leg.carrier_name} {leg.origin_name} {leg.destination_name}".lower()
            for keywords, city_carrier in (
                (HVV_KEYWORDS, Carrier.HVV),
                (MVV_KEYWORDS, Carrier.MVV),
                (VRS_KOLN_KEYWORDS, Carrier.VRS_KOLN),
            ):
                if any(k in tekst for k in keywords):
                    carrier = city_carrier
                    break
    if carrier is None:
        return _fallback_priced_leg(leg, f"Brak modułu taryf dla przewoźnika '{leg.carrier_name}'.")

    try:
        segment = Segment(
            carrier=carrier,
            origin=leg.origin_name,
            destination=leg.destination_name,
            distance_km=leg.distance_km,
            discounts=discounts,
            travel_date=leg.depart.date().isoformat(),
            german_portion_fraction=(
                german_portion_fraction(leg) if carrier is Carrier.INTERNATIONAL_PL_DE else None
            ),
        )
        result = fares_estimate_price(segment)
        if carrier is Carrier.INTERNATIONAL_PL_DE:
            result = _with_pkp_alternative(segment, result)
            result = _with_spi_range(segment, result)
    except ValueError as exc:
        return _fallback_priced_leg(leg, f"Kalkulator {carrier.value} zwrócił błąd ({exc}).")

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=result.price_type.value,
        notes=result.notes,
        breakdown=result.breakdown,
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

    # Bagaż PODRĘCZNY: osobna informacja (wliczony / płatny z kwotą w oryginalnej walucie /
    # nieznany). NIE zmienia ceny biletu ani kwoty łącznej — dopłata to widełki w walucie
    # przewoźnika, których nie przeliczamy po placeholderowym kursie.
    cabin = get_cabin_baggage(result.breakdown.get("linia"))
    result.breakdown["bagaz_podreczny"] = cabin.to_dict()

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=result.price_type.value,
        notes=result.notes,
        breakdown=result.breakdown,
    )


LOCAL_BUS_FLAT_PLN = 4.0
"""PLACEHOLDER: ryczałt za jeden przejazd autobusem/tramwajem miejskim, używany TYLKO gdy
lokalny operator nie jest rozpoznany przez żaden moduł taryf komunikacji miejskiej (patrz
fares/ztm_lublin.py i fares/vrr.py) — np. transport miejski poza Lublinem i obszarem VRR."""


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


def price_bus_leg(leg: Leg, discounts: DiscountProfile | None = None) -> PricedLeg:
    """UWAGA (sprawdzone 2026-10-10, test realnym GTFS HVV/MVV/VRS w PR #49): ten kalkulator
    bywa wołany też dla legów, które MOTIS sklasyfikował jako "BUS" mimo że faktycznie są
    S-Bahn/U-Bahn obsługiwanym przez DB Regio (routing/motis_client.py::itinerary_to_legs
    mapuje każdy tryb MOTIS inny niż RAIL/TRAIN na LegMode.BUS, patrz komentarz tam). To NIE
    jest błąd do naprawy: HVV/MVV/Rheinlandtarif (VRS) to Verbundtarif obejmujący WSZYSTKIE
    lokalne środki transportu (S-Bahn, U-Bahn, tramwaj, autobus) w obrębie związku jedną,
    wspólną ceną zależną od strefy/relacji, niezależnie od operatora czy trybu — więc
    dopasowanie po nazwie przystanku/miasta (city_carriers poniżej) i wycena z taryfy
    związkowej jest poprawna, nawet gdy przewoźnik widoczny w danych to "DB Regio ..."."""
    discounts = discounts or DiscountProfile()

    is_coach = leg.extra.get("motis_mode") == "COACH" or any(
        k in leg.carrier_name.lower() for k in LONG_DISTANCE_COACH_KEYWORDS
    )
    if is_coach:
        if "flix" in leg.carrier_name.lower():
            return price_flixbus_leg(leg)
        return _fallback_priced_leg(leg, "Autokar dalekobieżny — brak modułu taryf.")

    tekst = f"{leg.carrier_name} {leg.origin_name} {leg.destination_name}".lower()

    city_carriers = [
        (ZTM_LUBLIN_KEYWORDS, Carrier.ZTM_LUBLIN),
        (ZTM_WARSZAWA_KEYWORDS, Carrier.ZTM_WARSZAWA),
        (MPK_KRAKOW_KEYWORDS, Carrier.MPK_KRAKOW),
        (ZTM_POZNAN_KEYWORDS, Carrier.ZTM_POZNAN),
        (MPK_WROCLAW_KEYWORDS, Carrier.MPK_WROCLAW),
        (BVG_BERLIN_KEYWORDS, Carrier.BVG_BERLIN),
        (HVV_KEYWORDS, Carrier.HVV),
        (MVV_KEYWORDS, Carrier.MVV),
        (VRS_KOLN_KEYWORDS, Carrier.VRS_KOLN),
    ]
    for keywords, carrier in city_carriers:
        if any(k in tekst for k in keywords):
            try:
                segment = Segment(
                    carrier=carrier,
                    origin=leg.origin_name,
                    destination=leg.destination_name,
                    ride_duration_min=leg.duration_min,
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
                    carrier=carrier,
                )
            except ValueError as exc:
                return _fallback_priced_leg(leg, f"Kalkulator {carrier.value} zwrócił błąd ({exc}).")

    # Cały niemiecki fragment sieci w tym silniku to NRW (Zagłębie Rury), więc lokalny
    # autobus/tramwaj tu jest domyślnie traktowany jako obszar taryfowy VRR (eezy.nrw) —
    # patrz VRR_AREA_KEYWORDS/infer_rail_carrier oraz fares/README.md.
    if leg.distance_km is not None:
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
            )
        except ValueError as exc:
            return _fallback_priced_leg(leg, f"Kalkulator VRR zwrócił błąd ({exc}).")

    return PricedLeg(
        leg=leg,
        amount=LOCAL_BUS_FLAT_PLN,
        currency="PLN",
        price_type="szacunek",
        notes="Ryczałt za przejazd komunikacją miejską (placeholder, nieznany operator lokalny).",
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
