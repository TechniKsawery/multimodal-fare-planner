"""Sprawdzanie bezpieczeństwa przesiadek między kolejnymi odcinkami wariantu.

Progi minimalne są SZACUNKIEM (nie oficjalnymi zaleceniami przewoźników) — patrz README.md.
"""

from .model import Leg, LegMode, TransferWarning

MIN_TRANSFER_MINUTES_SAME_PLATFORM = (
    20  # kolej->kolej, bez zmiany peronu/dworca (brak legu WALK w MOTIS)
)
MIN_TRANSFER_MINUTES_WALK = 30  # kolej->kolej, ze zmianą peronu/dworca (jest leg WALK w MOTIS)
MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT = 120  # dojście do terminala, odprawa, kontrola bezpieczeństwa
MIN_TRANSFER_MINUTES_FLIGHT_TO_RAIL = (
    60  # wyjście z samolotu, odbiór bagażu, dojście/dojazd do stacji
)
# Bufory, które variants.py wstawia wokół lotu, to dokładnie te progi (jedno miejsce wartości):
# przed odlotem = MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT, po przylocie = MIN_TRANSFER_MINUTES_FLIGHT_TO_RAIL.


# ABSOLUTNE minima wykonalności — poniżej nich człowiek fizycznie nie zdąży (wariant jest
# odrzucany, a nie tylko oflagowany). Powyżej tego, ale poniżej progów "bezpiecznych" wyżej,
# przesiadka jest tylko RYZYKOWNA.
FEASIBLE_MIN_MINUTES_SAME_PLATFORM = 3
FEASIBLE_MIN_MINUTES_WALK = 8
FEASIBLE_MIN_MINUTES_RAIL_TO_FLIGHT = 60
FEASIBLE_MIN_MINUTES_FLIGHT_TO_RAIL = 45


# Znane kompleksy przystankowe, które GTFS/MOTIS nazywa RÓŻNYMI nazwami (osobne wejścia/części
# dworca dostały osobne rekordy stop), ale które fizycznie są tym samym budynkiem/węzłem, więc
# przejście między nimi trwa minuty, nie 30 min jak przy prawdziwej zmianie dworca w mieście.
# Zweryfikowane ręcznie (Moovit/opisy dworców) — patrz PR #9. Dopisuj tu kolejne potwierdzone
# przypadki, gdy user zgłosi kolejną fałszywie odrzuconą przesiadkę.
KNOWN_STATION_COMPLEX_ALIASES: list[frozenset] = [
    # Dworzec metropolitalny w Lublinie (ul. Kunickiego) — GTFS/MOTIS zna go pod kilkoma
    # nazwami wg przystanku/peronu (MPK Lublin: "Dworzec Lublin - Kunickiego", "Dworzec Lublin
    # 51/52"); "Lublin Główny" to sąsiadujący dworzec kolejowy połączony z nim przejściem
    # podziemnym (ul. Pocztowa) — jeden kompleks przesiadkowy.
    frozenset({"Dworzec Lublin - Kunickiego", "Dworzec Lublin", "Lublin Główny"}),
    # Zintegrowany węzeł Berlin-Lichtenberg: dworzec dalekobieżny/regionalny i S+U Lichtenberg
    # (S-Bahn/U-Bahn) to jeden kompleks, połączony przejściem podziemnym nad torami U-Bahn
    # (Wikipedia: "Berlin-Lichtenberg station").
    frozenset({"Berlin-Lichtenberg", "S+U Lichtenberg Bhf (Berlin)"}),
]


def _same_stop(prev_leg: Leg, next_leg: Leg) -> bool:
    """True, gdy MOTIS oznaczył przesiadkę jako "wymagającą przejścia" (requires_walk, bo
    zapytanie zwróciło leg WALK między odcinkami transitu), ale to w rzeczywistości ten sam
    kompleks przystankowy (inny peron/wejście tej samej stacji), a nie zmiana dworca. Trafia
    tu zarówno identyczna nazwa po obu stronach (MOTIS/GTFS czasem generuje "spacerowy" leg
    nawet w obrębie jednego przystanku, bo perony mają osobne id mimo wspólnej nazwy), jak i
    znana z KNOWN_STATION_COMPLEX_ALIASES para różnych nazw tego samego fizycznego budynku."""
    origin, destination = prev_leg.destination_name, next_leg.origin_name
    if not origin or not destination:
        return False
    if origin == destination:
        return True
    pair = frozenset({origin, destination})
    return any(pair <= alias for alias in KNOWN_STATION_COMPLEX_ALIASES)


