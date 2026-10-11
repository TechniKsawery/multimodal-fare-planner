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

from ._data_loading import load
from .db import flexpreis_upper_bound

_TABLE = load("bahncard.json")
_MNOZNIK_TABLE = load("db_flexpreis.json")["bahncard_mnoznik"]


def _existing_discount_percent(existing_bahncard: str | None) -> float:
    """Rabat (%) już posiadanej karty (None/"brak" -> 0%), wyliczony z tej samej tabeli
    mnożników co realna cena biletu (fares/db.py), żeby oba miejsca były zawsze spójne."""
    mnoznik = _MNOZNIK_TABLE.get(existing_bahncard or "brak", 1.0)
    return round((1 - mnoznik) * 100)


@dataclass
class CardSuggestion:
    """Wynik oceny opłacalności jednego wariantu karty na daną trasę/liczbę podróży."""

    variant_key: str
    nazwa: str
    cena_karty: float
    waluta: str
    cena_biletu_bez_karty: float  # Flexpreis za JEDEN przejazd, bez karty
    cena_biletu_z_karta: float  # Flexpreis za JEDEN przejazd, z rabatem karty (bez samej karty)
    oszczednosc_rocznie: float  # dodatnia = kupno się opłaca przy podanej liczbie podróży
    journeys_needed_to_break_even: int | None  # None gdy karta już się opłaca; inaczej próg
    rekomendowana: bool
    opis: str


def _effective_price(wariant: dict, reference_date: date) -> float:
    promocja_do = wariant.get("promocja_do")
    promocja_od = wariant.get("promocja_od")
    if (
        promocja_do
        and "cena_promocyjna" in wariant
        and (not promocja_od or date.fromisoformat(promocja_od) <= reference_date)
        and reference_date <= date.fromisoformat(promocja_do)
    ):
        return wariant["cena_promocyjna"]
    return wariant["cena_roczna"]


def _eligible(wariant: dict, age: int | None) -> bool:
    wiek_min, wiek_max = wariant["wiek_min"], wariant["wiek_max"]
    if wiek_min is None and wiek_max is None:
        return True  # standardowa BahnCard: dostępna niezależnie od wieku
    if age is None:
        return False  # wariant wymaga konkretnego wieku, a go nie podano
    return wiek_min <= age <= wiek_max


def suggest_bahncard(
    distance_km: float,
    journeys_per_year: int = 2,
    age: int | None = None,
    reference_date: date | None = None,
    existing_bahncard: str | None = None,
) -> list[CardSuggestion]:
    """Dla podanej odległości JEDNEGO ciągłego odcinka DB (Flexpreis, patrz fares/db.py) i
    przewidywanej liczby podróży rocznie (domyślnie 2 = jeden przejazd w obie strony), ocenia
    opłacalność każdego wariantu BahnCard, dla którego pasażer spełnia wymóg wieku.

    Dla WARIANTU Z KILKOMA oddzielnymi biletami DB (np. przesiadka we Frankfurcie na inny
    pociąg dalekobieżny) NIE sumuj tu dystansów i nie wywołuj tej funkcji z sumą — pasma
    Flexpreis są nieliniowe (płaskie powyżej ok. 600 km), więc zbanowanie sumy dystansów jako
    jednego "megaodcinka" zaniża łączną cenę względem sumy realnie sprzedawanych biletów. Użyj
    zamiast tego suggest_bahncard_for_total_price() z sumą cen poszczególnych biletów — patrz
    routing/card_suggestions.py::suggest_bahncard_for_itinerary().

    existing_bahncard: karta, którą pasażer już zadeklarował w formularzu ("25"/"50"/"100"/None).
    Warianty o rabacie nie lepszym niż już posiadana karta są pomijane (nie ma sensu sugerować
    kupna karty, którą user już ma, albo gorszej) — a oszczędność liczona jest względem ceny,
    którą user faktycznie płaci już teraz (z posiadaną kartą), nie względem pełnego Flexpreis."""
    if distance_km <= 0:
        raise ValueError("distance_km musi być dodatnie")
    return suggest_bahncard_for_total_price(
        flexpreis_upper_bound(distance_km),
        journeys_per_year,
        age,
        reference_date,
        existing_bahncard,
    )


