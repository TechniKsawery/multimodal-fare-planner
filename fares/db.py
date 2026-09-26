"""Szacowanie ceny segmentu DB: Flexpreis (górna granica) x mnożnik BahnCard.

Dane cenowe w fares/data/db_flexpreis.json są PLACEHOLDEREM — patrz README.md w tym katalogu.
Prawdziwy Flexpreis nie jest funkcją samej odległości (zależy od konkretnej trasy w systemie DB),
więc ten kalkulator daje tylko orientacyjny górny szacunek.
"""
from .model import Carrier, PriceEstimate, PriceType, Segment
from ._data_loading import load

_TABLE = load("db_flexpreis.json")


def _flexpreis_upper_bound(distance_km: float) -> float:
    for pasmo in _TABLE["pasma_odleglosci_km"]:
        if pasmo["do_km"] is None or distance_km <= pasmo["do_km"]:
            return pasmo["cena"]
    raise ValueError("brak pasma cenowego dla podanej odległości")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.DB:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora DB: {segment.carrier}")
    if segment.distance_km is None:
        raise ValueError("DB: distance_km jest wymagane")

    bahncard = segment.discounts.bahncard or "brak"
    mnozniki = _TABLE["bahncard_mnoznik"]
    if bahncard not in mnozniki:
        raise ValueError(f"nieznana BahnCard: {bahncard!r}, dostępne: {list(mnozniki)}")

    upper_bound = _flexpreis_upper_bound(segment.distance_km)
    mnoznik = mnozniki[bahncard]
    amount = round(upper_bound * mnoznik, 2)

    return PriceEstimate(
        carrier=Carrier.DB,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "flexpreis_gorna_granica": upper_bound,
            "bahncard": bahncard,
            "mnoznik": mnoznik,
            "klasa": _TABLE["klasa"],
        },
        notes=(
            "Flexpreis to górna granica z placeholderowej tabeli pasm odległości — "
            "rzeczywista cena DB może być niższa i zależy od konkretnej trasy/pociągu."
        ),
    )
