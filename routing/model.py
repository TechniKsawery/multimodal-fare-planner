"""Wspólny model danych dla silnika optymalizacji trasy: odcinki, wyceny i warianty."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class LegMode(str, Enum):
    RAIL = "kolej"
    FLIGHT = "lot"
    BUS = "autobus"
    WALK = "pieszo"


@dataclass
class Leg:
    """Jeden odcinek podróży (przed wyceną)."""

    mode: LegMode
    origin_name: str
    destination_name: str
    depart: datetime
    arrive: datetime
    carrier_name: str = ""             # np. "PKP Intercity", "DB Fernverkehr AG", "Ryanair"
    distance_km: Optional[float] = None
    requires_walk: bool = True         # czy przesiadka na początku tego legu wymaga przejścia (zmiana peronu/dworca/terminala)
    extra: dict = field(default_factory=dict)  # np. iata kody dla lotów, id przystanków MOTIS

    @property
    def duration_min(self) -> float:
        return (self.arrive - self.depart).total_seconds() / 60


@dataclass
class PricedLeg:
    """Odcinek podróży razem z wyceną."""

    leg: Leg
    amount: float
    currency: str
    price_type: str          # "szacunek" albo "oficjalna_taryfa" (PriceType.value z fares/flights)
    notes: str = ""


@dataclass
class TransferWarning:
    """Ostrzeżenie o zbyt krótkiej/ryzykownej przesiadce między dwoma odcinkami."""

    after_leg_index: int      # indeks legu PRZED przesiadką (przesiadka jest między legs[i] i legs[i+1])
    gap_minutes: float
    minimum_required_minutes: float
    reason: str
    infeasible: bool = False   # True: poniżej absolutnego minimum wykonalności (nikt tego nie zdąży)


@dataclass
class Itinerary:
    """Jeden wariant trasy: sekwencja wycenionych odcinków + zagregowane metryki."""

    variant_name: str
    legs: List[PricedLeg]
    total_price_pln: float             # suma cen wszystkich odcinków, przeliczona do PLN (patrz routing/currency.py)
    total_duration_min: float          # od odjazdu pierwszego legu do przyjazdu ostatniego (wliczając czekanie)
    num_transfers: int
    transfer_warnings: List[TransferWarning] = field(default_factory=list)

    @property
    def is_infeasible(self) -> bool:
        return any(w.infeasible for w in self.transfer_warnings)

    @property
    def is_risky(self) -> bool:
        """Ciasne, ale teoretycznie wykonalne przesiadki (niewykonalne warianty są odrzucane)."""
        return any(not w.infeasible for w in self.transfer_warnings)

    @property
    def price_per_hour(self) -> float:
        hours = self.total_duration_min / 60
        return self.total_price_pln / hours if hours > 0 else float("inf")


@dataclass
class SkippedVariant:
    """Wariant, którego nie udało się zbudować/wycenić (np. brak tokena API, brak połączenia w MOTIS)."""

    variant_name: str
    reason: str