def suggest_bahncard_for_total_price(
    upper_bound: float,
    journeys_per_year: int = 2,
    age: int | None = None,
    reference_date: date | None = None,
    existing_bahncard: str | None = None,
) -> list[CardSuggestion]:
    """Jak suggest_bahncard(), ale przyjmuje już wyliczoną łączną cenę Flexpreis (bez karty) —
    dla wariantu z kilkoma biletami DB powinna to być SUMA cen poszczególnych biletów (każdy
    liczony ze swojego własnego pasma odległości), nie cena z jednego pasma dla sumy dystansów."""
    if upper_bound <= 0:
        raise ValueError("upper_bound musi być dodatnie")
    if journeys_per_year <= 0:
        raise ValueError("journeys_per_year musi być dodatnie")

    reference_date = reference_date or date.today()
    waluta = _TABLE["waluta"]

    existing_percent = _existing_discount_percent(existing_bahncard)
    current_price = round(upper_bound * (1 - existing_percent / 100), 2)

    results: list[CardSuggestion] = []
    for key, wariant in _TABLE["warianty"].items():
        if not _eligible(wariant, age):
            continue
        if wariant["rabat_procent"] <= existing_percent:
            # user ma już kartę z takim samym lub lepszym rabatem — nic do zasugerowania
            continue

        cena_karty = _effective_price(wariant, reference_date)
        cena_z_karta = round(upper_bound * (1 - wariant["rabat_procent"] / 100), 2)
        savings_per_journey = round(current_price - cena_z_karta, 2)
        oszczednosc_rocznie = round(savings_per_journey * journeys_per_year - cena_karty, 2)
        posiadana_info = (
            f" (masz już {existing_bahncard}% rabatu — obecna cena to {current_price:.2f} {waluta})"
            if existing_percent > 0
            else ""
        )

        if oszczednosc_rocznie > 0:
            results.append(
                CardSuggestion(
                    variant_key=key,
                    nazwa=wariant["nazwa"],
                    cena_karty=cena_karty,
                    waluta=waluta,
                    cena_biletu_bez_karty=current_price,
                    cena_biletu_z_karta=cena_z_karta,
                    oszczednosc_rocznie=oszczednosc_rocznie,
                    journeys_needed_to_break_even=None,
                    rekomendowana=True,
                    opis=(
                        f"Kup {wariant['nazwa']} za {cena_karty:.2f} {waluta} — bilet na tej trasie "
                        f"zapłacisz {cena_z_karta:.2f} {waluta} zamiast {current_price:.2f} {waluta}"
                        f"{posiadana_info}; przy {journeys_per_year} podróżach/rok zaoszczędzisz łącznie "
                        f"{oszczednosc_rocznie:.2f} {waluta}/rok (po odjęciu ceny karty)."
                    ),
                )
            )
        else:
            break_even = (
                math.ceil(cena_karty / savings_per_journey) if savings_per_journey > 0 else None
            )
            opis = (
                f"{wariant['nazwa']} ({cena_karty:.2f} {waluta}/rok): bilet na tej trasie kosztowałby "
                f"{cena_z_karta:.2f} {waluta} zamiast {current_price:.2f} {waluta}{posiadana_info}, ale "
                f"przy {journeys_per_year} podróżach/rok karta jeszcze się nie zwraca — opłaca się "
                f"dopiero od {break_even} podróży/rok."
                if break_even is not None
                else f"{wariant['nazwa']}: brak dodatkowego rabatu względem posiadanej karty, nie zwróci się."
            )
            results.append(
                CardSuggestion(
                    variant_key=key,
                    nazwa=wariant["nazwa"],
                    cena_karty=cena_karty,
                    waluta=waluta,
                    cena_biletu_bez_karty=current_price,
                    cena_biletu_z_karta=cena_z_karta,
                    oszczednosc_rocznie=oszczednosc_rocznie,
                    journeys_needed_to_break_even=break_even,
                    rekomendowana=False,
                    opis=opis,
                )
            )

    results.sort(
        key=lambda r: (
            0 if r.rekomendowana else 1,
            (
                -r.oszczednosc_rocznie
                if r.rekomendowana
                else (r.journeys_needed_to_break_even or math.inf)
            ),
        )
    )
    return results


def best_bahncard_suggestion(
    distance_km: float,
    journeys_per_year: int = 2,
    age: int | None = None,
    reference_date: date | None = None,
    existing_bahncard: str | None = None,
) -> CardSuggestion | None:
    """Najlepszy wariant (pierwszy po sortowaniu suggest_bahncard) albo None, gdy pasażer nie
    kwalifikuje się do żadnego wariantu (np. wiek poza zakresem My/Jugend BahnCard bez podania
    wieku wcale — wtedy pod uwagę brane są tylko warianty standardowe), albo gdy już posiada
    kartę z rabatem równym lub lepszym niż wszystkie dostępne warianty."""
    suggestions = suggest_bahncard(
        distance_km, journeys_per_year, age, reference_date, existing_bahncard
    )
    return suggestions[0] if suggestions else None
