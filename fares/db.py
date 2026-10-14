"""Szacowanie ceny segmentu DB: Flexpreis (górna granica) x mnożnik BahnCard.

Tabela pasm odległości w fares/data/db_flexpreis.json to nadal SZACUNEK — DB nie publikuje
oficjalnej tabeli cena-za-km (Flexpreis zależy dynamicznie od trasy/daty w systemie DB).
Mnożniki BahnCard 25/50 są potwierdzone oficjalnie (bahn.de/faq); mnożnik BahnCard 100 (0,0)
NIE ma potwierdzonego źródła ("bahncard_mnoznik_niepotwierdzone" w danych) — patrz "_zrodlo_bahncard".
Wiek NIE jest tu czytany: ulgi wiekowe DB krajowego (dzieci, seniorzy) nie są zamodelowane, bo nie
potwierdzono ich dosłownym cytatem z bahn.de (zob. fares/README.md). Patrz też README.md w tym katalogu.
"""

from . import _db_vendo_api, _unofficial
from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("db_flexpreis.json")


def _flexpreis_upper_bound(distance_km: float) -> float:
    for pasmo in _TABLE["pasma_odleglosci_km"]:
        if pasmo["do_km"] is None or distance_km <= pasmo["do_km"]:
            return pasmo["cena"]
    raise ValueError("brak pasma cenowego dla podanej odległości")


def flexpreis_upper_bound(distance_km: float) -> float:
    """Górna granica Flexpreis (bez BahnCard) dla danej odległości — używane też przez fares/cards.py
    do liczenia opłacalności BahnCard."""
    return _flexpreis_upper_bound(distance_km)


def _unofficial_estimate(segment, bahncard, upper_bound, table_amount) -> PriceEstimate | None:
    """OPCJONALNA cena z nieoficjalnego API DB (db-vendo-client). None = użyj tabeli pasm."""
    if not segment.travel_date or not _unofficial.enabled("db"):
        return None
    try:
        hit = _db_vendo_api.fetch_cheapest(
            segment.origin, segment.destination, segment.travel_date, segment.discounts.bahncard
        )
    except _db_vendo_api.DbVendoError:
        return None
    return PriceEstimate(
        carrier=Carrier.DB,
        amount=round(float(hit["amount"]), 2),
        currency=hit.get("currency", "EUR"),
        price_type=PriceType.ESTIMATE,
        breakdown={
            "zrodlo": "nieoficjalne_db_vendo",
            "data": segment.travel_date,
            "bahncard": bahncard,
            "z_cache": hit.get("z_cache"),
            "nasz_szacunek_z_tabeli": table_amount,
            "flexpreis_gorna_granica": upper_bound,
        },
        notes=(
            "Najniższa cena z NIEOFICJALNEGO API DB (db-vendo-client) dla podanej daty — "
            "szacunek, nie oficjalna taryfa: DB nie udostępnia oficjalnego API cen, ceny są "
            "dynamiczne, a źródło może zostać zablokowane. Po wyłączeniu UNOFFICIAL_PRICES "
            "wracamy do tabeli pasm (górna granica Flexpreis)."
        ),
    )


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
    mnoznik_niepotwierdzony = bahncard in _TABLE.get("bahncard_mnoznik_niepotwierdzone", [])

    unofficial = _unofficial_estimate(segment, bahncard, upper_bound, amount)
    if unofficial:
        return unofficial

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
            "mnoznik_potwierdzony": not mnoznik_niepotwierdzony,
        },
        notes=(
            "Flexpreis to górna granica z tabeli pasm odległości (nadal szacunek, patrz "
            "_uwaga w danych) — rzeczywista cena DB może być niższa i zależy od konkretnej "
            "trasy/pociągu. "
            + (
                f"Mnożnik BahnCard {bahncard} ({mnoznik}) jest NIEPOTWIERDZONY źródłem na bahn.de."
                if mnoznik_niepotwierdzony
                else "Mnożnik BahnCard jest oficjalny (bahn.de/faq)."
            )
        ),
    )
