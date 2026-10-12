"""Szacowanie ceny segmentu lotu: cena biletu (Travelpayouts) + bagaż + dojazd + transfer."""

from dataclasses import replace

from common.currency import convert, normalize_currency

from . import extras as extras_module
from . import travelpayouts
from .model import ExtrasProfile, FlightSegment, PriceEstimate, PriceType

GENERIC_FLIGHT_FALLBACK_PLN = 350.0
"""Kwota W ZŁOTYCH (dla innej waluty segmentu przeliczana placeholderowym kursem z
common/currency.py). Bardzo zgrubny szacunek ceny biletu (PL-DE, tania linia, w jedną stronę), używany TYLKO gdy
Travelpayouts nie ma w cache ceny ani dla dokładnej daty, ani dla całego miesiąca (relacja/data
zbyt egzotyczna) — patrz README.md. Nie oparty na żadnych realnych danych dla tej konkretnej
relacji, tylko na rzędzie wielkości typowych cen Ryanair/Wizz Air na krótkich trasach PL-DE."""


def _fetch_ticket(segment: FlightSegment):
    """Zwraca (ticket_dict, notatka_o_zrodle). Próbuje kolejno: dokładna data z cache
    Travelpayouts -> cały miesiąc z cache Travelpayouts (API akceptuje depart_date="YYYY-MM") ->
    zgrubny szacunek stały (breakdown["price_verified"]=False), gdy obie próby nie dały ceny lotu
    bezpośredniego dla tej relacji."""
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

    fallback_price = round(convert(GENERIC_FLIGHT_FALLBACK_PLN, "PLN", segment.currency), 2)
    in_segment_currency = (
        ""
        if segment.currency == "PLN"
        else f" (= {fallback_price:.2f} {segment.currency} kurs NBP z 2026-10-09, szacunek)"
    )
    return (
        {
            "price": fallback_price,
            "transfers": None,
            "airline": None,
            "departure_at": None,
            "price_verified": False,
        },
        (
            "Cena niepotwierdzona: brak ceny lotu BEZPOŚREDNIEGO w cache Travelpayouts dla tej "
            "relacji (ani dokładna data, ani cały miesiąc; wpisy z przesiadkami pomijamy) — "
            f"BARDZO ZGRUBNY szacunek stały ({GENERIC_FLIGHT_FALLBACK_PLN:.0f} PLN"
            f"{in_segment_currency}), nieoparty na realnych danych dla tej trasy."
        ),
    )


def _table_extras_in_currency(origin: str, destination: str, currency: str) -> ExtrasProfile:
    """Koszty dodatkowe z placeholderowej tabeli (zapisane w jej walucie, domyślnie PLN)
    przeliczone na walutę segmentu — bez przeliczenia kwoty w PLN dostałyby etykietę EUR."""
    table = extras_module.get_extras(origin, destination)
    if table.currency == currency:
        return table
    return ExtrasProfile(
        baggage_cost=round(convert(table.baggage_cost, table.currency, currency), 2),
        airport_access_cost=round(convert(table.airport_access_cost, table.currency, currency), 2),
        destination_transfer_cost=round(
            convert(table.destination_transfer_cost, table.currency, currency), 2
        ),
        currency=currency,
        note=f"{table.note} Przeliczone z {table.currency} na {currency} kursem NBP z 2026-10-09 (szacunek).",
    )


def estimate_price(segment: FlightSegment) -> PriceEstimate:
    # Waluta bez kursu = od razu czytelny błąd (UnsupportedCurrencyError), niezależnie od tego,
    # czy bilet przyjdzie z cache Travelpayouts, czy z szacunku stałego.
    segment = replace(segment, currency=normalize_currency(segment.currency))
    ticket, ticket_note = _fetch_ticket(segment)

    extras = segment.extras or _table_extras_in_currency(
        segment.origin, segment.destination, segment.currency
    )
    if extras.currency != segment.currency:
        raise ValueError(
            f"Waluta kosztów dodatkowych ({extras.currency}) różni się od waluty biletu "
            f"({segment.currency}) — podaj ExtrasProfile w tej samej walucie co segment."
        )

    total = round(ticket["price"] + extras.total, 2)

    notes = ticket_note
    if extras.note:
        notes += " " + extras.note

    breakdown = {
        "cena_biletu": ticket["price"],
        "przesiadki": ticket.get("transfers"),
        "linia": ticket.get("airline"),
        "wylot": ticket.get("departure_at"),
        "bagaz": extras.baggage_cost,
        "dojazd_na_lotnisko": extras.airport_access_cost,
        "transfer_z_lotniska": extras.destination_transfer_cost,
    }
    if ticket.get("price_verified") is False:
        breakdown["price_verified"] = False  # UI/demo dopisują "cena niepotwierdzona"

    return PriceEstimate(
        origin=segment.origin.upper(),
        destination=segment.destination.upper(),
        amount=total,
        currency=segment.currency,
        price_type=PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