def feasible_minimum_minutes(
    prev_mode: LegMode, next_mode: LegMode, requires_walk: bool, same_stop: bool = False
) -> float:
    if prev_mode is LegMode.FLIGHT and next_mode is LegMode.FLIGHT:
        return FEASIBLE_MIN_MINUTES_RAIL_TO_FLIGHT
    if next_mode is LegMode.FLIGHT:
        return FEASIBLE_MIN_MINUTES_RAIL_TO_FLIGHT
    if prev_mode is LegMode.FLIGHT:
        return FEASIBLE_MIN_MINUTES_FLIGHT_TO_RAIL
    if requires_walk and same_stop:
        return FEASIBLE_MIN_MINUTES_SAME_PLATFORM
    return FEASIBLE_MIN_MINUTES_WALK if requires_walk else FEASIBLE_MIN_MINUTES_SAME_PLATFORM


def minimum_transfer_minutes(
    prev_mode: LegMode, next_mode: LegMode, requires_walk: bool, same_stop: bool = False
) -> float:
    if prev_mode is LegMode.RAIL and next_mode is LegMode.FLIGHT:
        return MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT
    if prev_mode is LegMode.FLIGHT and next_mode is LegMode.RAIL:
        return MIN_TRANSFER_MINUTES_FLIGHT_TO_RAIL
    if prev_mode is LegMode.FLIGHT and next_mode is LegMode.FLIGHT:
        return MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT
    if requires_walk and same_stop:
        return MIN_TRANSFER_MINUTES_SAME_PLATFORM
    return MIN_TRANSFER_MINUTES_WALK if requires_walk else MIN_TRANSFER_MINUTES_SAME_PLATFORM


def check_transfer(prev_leg: Leg, next_leg: Leg, after_leg_index: int) -> TransferWarning | None:
    gap_minutes = (next_leg.depart - prev_leg.arrive).total_seconds() / 60
    same_stop = next_leg.requires_walk and _same_stop(prev_leg, next_leg)
    minimum = minimum_transfer_minutes(
        prev_leg.mode, next_leg.mode, next_leg.requires_walk, same_stop
    )

    if gap_minutes < minimum:
        infeasible = gap_minutes < feasible_minimum_minutes(
            prev_leg.mode, next_leg.mode, next_leg.requires_walk, same_stop
        )
        if same_stop:
            powod_zmiany = "ten sam przystanek, inny peron/wejście wg MOTIS"
        elif next_leg.requires_walk:
            powod_zmiany = "wymaga przejścia/zmiany dworca"
        else:
            powod_zmiany = "na tym samym przystanku/peronie"
        reason = (
            f"Tylko {gap_minutes:.0f} min na przesiadkę {prev_leg.mode.value} -> {next_leg.mode.value} "
            f"({powod_zmiany}, {prev_leg.destination_name} -> {next_leg.origin_name}), "
            f"potrzeba minimum {minimum:.0f} min."
        )
        return TransferWarning(
            after_leg_index=after_leg_index,
            gap_minutes=gap_minutes,
            minimum_required_minutes=minimum,
            reason=reason,
            infeasible=infeasible,
        )
    return None


def check_all_transfers(legs: list[Leg]) -> list[TransferWarning]:
    warnings: list[TransferWarning] = []
    # odcinki piesze (dojście z adresu / do adresu) nie są przesiadkami — pomijamy je,
    # ale zachowujemy oryginalne indeksy legów w after_leg_index
    indexed = [(i, leg) for i, leg in enumerate(legs) if leg.mode is not LegMode.WALK]
    for (i, prev), (_, nxt) in zip(indexed, indexed[1:]):
        warning = check_transfer(prev, nxt, after_leg_index=i)
        if warning is not None:
            warnings.append(warning)
    return warnings
