"""Szacowanie ceny segmentu lotu: cena biletu (Travelpayouts) + bagaż + dojazd + transfer."""
from . import extras as extras_module
from . import travelpayouts
from .model import FlightSegment, PriceEstimate, PriceType


def estimate_price(segment: FlightSegment) -> PriceEstimate:
    payload = travelpayouts.fetch_cheapest_price(
        origin=segment.origin,
        destination=segment.destination,
        depart_date=segment.depart_date,
        return_date=segment.return_date,
        currency=segment.currency,
    )
    ticket = travelpayouts.cheapest_entry(payload, segment.destination)

    extras = segment.extras or extras_module.get_extras(segment.origin, segment.destination)
    if extras.currency != segment.currency:
        raise ValueError(
            f"Waluta kosztów dodatkowych ({extras.currency}) różni się od waluty biletu "
            f"({segment.currency}) — podaj ExtrasProfile w tej samej walucie co segment."
        )

    total = round(ticket["price"] + extras.total, 2)

    notes = "Cena biletu z cache Travelpayouts — może być nieaktualna o kilka dni."
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
