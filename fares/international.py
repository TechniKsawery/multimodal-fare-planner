"""Szacowanie ceny biletu MIĘDZYNARODOWEGO PL-DE (np. Berlin-Warszawa-Express, jeden ciągły
odcinek kolejowy przekraczający granicę) — SZTYWNE kategorie cenowe zależne od relacji (Super
Sparpreis Europa), NIE tabela pasm liniowa od km jak krajowe kalkulatory `fares/pkp.py` i
`fares/db.py`. BahnCard oficjalnie obniża tylko niemiecki odcinek trasy — nie mamy podziału
PL/DE w danych, więc to uproszczone. Patrz `_uwaga`/`_uwaga_bahncard` w
fares/data/international_pl_de.json dla pełnych zastrzeżeń i źródeł.

Wiek pasażera (`segment.discounts.age`) wybiera jedną z czterech kategorii, w tej kolejności
pierwszeństwa (zob. `_uwaga_dziecko` w danych dla pełnych cytatów z bahn.de):
1. do 5 lat (wiek < `dziecko_bezplatnie_wiek_max`): zawsze gratis, niezależnie od reszty.
2. 6-14 lat Z opiekunem (`discounts.child_with_guardian`): też gratis.
3. 6-14 lat SAMODZIELNIE: normalna taryfa wg progu km, z 50% zniżką TYLKO na niemiecki odcinek
   trasy (ignoruje BahnCard — dziecko w tym wieku realnie nie ma własnej karty, nie łączymy).
4. 15-26 lat: taryfa "Super Sparpreis Europa Young" — jedna cena "od" dla wszystkich relacji,
   NIE progi zależne od odległości jak dla dorosłych (zob. `_uwaga_young` w danych). BahnCard
   działa identycznie jak dla dorosłych.
Brak wieku (None) albo wiek >=27: taryfa normalna wg progu km + BahnCard jak dotychczas. Nie ma
osobnej taryfy seniora na TEJ ofercie — "Super Sparpreis Senioren" (65+) to osobny, WYŁĄCZNIE
krajowy produkt DB, zweryfikowane 2026-10-09 (bahn.de/angebot/sparpreis-flexpreis/super-sparpreis-senioren).
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("international_pl_de.json")


def _tier(distance_km: float):
    for prog in _TABLE["progi_km"]:
        if prog["do_km"] is None or distance_km <= prog["do_km"]:
            return prog
    raise ValueError("brak progu cenowego dla podanej odległości")


def _is_infant_free(age: int | None) -> bool:
    return age is not None and age < _TABLE["dziecko_bezplatnie_wiek_max"]


def _is_child_age(age: int | None) -> bool:
    return age is not None and _TABLE["dziecko_wiek_min"] <= age <= _TABLE["dziecko_wiek_max"]


def _is_young(age: int | None) -> bool:
    return age is not None and _TABLE["young_wiek_min"] <= age <= _TABLE["young_wiek_max"]


def _german_portion_discount(nominal_rabat_procent: float, fraction: float | None) -> tuple[float, str]:
    """Wspólna logika dla rabatów obowiązujących TYLKO na niemiecki odcinek trasy (BahnCard i
    rabat dziecięcy 6-14 lat samodzielnie) — efektywny rabat na CAŁĄ cenę to rabat nominalny *
    udział niemieckiego odcinka; bez współrzędnych (fraction=None) fallback: rabat od całej ceny
    (zawyża realny rabat, ale to jedyny dostępny fallback bez geografii)."""
    if fraction is None:
        return nominal_rabat_procent, (
            "brak współrzędnych stacji — rabat naliczony od całej ceny (zawyża realny rabat)"
        )
    fraction = max(0.0, min(1.0, fraction))
    efektywny = nominal_rabat_procent * fraction
    return efektywny, (
        f"rabat naliczony proporcjonalnie do szacowanego udziału niemieckiego odcinka trasy "
        f"(~{fraction * 100:.0f}% dystansu w linii prostej)"
    )


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.INTERNATIONAL_PL_DE:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora międzynarodowego: {segment.carrier}"
        )
    if segment.distance_km is None:
        raise ValueError("bilet międzynarodowy PL-DE: distance_km jest wymagane")

    age = segment.discounts.age

    if _is_infant_free(age):
        return PriceEstimate(
            carrier=Carrier.INTERNATIONAL_PL_DE,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.ESTIMATE,
            breakdown={"kategoria_relacji": "niemowle", "wiek": age},
            notes=(
                f"Bilet międzynarodowy PL-DE, dziecko poniżej {_TABLE['dziecko_bezplatnie_wiek_max']} "
                "lat — zawsze przejazd bezpłatny (bahn.de, Super Sparpreis Europa Polen)."
            ),
        )

    if _is_child_age(age) and segment.discounts.child_with_guardian:
        return PriceEstimate(
            carrier=Carrier.INTERNATIONAL_PL_DE,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.ESTIMATE,
            breakdown={"kategoria_relacji": "dziecko_z_opiekunem", "wiek": age},
            notes=(
                f"Bilet międzynarodowy PL-DE, dziecko {_TABLE['dziecko_wiek_min']}-"
                f"{_TABLE['dziecko_wiek_max']} lat podróżujące w towarzystwie osoby od 15 lat — "
                "przejazd bezpłatny (bahn.de, Super Sparpreis Europa Polen), zgłoszone przy rezerwacji."
            ),
        )

    if _is_child_age(age):
        prog = _tier(segment.distance_km)
        cena_od = prog["cena_od"]
        rabat_procent = _TABLE["dziecko_samodzielnie_rabat_procent"]
        efektywny_rabat_procent, podzial_note = _german_portion_discount(
            rabat_procent, segment.german_portion_fraction
        )
        amount = round(cena_od * (1 - efektywny_rabat_procent / 100), 2)
        return PriceEstimate(
            carrier=Carrier.INTERNATIONAL_PL_DE,
            amount=amount,
            currency=_TABLE["waluta"],
            price_type=PriceType.ESTIMATE,
            breakdown={
                "kategoria_relacji": "dziecko_samodzielnie",
                "cena_od": cena_od,
                "wiek": age,
                "rabat_procent_nominalny": rabat_procent,
                "udzial_niemieckiego_odcinka": segment.german_portion_fraction,
                "rabat_procent_efektywny": round(efektywny_rabat_procent, 1),
            },
            notes=(
                f"Bilet międzynarodowy PL-DE, dziecko {_TABLE['dziecko_wiek_min']}-"
                f"{_TABLE['dziecko_wiek_max']} lat podróżujące SAMODZIELNIE — 50% zniżki, ale "
                f"TYLKO na niemiecki odcinek trasy (bahn.de): {podzial_note}. Polski odcinek "
                "pozostaje bez tego rabatu (konserwatywne uproszczenie — zaniża, nie zawyża, "
                "realny rabat na całość biletu). BahnCard pominięta dla tej kategorii wieku."
            ),
        )

    young = _is_young(age)
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

    efektywny_rabat_procent, podzial_note = _german_portion_discount(
        rabat_procent, segment.german_portion_fraction
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
            "udzial_niemieckiego_odcinka": segment.german_portion_fraction,
            "rabat_procent_efektywny": round(efektywny_rabat_procent, 1),
            "dystans_km_linia_prosta": round(segment.distance_km, 1),
            "wiek": age,
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
                "realna cena rynkowa może być wyższa. Brak osobnej taryfy seniora na tej "
                "ofercie — 'Super Sparpreis Senioren' (65+) to inny, wyłącznie krajowy produkt DB. "
            )
            + "BahnCard (każdy poziom: 25/50/100) daje "
            f"nominalnie 25% zniżki, ale OFICJALNIE TYLKO na niemiecki odcinek trasy — {podzial_note}. "
            "Podział wg linii prostej i stałego przybliżonego punktu granicy — patrz "
            "_uwaga_bahncard w danych źródłowych i BORDER_CROSSING_PL_DE w routing/pricing.py."
        ),
    )
