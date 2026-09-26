"""Sprawdzanie bezpieczeństwa przesiadek między kolejnymi odcinkami wariantu.

Progi minimalne są SZACUNKIEM (nie oficjalnymi zaleceniami przewoźników) — patrz README.md.
"""
from typing import List, Optional

from .model import Leg, LegMode, TransferWarning

MIN_TRANSFER_MINUTES_SAME_PLATFORM = 20   # kolej->kolej, bez zmiany peronu/dworca (brak legu WALK w MOTIS)
MIN_TRANSFER_MINUTES_WALK = 30            # kolej->kolej, ze zmianą peronu/dworca (jest leg WALK w MOTIS)
MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT = 120  # dojście do terminala, odprawa, kontrola bezpieczeństwa
MIN_TRANSFER_MINUTES_FLIGHT_TO_RAIL = 90   # wyjście z samolotu, odbiór bagażu, dojście/dojazd do stacji


def minimum_transfer_minutes(prev_mode: LegMode, next_mode: LegMode, requires_walk: bool) -> float:
    if prev_mode is LegMode.RAIL and next_mode is LegMode.FLIGHT:
        return MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT
    if prev_mode is LegMode.FLIGHT and next_mode is LegMode.RAIL:
        return MIN_TRANSFER_MINUTES_FLIGHT_TO_RAIL
    if prev_mode is LegMode.FLIGHT and next_mode is LegMode.FLIGHT:
        return MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT
    return MIN_TRANSFER_MINUTES_WALK if requires_walk else MIN_TRANSFER_MINUTES_SAME_PLATFORM


def check_transfer(prev_leg: Leg, next_leg: Leg, after_leg_index: int) -> Optional[TransferWarning]:
    gap_minutes = (next_leg.depart - prev_leg.arrive).total_seconds() / 60
    minimum = minimum_transfer_minutes(prev_leg.mode, next_leg.mode, next_leg.requires_walk)

    if gap_minutes < minimum:
        powod_zmiany = "wymaga przejścia/zmiany dworca" if next_leg.requires_walk else "na tym samym przystanku/peronie"
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
        )
    return None


def check_all_transfers(legs: List[Leg]) -> List[TransferWarning]:
    warnings: List[TransferWarning] = []
    # odcinki piesze (dojście z adresu / do adresu) nie są przesiadkami — pomijamy je,
    # ale zachowujemy oryginalne indeksy legów w after_leg_index
    indexed = [(i, leg) for i, leg in enumerate(legs) if leg.mode is not LegMode.WALK]
    for (i, prev), (_, nxt) in zip(indexed, indexed[1:]):
        warning = check_transfer(prev, nxt, after_leg_index=i)
        if warning is not None:
            warnings.append(warning)
    return warnings
