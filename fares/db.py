"""Szacowanie ceny segmentu DB: Flexpreis (górna granica) x mnożnik BahnCard oraz ulgi wiekowe.

Tabela pasm odległości w fares/data/db_flexpreis.json to nadal SZACUNEK — DB nie publikuje
oficjalnej tabeli cena-za-km (Flexpreis zależy dynamicznie od trasy/daty w systemie DB).
Mnożniki BahnCard 25/50 oraz BahnCard 100 (0,0) są potwierdzone oficjalnie na bahn.de
(bahn.de/faq oraz bahn.de/angebot, zweryfikowano 2026-10-14).
Ulgi wiekowe DB krajowego (dzieci) są zamodelowane na podstawie dosłownych cytatów z bahn.de
(zweryfikowano 2026-10-14):
1. Dzieci do 5 lat (wiek < 6): bezpłatnie i bez biletu.
2. Dzieci 6–14 lat z opiekunem (osobą od 15 lat, child_with_guardian=True): bezpłatnie.
3. Dzieci 6–14 lat samodzielnie (child_with_guardian=False): 50% rabatu na Flexpreis.
Seniorzy (65+): w krajowej taryfie Flexpreis DB nie ma ulgi wiekowej dla seniorów (zweryfikowano
2026-10-14 na bahn.de/angebot/sparpreis-flexpreis/flexpreis; oferta Super Sparpreis Senioren
to osobny produkt taryfowy, a nie ulga na Flexpreis).
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


def _is_infant_free(age: int | None) -> bool:
    return age is not None and age < _TABLE.get("dziecko_bezplatnie_wiek_max", 6)


def _is_child_age(age: int | None) -> bool:
    min_age = _TABLE.get("dziecko_wiek_min", 6)
    max_age = _TABLE.get("dziecko_wiek_max", 14)
    return age is not None and min_age <= age <= max_age


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
    mnoznik_niepotwierdzony = bahncard in _TABLE.get("bahncard_mnoznik_niepotwierdzone", [])

    age = segment.discounts.age
    child_with_guardian = segment.discounts.child_with_guardian

    if _is_infant_free(age):
        return PriceEstimate(
            carrier=Carrier.DB,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.ESTIMATE,
            breakdown={
                "flexpreis_gorna_granica": upper_bound,
                "bahncard": bahncard,
                "mnoznik": mnoznik,
                "klasa": _TABLE["klasa"],
                "mnoznik_potwierdzony": not mnoznik_niepotwierdzony,
                "wiek": age,
                "kategoria_wiekowa": "dziecko_do_5_lat",
            },
            notes=(
                "Flexpreis DB (krajowy): dziecko poniżej 6 lat podróżuje bezpłatnie i bez biletu: "
                "'Kinder im Alter von 0 bis inklusive 5 Jahre reisen innerhalb Deutschlands immer "
                "kostenfrei und ohne eigene Fahrkarte' (bahn.de, zweryfikowano 2026-10-14)."
            ),
        )

    if _is_child_age(age) and child_with_guardian:
        return PriceEstimate(
            carrier=Carrier.DB,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.ESTIMATE,
            breakdown={
                "flexpreis_gorna_granica": upper_bound,
                "bahncard": bahncard,
                "mnoznik": mnoznik,
                "klasa": _TABLE["klasa"],
                "mnoznik_potwierdzony": not mnoznik_niepotwierdzony,
                "wiek": age,
                "child_with_guardian": True,
                "kategoria_wiekowa": "dziecko_6_14_z_opiekunem",
            },
            notes=(
                "Flexpreis DB (krajowy): dziecko 6–14 lat podróżujące w towarzystwie osoby od 15 lat "
                "podróżuje bezpłatnie: 'Kinder im Alter von 6 bis inklusive 14 Jahre fahren in "
                "Begleitung von Reisenden ab 15 Jahre kostenfrei' (bahn.de, zweryfikowano 2026-10-14)."
            ),
        )

    if _is_child_age(age) and not child_with_guardian:
        child_discount_pct = float(_TABLE.get("dziecko_samodzielnie_rabat_procent", 50))
        child_multiplier = 1.0 - (child_discount_pct / 100.0)
        effective_multiplier = child_multiplier * mnoznik
        amount = round(upper_bound * effective_multiplier, 2)

        unofficial = _unofficial_estimate(segment, bahncard, upper_bound, amount)
        if unofficial and amount > 0:
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
                "ulga_dziecieca_rabat_procent": child_discount_pct,
                "ulga_dziecieca_mnoznik": child_multiplier,
                "efektywny_mnoznik": effective_multiplier,
                "klasa": _TABLE["klasa"],
                "mnoznik_potwierdzony": not mnoznik_niepotwierdzony,
                "wiek": age,
                "child_with_guardian": False,
                "kategoria_wiekowa": "dziecko_6_14_samodzielnie",
            },
            notes=(
                "Flexpreis to górna granica z tabeli pasm odległości (szacunek). Dziecko 6–14 lat "
                "podróżujące SAMODZIELNIE otrzymuje 50% rabatu na Flexpreis: 'Allein reisende Kinder "
                "erhalten bis zu ihrem 15. Geburtstag 50 % Rabatt auf Flexpreis- oder Sparpreis-Tickets' "
                "(bahn.de, zweryfikowano 2026-10-14). "
                + (
                    f"Mnożnik BahnCard {bahncard} ({mnoznik}) jest NIEPOTWIERDZONY źródłem na bahn.de."
                    if mnoznik_niepotwierdzony
                    else "Mnożnik BahnCard jest oficjalny (bahn.de/faq)."
                )
            ),
        )

    amount = round(upper_bound * mnoznik, 2)
    unofficial = _unofficial_estimate(segment, bahncard, upper_bound, amount)
    if unofficial and amount > 0:
        return unofficial

    breakdown = {
        "flexpreis_gorna_granica": upper_bound,
        "bahncard": bahncard,
        "mnoznik": mnoznik,
        "klasa": _TABLE["klasa"],
        "mnoznik_potwierdzony": not mnoznik_niepotwierdzony,
    }
    if age is not None:
        breakdown["wiek"] = age

    return PriceEstimate(
        carrier=Carrier.DB,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown=breakdown,
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

