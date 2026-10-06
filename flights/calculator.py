"""Szacowanie ceny segmentu lotu: cena biletu (Travelpayouts) + bagaż + dojazd + transfer."""

from . import extras as extras_module
from . import travelpayouts
from .model import FlightSegment, PriceEstimate, PriceType

GENERIC_FLIGHT_FALLBACK_PLN = 350.0
"""Bardzo zgrubny szacunek ceny biletu (PL-DE, tania linia, w jedną stronę), używany TYLKO gdy
Travelpayouts nie ma w cache ceny ani dla dokładnej daty, ani dla całego miesiąca (relacja/data
zbyt egzotyczna) — patrz README.md. Nie oparty na żadnych realnych danych dla tej konkretnej
relacji, tylko na rzędzie wielkości typowych cen Ryanair/Wizz Air na krótkich trasach PL-DE."""


def _fetch_ticket(segment: FlightSegment):
    """Zwraca (ticket_dict, notatka_o_zrodle). Próbuje kolejno: dokładna data z cache
    Travelpayouts -> cały miesiąc z cache Travelpayouts (API akceptuje depart_date="YYYY-MM") ->
    zgrubny szacunek stały, gdy obie próby nie dały ceny dla tej relacji."""
    payload = travelpayouts.fetch_cheapest_price(
        origin=segment.origin,
        destination=segment.destination,
        depart_date=segment.depart_date,
        return_date=segment.return_date,
        currency=segment.currency,
    )
    ticket = travelpayouts.cheapest_entry_or_none(payload, segment.destination)
    if ticket is not None:
        return (
            ticket,
            "Cena biletu z cache Travelpayouts (dokładna data) — może być nieaktualna o kilka dni.",
        )

    month = segment.depart_date[:7]  # "YYYY-MM-DD" -> "YYYY-MM"
    if month != segment.depart_date:
        month_payload = travelpayouts.fetch_cheapest_price(
            origin=segment.origin,
            destination=segment.destination,
            depart_date=month,
            currency=segment.currency,
        )
        ticket = travelpayouts.cheapest_entry_or_none(month_payload, segment.destination)
        if ticket is not None:
            return ticket, (
                "Brak ceny w cache Travelpayouts dla dokładnej daty — cena z cache dla całego "
                f"miesiąca ({month}), może odbiegać od ceny na konkretny dzień."
            )

    return (
        {
            "price": GENERIC_FLIGHT_FALLBACK_PLN,
            "transfers": None,
            "airline": None,
            "departure_at": None,
        },
        (
            "Brak ceny w cache Travelpayouts dla tej relacji (ani dokładna data, ani cały miesiąc) — "
            f"BARDZO ZGRUBNY szacunek stały ({GENERIC_FLIGHT_FALLBACK_PLN:.0f} PLN), nieoparty na "
            "realnych danych dla tej trasy."
        ),
    )


def estimate_price(segment: FlightSegment) -> PriceEstimate:
    ticket, ticket_note = _fetch_ticket(segment)

    extras = segment.extras or extras_module.get_extras(segment.origin, segment.destination)
    if extras.currency != segment.currency:
        raise ValueError(
            f"Waluta kosztów dodatkowych ({extras.currency}) różni się od waluty biletu "
            f"({segment.currency}) — podaj ExtrasProfile w tej samej walucie co segment."
        )

    total = round(ticket["price"] + extras.total, 2)

    notes = ticket_note
    if extras.note:
        notes += " " + extras.note

    return PriceEstimate(
        origin=segment.origin.upper(),
        destination=segment.destination.upper(),
        amount=total,
        currency=segment.currency,
        price_type=PriceType.ESTIMATE,
        breakdown={
            "cena_biletu": ticket["price"],
            "przesiadki": ticket.get("transfers"),
            "linia": ticket.get("airline"),
            "wylot": ticket.get("departure_at"),
            "bagaz": extras.baggage_cost,
            "dojazd_na_lotnisko": extras.airport_access_cost,
            "transfer_z_lotniska": extras.destination_transfer_cost,
        },
        notes=notes,
    )
