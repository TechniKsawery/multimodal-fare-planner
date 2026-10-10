"""Szacowanie ceny segmentu komunikacji miejskiej MVV (Monachium): Einzelkarte Zone M
(najniższa strefa, centrum Monachium).

Dane pochodzą z oficjalnego cennika MVV (ceny od 01.01.2026), zweryfikowanego w przeglądarce
— patrz pole "_zrodlo" w fares/data/mvv.json oraz README.md w tym katalogu. Taryfa MVV jest
strefowa (Zone M + strefy 1-12), a nie mamy mapowania przystanek->strefa, więc kalkulator
zawsze liczy Zone M — to NIEDOSZACOWUJE realną cenę dla relacji wychodzących poza Zone M.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("mvv.json")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.MVV:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora MVV: {segment.carrier}")

    dziecko = segment.discounts.mvv_dziecko
    bilet = _TABLE["einzelkarte_zone_m"]
    amount = bilet["dziecko"] if dziecko else bilet["normalny"]

    return PriceEstimate(
        carrier=Carrier.MVV,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelkarte dziecko" if dziecko else "Einzelkarte normalny",
            "strefa": "Zone M (przybliżenie najniższej strefy)",
        },
        notes=(
            "Taryfa MVV (ceny od 01.01.2026): Einzelkarte Zone M. Brak mapowania "
            "przystanek->strefa — relacje wychodzące poza Zone M (strefy 1-12) są w "
            "rzeczywistości droższe niż ten wynik."
        ),
    )
