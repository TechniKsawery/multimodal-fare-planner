"""Szacowanie ceny segmentu VRR wg aktualnej (2026) taryfy eezy.nrw:
cena = Grundpreis + cena_za_km x odległość w linii prostej, z sufitem cenowym.

Dane pochodzą z oficjalnej "Preistabelle ab 01.06.2026" VRR — patrz pole "_zrodlo"
w fares/data/vrr_eezy.json oraz README.md w tym katalogu. Sufit cenowy jest uproszczony
(patrz "_uwaga" w tym samym pliku) — nie mamy mapowania relacja -> strefa cenowa (A/B/C).
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("vrr_eezy.json")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.VRR:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora VRR: {segment.carrier}")
    if segment.distance_km is None:
        raise ValueError("VRR (eezy.nrw): distance_km jest wymagane (odległość w linii prostej)")

    surowa_cena = _TABLE["grundpreis"] + _TABLE["cena_za_km"] * segment.distance_km
    sufit = _TABLE["sufity_cenowe_einzelticket"][_TABLE["sufit_uzywany_domyslnie"]]
    amount = round(min(surowa_cena, sufit), 2)

    dziecko = segment.discounts.vrr_dziecko
    if dziecko:
        amount = round(amount * (1 - _TABLE["kindertarif_rabat_procent"] / 100), 2)

    return PriceEstimate(
        carrier=Carrier.VRR,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "grundpreis": _TABLE["grundpreis"],
            "cena_za_km": _TABLE["cena_za_km"],
            "odleglosc_km": segment.distance_km,
            "cena_przed_sufitem": round(surowa_cena, 2),
            "sufit_cenowy": sufit,
            "sufit_zastosowany": surowa_cena > sufit,
            "kindertarif": dziecko,
        },
        notes=(
            "Taryfa eezy.nrw (oficjalna, Stand 01.06.2026): Grundpreis + cena za km linii "
            "prostej, ograniczona sufitem ceny EinzelTicket dla najwyższej strefy sieciowej "
            "(Preisstufe C) — rzeczywisty sufit dla krótszych relacji może być niższy "
            "(Preisstufe A/B), patrz fares/data/vrr_eezy.json."
            + (
                f" Zastosowano Kindertarif: {_TABLE['kindertarif_rabat_procent']}% rabatu "
                "(dzieci 6-14 lat, oficjalny, wliczając sufit cenowy)."
                if dziecko
                else ""
            )
        ),
    )
