"""Szacowanie ceny segmentu PKP Intercity: cena z tabeli pasm odległości x mnożnik ulgi.

Dane cenowe w fares/data/pkp_intercity.json są PLACEHOLDEREM — patrz README.md w tym katalogu.
"""
from .model import Carrier, PriceEstimate, PriceType, Segment
from ._data_loading import load

_TABLE = load("pkp_intercity.json")


def _base_price(distance_km: float) -> float:
    for pasmo in _TABLE["pasma_odleglosci_km"]:
        if pasmo["do_km"] is None or distance_km <= pasmo["do_km"]:
            return pasmo["cena"]
    raise ValueError("brak pasma cenowego dla podanej odległości")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.PKP_INTERCITY:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora PKP: {segment.carrier}")
    if segment.distance_km is None:
        raise ValueError("PKP Intercity: distance_km jest wymagane")

    ulga_kod = segment.discounts.pkp_ulga_kod
    ulgi = _TABLE["ulgi_procent"]
    if ulga_kod not in ulgi:
        raise ValueError(f"nieznany kod ulgi PKP: {ulga_kod!r}, dostępne: {list(ulgi)}")

    base = _base_price(segment.distance_km)
    ulga_procent = ulgi[ulga_kod]
    amount = round(base * (1 - ulga_procent / 100), 2)

    return PriceEstimate(
        carrier=Carrier.PKP_INTERCITY,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "cena_bazowa": base,
            "ulga_kod": ulga_kod,
            "ulga_procent": ulga_procent,
            "klasa": _TABLE["klasa"],
        },
        notes="Cena bazowa z placeholderowej tabeli pasm odległości — nie oficjalny cennik PKP IC.",
    )
