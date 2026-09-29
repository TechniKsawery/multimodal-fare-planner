"""Szacowanie ceny biletu MIĘDZYNARODOWEGO PL-DE (np. Berlin-Warszawa-Express, jeden ciągły
odcinek kolejowy przekraczający granicę) — SZTYWNE kategorie cenowe zależne od relacji (Super
Sparpreis Europa), NIE tabela pasm liniowa od km jak krajowe kalkulatory `fares/pkp.py` i
`fares/db.py`. BahnCard oficjalnie obniża tylko niemiecki odcinek trasy — nie mamy podziału
PL/DE w danych, więc to uproszczone. Patrz `_uwaga`/`_uwaga_bahncard` w
fares/data/international_pl_de.json dla pełnych zastrzeżeń i źródeł.
"""
from .model import Carrier, PriceEstimate, PriceType, Segment
from ._data_loading import load

_TABLE = load("international_pl_de.json")


def _tier(distance_km: float):
    for prog in _TABLE["progi_km"]:
        if prog["do_km"] is None or distance_km <= prog["do_km"]:
            return prog
    raise ValueError("brak progu cenowego dla podanej odległości")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.INTERNATIONAL_PL_DE:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora międzynarodowego: {segment.carrier}")
    if segment.distance_km is None:
        raise ValueError("bilet międzynarodowy PL-DE: distance_km jest wymagane")

    prog = _tier(segment.distance_km)
    cena_od = prog["cena_od"]

    bahncard = segment.discounts.bahncard or "brak"
    rabaty = _TABLE["bahncard_rabat_procent"]
    if bahncard not in rabaty:
        raise ValueError(f"nieznana BahnCard: {bahncard!r}, dostępne: {list(rabaty)}")
    rabat_procent = rabaty[bahncard]
    amount = round(cena_od * (1 - rabat_procent / 100), 2)

    return PriceEstimate(
        carrier=Carrier.INTERNATIONAL_PL_DE,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "kategoria_relacji": prog["kategoria"],
            "cena_od": cena_od,
            "bahncard": bahncard,
            "rabat_procent": rabat_procent,
            "dystans_km_linia_prosta": round(segment.distance_km, 1),
        },
        notes=(
            f"Bilet międzynarodowy PL-DE, kategoria '{prog['kategoria']}' wg przybliżenia "
            "odległością w linii prostej (DB nie publikuje tabeli relacja->kategoria) — "
            "Super Sparpreis Europa, cena 'OD' (promocyjna, ograniczona pula miejsc), "
            "realna cena rynkowa może być wyższa. BahnCard oficjalnie obniża tylko niemiecki "
            "odcinek trasy — nie mamy podziału PL/DE, rabat powyżej jest uproszczeniem "
            "(patrz _uwaga_bahncard w danych źródłowych)."
        ),
    )
