"""Wycena pojedynczego odcinka: dispatch do fares/ (kolej) albo flights/ (lot)."""
from typing import Optional

from fares import estimate_price as fares_estimate_price
from fares.model import Carrier, DiscountProfile, Segment
from flights import ExtrasProfile, FlightSegment, TravelpayoutsError
from flights import estimate_price as flights_estimate_price
from flights.extras import get_baggage_by_airline, get_extras as flights_get_extras

from .currency import convert as convert_currency
from .model import Leg, LegMode, PricedLeg

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

ZTM_LUBLIN_KEYWORDS = ("lublin", "zditm", "ztm")
"""Fragmenty agencyName/nazw przystanków traktowane jako komunikacja miejska ZTM Lublin."""


def infer_rail_carrier(agency_name: str) -> Optional[Carrier]:
    """Zgrubne mapowanie agencyName z MOTIS na przewoźnika z modułu fares/.

    To PRZYBLIŻENIE: każdy niemiecki regionalny przewoźnik poza DB Fernverkehr (S-Bahn,
    Abellio, National Express, ...) jest tu traktowany jak VRR, choć w rzeczywistości różne
    związki taryfowe (VRR, VRS, ...) obowiązują w różnych regionach Niemiec.
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


def price_rail_leg(leg: Leg, discounts: DiscountProfile) -> PricedLeg:
    if leg.mode is not LegMode.RAIL:
        raise ValueError(f"price_rail_leg wymaga LegMode.RAIL, dostał {leg.mode}")

    carrier = infer_rail_carrier(leg.carrier_name)
    if carrier is None:
        return _fallback_priced_leg(
            leg, f"Brak modułu taryf dla przewoźnika '{leg.carrier_name}'."
        )

    try:
        segment = Segment(
            carrier=carrier,
            origin=leg.origin_name,
            destination=leg.destination_name,
            distance_km=leg.distance_km,
            discounts=discounts,
        )
        result = fares_estimate_price(segment)
    except ValueError as exc:
        return _fallback_priced_leg(leg, f"Kalkulator {carrier.value} zwrócił błąd ({exc}).")

    return PricedLeg(
        leg=leg,
        amount=result.amount,
        currency=result.currency,
        price_type=result.price_type.value,
        notes=result.notes,
    )


def price_flight_leg(leg: Leg, currency: str = "PLN") -> PricedLeg:
    if leg.mode is not LegMode.FLIGHT:
        raise ValueError(f"price_flight_leg wymaga LegMode.FLIGHT, dostał {leg.mode}")

    origin_iata = leg.extra["origin_iata"]
    destination_iata = leg.extra["destination_iata"]
    segment = FlightSegment(
        origin=origin_iata,
        destination=destination_iata,
        depart_date=leg.extra["depart_date"],
        currency=currency,
        extras=_flight_baggage_only_extras(origin_iata, destination_iata, currency),
    )
    result = flights_estimate_price(segment)  # może podnieść TravelpayoutsError — obsługa wyżej (variants.py)

    # Dociągamy REALNY cennik bagażu wg linii z biletu (result.breakdown["linia"], np. "FR" dla
    # Ryanaira), jeśli go znamy — nadpisuje szacunek z tabeli relacji/domyślny użyty wyżej
    # w _flight_baggage_only_extras (ten nie znał jeszcze linii, bo poznajemy ją dopiero z
    # odpowiedzi Travelpayouts).
    airline_baggage = get_baggage_by_airline(result.breakdown.get("linia"))
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
        leg=leg, amount=result.amount, currency=result.currency,
        price_type=result.price_type.value, notes=result.notes,
    )


def price_bus_leg(leg: Leg, discounts: Optional[DiscountProfile] = None) -> PricedLeg:
    discounts = discounts or DiscountProfile()

    is_coach = leg.extra.get("motis_mode") == "COACH" or any(
        k in leg.carrier_name.lower() for k in LONG_DISTANCE_COACH_KEYWORDS
    )
    if is_coach:
        if "flix" in leg.carrier_name.lower():
            return price_flixbus_leg(leg)
        return _fallback_priced_leg(leg, "Autokar dalekobieżny — brak modułu taryf.")

    tekst = f"{leg.carrier_name} {leg.origin_name} {leg.destination_name}".lower()

    if any(k in tekst for k in ZTM_LUBLIN_KEYWORDS):
        try:
            segment = Segment(
                carrier=Carrier.ZTM_LUBLIN,
                origin=leg.origin_name,
                destination=leg.destination_name,
                ride_duration_min=leg.duration_min,
                discounts=discounts,
            )
            result = fares_estimate_price(segment)
            return PricedLeg(
                leg=leg, amount=result.amount, currency=result.currency,
                price_type=result.price_type.value, notes=result.notes,
            )
        except ValueError as exc:
            return _fallback_priced_leg(leg, f"Kalkulator ZTM Lublin zwrócił błąd ({exc}).")

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
                leg=leg, amount=result.amount, currency=result.currency,
                price_type=result.price_type.value, notes=result.notes,
            )
        except ValueError as exc:
            return _fallback_priced_leg(leg, f"Kalkulator VRR zwrócił błąd ({exc}).")

    return PricedLeg(
        leg=leg, amount=LOCAL_BUS_FLAT_PLN, currency="PLN", price_type="szacunek",
        notes="Ryczałt za przejazd komunikacją miejską (placeholder, nieznany operator lokalny).",
    )


def price_walk_leg(leg: Leg) -> PricedLeg:
    return PricedLeg(leg=leg, amount=0.0, currency="PLN", price_type="oficjalna_taryfa", notes="Dojście pieszo.")


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
