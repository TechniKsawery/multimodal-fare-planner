"""Agregacja odcinków w Itinerary i wybór rekomendacji.

Metoda scoringu "najlepszy stosunek ceny do czasu": cena_pln / czas_w_godzinach (PLN/h),
niżej = lepiej. To jedna prosta, znormalizowana miara łącząca oba kryteria bez wag do
ręcznego ustawiania — patrz README.md po dłuższe wyjaśnienie i alternatywy.

Metoda scoringu "najlepszy kompromis": każdy wariant dostaje pozycję 0..1 w cenie i pozycję
0..1 w czasie WZGLĘDEM pozostałych wariantów (0 = najlepszy w danej puli, 1 = najgorszy),
średnia z obu po równej wadze, niżej = lepiej. W odróżnieniu od "najlepszy stosunek cena/czas"
nie ma tu żadnej stałej do kalibrowania (jak VALUE_OF_TIME_PLN_PER_HOUR) — wynik zależy tylko
od tego, jak dany wariant wypada na tle innych znalezionych wariantów tej samej trasy, więc
jest wprost do wytłumaczenia: "trasa najbliżej czołówki jednocześnie w cenie i w czasie".

Metoda scoringu "najszybsza (z Twoimi ulgami)": inaczej niż "najlepszy kompromis" (który może
wybrać wyraźnie wolniejszy wariant, jeśli jest dużo tańszy), ta kategoria ZAWSZE trzyma się
czubka rankingu czasowego — cena rozstrzyga tylko remisy/prawie-remisy w czasie. Bierze
wszystkie warianty w tolerancji od najszybszego czasu (patrz FASTEST_TOLERANCE_* niżej) i
wybiera wśród nich najtańszy, czyli z uwzględnieniem konkretnych ulg usera (BahnCard, ulgi
PKP itd. są już wliczone w total_price_pln każdego wariantu).

"Najtańsza" (i "Najtańsza bezpieczna") najpierw porównuje warianty z potwierdzoną ceną
(Itinerary.price_verified): wariant z odcinkiem bez taryfy (szacunek PLN/km albo wartość
zastępcza LOCAL_BUS_FLAT_PLN, patrz routing/pricing.py) nie wygrywa z wariantem o potwierdzonej
cenie, nawet gdy jego suma jest nominalnie niższa — ta suma nie jest ceną, tylko zgrubnym
oszacowaniem. Gdy żaden wariant nie ma potwierdzonej ceny, wygrywa najtańszy nominalnie, a UI i
demo.py oznaczają go jako cenę niepotwierdzoną. Pozostałe kategorie się nie zmieniają.
"""

from .currency import to_pln
from .model import Itinerary, LegMode, PricedLeg
from .transfers import check_all_transfers

RECOMMENDATION_LABELS = {
    "najtansza": "Najtańsza",
    "najszybsza": "Najszybsza",
    "najmniej_przesiadek": "Najmniej przesiadek",
    "najlepszy_stosunek_ceny_do_czasu": "Najlepszy stosunek cena/czas",
    "najlepszy_kompromis": "Najlepszy kompromis",
    "najszybsza_z_ulgami": "Najszybsza (z Twoimi ulgami)",
    "najszybsza_bezpieczna": "Najszybsza bezpieczna",
    "najtansza_bezpieczna": "Najtańsza bezpieczna",
    "najlepszy_kompromis_bezpieczny": "Najlepszy kompromis (bezpieczny)",
    "najszybsza_z_ulgami_bezpieczna": "Najszybsza z ulgami (bezpieczna)",
    "najmniej_przesiadek_bezpieczna": "Najmniej przesiadek (bezpieczna)",
}

SAFE_CATEGORY_KEYS = (
    "najszybsza_bezpieczna",
    "najtansza_bezpieczna",
    "najlepszy_kompromis_bezpieczny",
    "najszybsza_z_ulgami_bezpieczna",
    "najmniej_przesiadek_bezpieczna",
)

# Kategorie, w których o wyborze decyduje cena: wariant z ceną niepotwierdzoną przegrywa w nich
# z wariantem o potwierdzonej cenie (patrz docstring modułu i cheaper_unverified niżej).
PRICE_RANKED_KEYS = ("najtansza", "najtansza_bezpieczna")

