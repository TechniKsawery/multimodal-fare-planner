"""Sugestie zakupu karty rabatowej (BahnCard) — czy opłaca się kupić kartę na daną trasę.

W przeciwieństwie do ulg PKP Intercity (ustawowe, przysługują z tytułu wieku/statusu i są
wliczane bezpośrednio w fares/pkp.py przez DiscountProfile.pkp_ulga_kod), BahnCard to PRODUKT
DO KUPIENIA — stąd osobna logika: policz, czy roczny koszt karty zwróci się w oszczędnościach
na przewidywanej liczbie podróży, a jeśli nie, od ilu podróży rocznie się opłaci.

TODO: gdy w silniku pojawi się realne porównanie z lotami, doliczyć koszt bagażu do progu
opłacalności — dla kolei/autobusów w PL/DE bagaż jest bezpłatny i nie wpływa na wynik, ale
przy lotach bagaż rejestrowany bywa droższy niż sam bilet i realnie zmienia próg opłacalności.
"""
import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from ._data_loading import load
from .db import flexpreis_upper_bound

_TABLE = load("bahncard.json")


@dataclass
class CardSuggestion:
    """Wynik oceny opłacalności jednego wariantu karty na daną trasę/liczbę podróży."""

    variant_key: str
    nazwa: str
    cena_karty: float
    waluta: str
    oszczednosc_rocznie: float          # dodatnia = kupno się opłaca przy podanej liczbie podróży
    journeys_needed_to_break_even: Optional[int]  # None gdy karta już się opłaca; inaczej próg
    rekomendowana: bool
    opis: str


def _effective_price(wariant: dict, reference_date: date) -> float:
    promocja_do = wariant.get("promocja_do")
    if promocja_do and "cena_promocyjna" in wariant and reference_date <= date.fromisoformat(promocja_do):
        return wariant["cena_promocyjna"]
    return wariant["cena_roczna"]


def _eligible(wariant: dict, age: Optional[int]) -> bool:
    wiek_min, wiek_max = wariant["wiek_min"], wariant["wiek_max"]
    if wiek_min is None and wiek_max is None:
        return True  # standardowa BahnCard: dostępna niezależnie od wieku
    if age is None:
        return False  # wariant wymaga konkretnego wieku, a go nie podano
    return wiek_min <= age <= wiek_max


def suggest_bahncard(
    distance_km: float,
    journeys_per_year: int = 2,
    age: Optional[int] = None,
    reference_date: Optional[date] = None,
) -> List[CardSuggestion]:
    """Dla podanej odległości segmentu DB (Flexpreis, patrz fares/db.py) i przewidywanej liczby
    podróży rocznie (domyślnie 2 = jeden przejazd w obie strony), ocenia opłacalność każdego
    wariantu BahnCard, dla którego pasażer spełnia wymóg wieku. Wyniki posortowane: najpierw
    te, które już się opłacają (rosnąco wg progu wieku... a właściwie wg oszczędności malejąco),
    potem te wymagające większej liczby podróży (rosnąco wg progu)."""
    if distance_km <= 0:
        raise ValueError("distance_km musi być dodatnie")
    if journeys_per_year <= 0:
        raise ValueError("journeys_per_year musi być dodatnie")

    reference_date = reference_date or date.today()
    upper_bound = flexpreis_upper_bound(distance_km)
    waluta = _TABLE["waluta"]

    results: List[CardSuggestion] = []
    for key, wariant in _TABLE["warianty"].items():
        if not _eligible(wariant, age):
            continue

        cena_karty = _effective_price(wariant, reference_date)
        savings_per_journey = upper_bound * wariant["rabat_procent"] / 100
        oszczednosc_rocznie = round(savings_per_journey * journeys_per_year - cena_karty, 2)

        if oszczednosc_rocznie > 0:
            results.append(CardSuggestion(
                variant_key=key,
                nazwa=wariant["nazwa"],
                cena_karty=cena_karty,
                waluta=waluta,
                oszczednosc_rocznie=oszczednosc_rocznie,
                journeys_needed_to_break_even=None,
                rekomendowana=True,
                opis=(
                    f"Kup {wariant['nazwa']} za {cena_karty:.2f} {waluta} — przy {journeys_per_year} "
                    f"podróżach/rok na tej trasie zaoszczędzisz {oszczednosc_rocznie:.2f} {waluta}/rok."
                ),
            ))
        else:
            break_even = math.ceil(cena_karty / savings_per_journey) if savings_per_journey > 0 else None
            opis = (
                f"{wariant['nazwa']} ({cena_karty:.2f} {waluta}/rok) nie opłaca się przy "
                f"{journeys_per_year} podróżach/rok na tej trasie — opłaca się dopiero od "
                f"{break_even} podróży/rok."
                if break_even is not None else
                f"{wariant['nazwa']}: brak rabatu na Flexpreis, karta się nie zwróci."
            )
            results.append(CardSuggestion(
                variant_key=key,
                nazwa=wariant["nazwa"],
                cena_karty=cena_karty,
                waluta=waluta,
                oszczednosc_rocznie=oszczednosc_rocznie,
                journeys_needed_to_break_even=break_even,
                rekomendowana=False,
                opis=opis,
            ))

    results.sort(key=lambda r: (
        0 if r.rekomendowana else 1,
        -r.oszczednosc_rocznie if r.rekomendowana else (r.journeys_needed_to_break_even or math.inf),
    ))
    return results


def best_bahncard_suggestion(
    distance_km: float,
    journeys_per_year: int = 2,
    age: Optional[int] = None,
    reference_date: Optional[date] = None,
) -> Optional[CardSuggestion]:
    """Najlepszy wariant (pierwszy po sortowaniu suggest_bahncard) albo None, gdy pasażer nie
    kwalifikuje się do żadnego wariantu (np. wiek poza zakresem My/Jugend BahnCard bez podania
    wieku wcale — wtedy pod uwagę brane są tylko warianty standardowe)."""
    suggestions = suggest_bahncard(distance_km, journeys_per_year, age, reference_date)
    return suggestions[0] if suggestions else None
