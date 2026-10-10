"""Szacowanie ceny segmentu komunikacji miejskiej HVV (Hamburg): Einzelkarte najniższej
strefy (1-2 Ringe / Hamburg AB).

Dane pochodzą z oficjalnego cennika HVV (Tarifstand 01.01.2026), zweryfikowanego w przeglądarce
— patrz pole "_zrodlo" w fares/data/hvv.json oraz README.md w tym katalogu. Taryfa HVV jest
strefowa (Ringe), a nie mamy mapowania przystanek->Ring, więc kalkulator zawsze liczy najniższą
strefę — to NIEDOSZACOWUJE realną cenę dla relacji obejmujących więcej Ringów.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("hvv.json")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.HVV:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora HVV: {segment.carrier}")

    dziecko = segment.discounts.hvv_dziecko
    bilet = _TABLE["einzelkarte_najnizsza_strefa"]
    amount = bilet["dziecko"] if dziecko else bilet["normalny"]

    return PriceEstimate(
        carrier=Carrier.HVV,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelkarte dziecko" if dziecko else "Einzelkarte normalny",
            "strefa": "1-2 Ringe / Hamburg AB (przybliżenie najniższej strefy)",
        },
        notes=(
            "Taryfa HVV (Tarifstand 01.01.2026): Einzelkarte najniższej strefy (1-2 Ringe / "
            "Hamburg AB). Brak mapowania przystanek->Ring — relacje obejmujące więcej Ringów "
            "są w rzeczywistości droższe niż ten wynik (patrz pełna tabela stref w "
            "fares/data/hvv.json)."
        ),
    )