# Kategorie pokazywane od razu w UI (reszta pod "Pokaż więcej" — patrz app.py). Dwa ekstrema
# (najtańsza, najszybsza) + dwie "inteligentne" kategorie łączące cenę i czas (kompromis,
# najszybsza z ulgami) — to cztery najbardziej różne od siebie punkty widzenia na tę samą
# trasę, więc razem dają najlepszy przegląd bez przytłaczania. Warianty "_bezpieczna" i węższe
# kategorie (najmniej przesiadek, stosunek cena/czas) zostają pod rozwinięciem.
TOP_CATEGORY_KEYS = (
    "najtansza",
    "najszybsza",
    "najlepszy_kompromis",
    "najszybsza_z_ulgami",
)

# Próg "blisko najszybszego" dla kategorii "najszybsza (z Twoimi ulgami)": większa z dwóch
# wartości, żeby sensownie skalować i dla krótkich tras regionalnych, i dla długich
# międzynarodowych (patrz README.md) — 10% czasu najszybszego wariantu, ale nie mniej niż
# 10 minut (żeby dla bardzo krótkich tras próg nie był śmiesznie ciasny).
FASTEST_TOLERANCE_FRACTION = 0.10
FASTEST_TOLERANCE_MIN_MINUTES = 10


def _compromise_key(pool: list[Itinerary]):
    """Buduje funkcję key() do min(): średnia znormalizowanej (0..1) pozycji w cenie i czasie
    WZGLĘDEM `pool` (nie względem wszystkich wariantów w ogóle — patrz docstring modułu)."""
    prices = [i.total_price_pln for i in pool]
    durations = [i.total_duration_min for i in pool]
    p_lo, p_hi = min(prices), max(prices)
    d_lo, d_hi = min(durations), max(durations)

    def norm(value: float, lo: float, hi: float) -> float:
        return 0.0 if hi <= lo else (value - lo) / (hi - lo)

    def key(itinerary: Itinerary) -> float:
        return (
            norm(itinerary.total_price_pln, p_lo, p_hi)
            + norm(itinerary.total_duration_min, d_lo, d_hi)
        ) / 2

    return key


def _fastest_within_tolerance(pool: list[Itinerary], key=lambda i: i.total_price_pln) -> Itinerary:
    """Spośród `pool` bierze warianty w tolerancji od najszybszego czasu (FASTEST_TOLERANCE_*)
    i zwraca ten najlepszy wg `key` (domyślnie najtańszy) spośród nich."""
    fastest_duration = min(i.total_duration_min for i in pool)
    tolerance = max(fastest_duration * FASTEST_TOLERANCE_FRACTION, FASTEST_TOLERANCE_MIN_MINUTES)
    candidates = [i for i in pool if i.total_duration_min <= fastest_duration + tolerance]
    return min(candidates, key=key)


def cheaper_unverified(itineraries: list[Itinerary], chosen: Itinerary) -> list[Itinerary]:
    """Wykonalne warianty z ceną niepotwierdzoną, nominalnie tańsze od `chosen` (od
    najtańszego) — te, które ranking "Najtańsza" pominął na rzecz wariantu z potwierdzoną ceną.
    UI i demo.py pokazują je jako informację, nie jako rekomendację."""
    return sorted(
        (
            i
            for i in itineraries
            if not i.is_infeasible
            and not i.price_verified
            and i.total_price_pln < chosen.total_price_pln
        ),
        key=lambda i: i.total_price_pln,
    )


def price_ranking_note(key: str, chosen: Itinerary, itineraries: list[Itinerary]) -> str | None:
    """Wspólny dla UI i demo.py dopisek pod kategorią z PRICE_RANKED_KEYS: czy wygrał wariant z
    ceną niepotwierdzoną (bo żaden nie miał potwierdzonej) albo czy pominięto nominalnie tańsze
    warianty z ceną niepotwierdzoną. None, gdy nie ma czego dopisać."""
    if key not in PRICE_RANKED_KEYS:
        return None
    if not chosen.price_verified:
        return (
            "Żaden wariant w tej kategorii nie ma w pełni potwierdzonej ceny — to najtańszy wg "
            "cen niepotwierdzonych (szacunek), porównuj ostrożnie."
        )
    if key != "najtansza":
        return None
    skipped = cheaper_unverified(itineraries, chosen)
    if not skipped:
        return None
    cheapest = skipped[0]
    return (
        f"Pominięto {len(skipped)} wariant(y) nominalnie tańsze, ale z ceną niepotwierdzoną "
        f"(np. {cheapest.variant_name}: {cheapest.total_price_pln:.2f} PLN) — ich suma zawiera "
        "odcinki bez potwierdzonej taryfy."
    )


