"""Szacowanie ceny segmentu VRR: sztywna tabela cen dla wybranych relacji.

Dane w fares/data/vrr_relacje.json są PLACEHOLDEREM — patrz README.md w tym katalogu.
Tabela obejmuje tylko relacje, które w niej wprost występują (w obie strony).
"""
from .model import Carrier, PriceEstimate, PriceType, Segment
from ._data_loading import load

_TABLE = load("vrr_relacje.json")
_RELACJE = {
    frozenset((r["z"], r["do"])): r["cena"] for r in _TABLE["relacje"]
}


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.VRR:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora VRR: {segment.carrier}")

    key = frozenset((segment.origin, segment.destination))
    if key not in _RELACJE:
        raise ValueError(
            f"brak relacji {segment.origin} <-> {segment.destination} w tabeli VRR "
            "(tabela obejmuje tylko wybrane, przykładowe relacje)"
        )

    amount = _RELACJE[key]
    return PriceEstimate(
        carrier=Carrier.VRR,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={"relacja": f"{segment.origin} <-> {segment.destination}"},
        notes="Cena ze sztywnej, placeholderowej tabeli wybranych relacji VRR.",
    )
