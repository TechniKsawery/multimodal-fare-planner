"""Szacowanie ceny biletu MIĘDZYNARODOWEGO PL-DE (np. Berlin-Warszawa-Express, jeden ciągły
odcinek kolejowy przekraczający granicę) — SZTYWNE kategorie cenowe zależne od relacji (Super
Sparpreis Europa), NIE tabela pasm liniowa od km jak krajowe kalkulatory `fares/pkp.py` i
`fares/db.py`. BahnCard oficjalnie obniża tylko niemiecki odcinek trasy — nie mamy podziału
PL/DE w danych, więc to uproszczone. Patrz `_uwaga`/`_uwaga_bahncard` w
fares/data/international_pl_de.json dla pełnych zastrzeżeń i źródeł.

Pasażerowie 15-26 lat (`segment.discounts.age`) dostają osobną taryfę "Super Sparpreis Europa
Young" (bahn.de) — jedna cena "od" dla wszystkich relacji, NIE progi zależne od odległości jak
dla dorosłych (zob. `_uwaga_young` w danych). BahnCard działa identycznie jak dla dorosłych.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("international_pl_de.json")


def _tier(distance_km: float):
    for prog in _TABLE["progi_km"]:
        if prog["do_km"] is None or distance_km <= prog["do_km"]:
            return prog
    raise ValueError("brak progu cenowego dla podanej odległości")


def _is_young(age: int | None) -> bool:
    return age is not None and _TABLE["young_wiek_min"] <= age <= _TABLE["young_wiek_max"]


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.INTERNATIONAL_PL_DE:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora międzynarodowego: {segment.carrier}"
        )
    if segment.distance_km is None:
        raise ValueError("bilet międzynarodowy PL-DE: distance_km jest wymagane")

    young = _is_young(segment.discounts.age)
    if young:
        kategoria_relacji = "young"
        cena_od = _TABLE["young_cena_od"]
    else:
        prog = _tier(segment.distance_km)
        kategoria_relacji = prog["kategoria"]
        cena_od = prog["cena_od"]

    bahncard = segment.discounts.bahncard or "brak"
    rabaty = _TABLE["bahncard_rabat_procent"]
    if bahncard not in rabaty:
        raise ValueError(f"nieznana BahnCard: {bahncard!r}, dostępne: {list(rabaty)}")
    rabat_procent = rabaty[bahncard]

    fraction = segment.german_portion_fraction
    if fraction is None:
        # Brak współrzędnych do oszacowania podziału trasy -> rabat naliczany od CAŁEJ ceny.
        # To ZAWYŻA realny rabat (oficjalnie dotyczy tylko niemieckiego odcinka), ale bez
        # geografii nie mamy jak wydzielić część niemiecką — jedyny dostępny fallback.
        efektywny_rabat_procent = rabat_procent
        podzial_note = (
            "brak współrzędnych stacji — rabat naliczony od całej ceny biletu (zawyża realny rabat)"
        )
    else:
        fraction = max(0.0, min(1.0, fraction))
        efektywny_rabat_procent = rabat_procent * fraction
        podzial_note = (
            f"rabat naliczony proporcjonalnie do szacowanego udziału niemieckiego odcinka "
            f"trasy (~{fraction * 100:.0f}% dystansu w linii prostej)"
        )
    amount = round(cena_od * (1 - efektywny_rabat_procent / 100), 2)

    return PriceEstimate(
        carrier=Carrier.INTERNATIONAL_PL_DE,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "kategoria_relacji": kategoria_relacji,
            "cena_od": cena_od,
            "bahncard": bahncard,
            "rabat_procent_nominalny": rabat_procent,
            "udzial_niemieckiego_odcinka": fraction,
            "rabat_procent_efektywny": round(efektywny_rabat_procent, 1),
            "dystans_km_linia_prosta": round(segment.distance_km, 1),
            "wiek": segment.discounts.age,
        },
        notes=(
            (
                "Bilet międzynarodowy PL-DE, taryfa 'Super Sparpreis Europa Young' "
                f"({_TABLE['young_wiek_min']}-{_TABLE['young_wiek_max']} lat, bahn.de) — JEDNA "
                "cena 'od' dla wszystkich relacji (bahn.de nie podaje progów zależnych od "
                "odległości dla tej oferty, w przeciwieństwie do wersji dla dorosłych), "
                "promocyjna/ograniczona pula, realna cena rynkowa może być wyższa. "
                if young
                else f"Bilet międzynarodowy PL-DE, kategoria '{kategoria_relacji}' wg przybliżenia "
                "odległością w linii prostej (DB nie publikuje tabeli relacja->kategoria) — "
                "Super Sparpreis Europa, cena 'OD' (promocyjna, ograniczona pula miejsc), "
                "realna cena rynkowa może być wyższa. "
            )
            + "BahnCard (każdy poziom: 25/50/100) daje "
            f"nominalnie 25% zniżki, ale OFICJALNIE TYLKO na niemiecki odcinek trasy — {podzial_note}. "
            "Podział wg linii prostej i stałego przybliżonego punktu granicy — patrz "
            "_uwaga_bahncard w danych źródłowych i BORDER_CROSSING_PL_DE w routing/pricing.py."
        ),
    )