def build_itinerary(variant_name: str, priced_legs: list[PricedLeg]) -> Itinerary:
    if not priced_legs:
        raise ValueError(f"wariant '{variant_name}': brak odcinków")

    total_price_pln = sum(to_pln(pl.amount, pl.currency) for pl in priced_legs)
    total_duration_min = (
        priced_legs[-1].leg.arrive - priced_legs[0].leg.depart
    ).total_seconds() / 60
    legs_only = [pl.leg for pl in priced_legs]
    has_range = any("zakres_cen" in pl.breakdown for pl in priced_legs)
    total_price_pln_high = (
        round(
            sum(
                to_pln(pl.breakdown["zakres_cen"]["do"], pl.breakdown["zakres_cen"]["waluta"])
                if "zakres_cen" in pl.breakdown
                else to_pln(pl.amount, pl.currency)
                for pl in priced_legs
            ),
            2,
        )
        if has_range
        else None
    )

    return Itinerary(
        variant_name=variant_name,
        legs=priced_legs,
        total_price_pln=round(total_price_pln, 2),
        total_price_pln_high=total_price_pln_high,
        total_duration_min=total_duration_min,
        num_transfers=max(sum(1 for pl in priced_legs if pl.leg.mode is not LegMode.WALK) - 1, 0),
        transfer_warnings=check_all_transfers(legs_only),
    )


def pick_recommendations(itineraries: list[Itinerary]) -> dict[str, Itinerary]:
    """Wybiera rekomendacje z listy wariantów. Może się zdarzyć, że ten sam wariant wygra
    w kilku kategoriach naraz (np. jest jednocześnie najtańszy i najszybszy) — to nie błąd.

    "Bezpieczna" = wariant bez żadnej ryzykownej przesiadki (i.is_risky == False). Jeśli
    żaden taki wariant nie istnieje, bierzemy najmniej ryzykowny z dostępnych (patrz
    is_safe_recommendation_fallback na Itinerary, ustawiane niżej) — lepiej pokazać
    "najbezpieczniejszy z tego, co jest" niż nic, ale trzeba to wyraźnie oznaczyć w UI."""
    itineraries = [
        i for i in itineraries if not i.is_infeasible
    ]  # niewykonalnych nie rekomendujemy
    if not itineraries:
        raise ValueError("brak wariantów do wyboru rekomendacji")

    safe = [i for i in itineraries if not i.is_risky]
    safe_pool = safe if safe else itineraries
    for i in itineraries:
        i.is_safe_fallback = (
            not safe
        )  # True: nawet "bezpieczna" rekomendacja ma tu ryzykowną przesiadkę

    compromise_key = _compromise_key(itineraries)
    safe_compromise_key = _compromise_key(safe_pool)

    return {
        # najpierw warianty z potwierdzoną ceną (False < True), potem cena — patrz docstring
        "najtansza": min(itineraries, key=lambda i: (not i.price_verified, i.total_price_pln)),
        "najszybsza": min(itineraries, key=lambda i: i.total_duration_min),
        # liczą się wszystkie przesiadki; remis: krótszy czas, potem niższa cena. Wybór jest
        # spośród wariantów zwróconych przez MOTIS (nie szukamy tras, których MOTIS nie dał).
        "najmniej_przesiadek": min(
            itineraries, key=lambda i: (i.num_transfers, i.total_duration_min, i.total_price_pln)
        ),
        "najlepszy_stosunek_ceny_do_czasu": min(itineraries, key=lambda i: i.value_score),
        "najlepszy_kompromis": min(itineraries, key=compromise_key),
        "najszybsza_z_ulgami": _fastest_within_tolerance(itineraries),
        "najszybsza_bezpieczna": min(
            safe_pool, key=lambda i: (i.num_risky_transfers, i.total_duration_min)
        ),
        "najtansza_bezpieczna": min(
            safe_pool,
            key=lambda i: (i.num_risky_transfers, not i.price_verified, i.total_price_pln),
        ),
        "najlepszy_kompromis_bezpieczny": min(
            safe_pool, key=lambda i: (i.num_risky_transfers, safe_compromise_key(i))
        ),
        "najmniej_przesiadek_bezpieczna": min(
            safe_pool,
            key=lambda i: (
                i.num_risky_transfers,
                i.num_transfers,
                i.total_duration_min,
                i.total_price_pln,
            ),
        ),
        "najszybsza_z_ulgami_bezpieczna": _fastest_within_tolerance(
            safe_pool, key=lambda i: (i.num_risky_transfers, i.total_price_pln)
        ),
    }
