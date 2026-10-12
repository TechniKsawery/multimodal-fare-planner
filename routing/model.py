"""Wspólny model danych dla silnika optymalizacji trasy: odcinki, wyceny i warianty."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from fares.model import Carrier


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
    carrier_name: str = ""  # np. "PKP Intercity", "DB Fernverkehr AG", "Ryanair"
    distance_km: float | None = None
    requires_walk: bool = (
        True  # czy przesiadka na początku tego legu wymaga przejścia (zmiana peronu/dworca/terminala)
    )
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
    price_type: str  # "szacunek" albo "oficjalna_taryfa" (PriceType.value z fares/flights)
    notes: str = ""
    breakdown: dict = field(
        default_factory=dict
    )  # przekazane 1:1 z PriceEstimate.breakdown (fares/flights)
    carrier: Carrier | None = None  # przewoźnik taryfy (gdy wycenił go moduł fares/)

    @property
    def price_verified(self) -> bool:
        """False, gdy wycena to fallback bez cennika (breakdown["price_verified"] is False,
        patrz routing/pricing.py) — UI i demo.py dopisują wtedy "cena niepotwierdzona"."""
        return self.breakdown.get("price_verified") is not False

    @property
    def unverified_label(self) -> str:
        """Dopisek przy cenie odcinka w UI i demo.py; pusty dla ceny z taryfy/oferty."""
        if self.price_verified:
            return ""
        if self.breakdown.get("wartosc_zastepcza"):
            return "cena niepotwierdzona (wartość zastępcza, nie z cennika)"
        return "cena niepotwierdzona"


@dataclass
class TransferWarning:
    """Ostrzeżenie o zbyt krótkiej/ryzykownej przesiadce między dwoma odcinkami."""

    after_leg_index: (
        int  # indeks legu PRZED przesiadką (przesiadka jest między legs[i] i legs[i+1])
    )
    gap_minutes: float
    minimum_required_minutes: float
    reason: str
    infeasible: bool = False  # True: poniżej absolutnego minimum wykonalności (nikt tego nie zdąży)


@dataclass
class Itinerary:
    """Jeden wariant trasy: sekwencja wycenionych odcinków + zagregowane metryki."""

    variant_name: str
    legs: list[PricedLeg]
    total_price_pln: (
        float  # suma cen wszystkich odcinków, przeliczona do PLN (patrz routing/currency.py)
    )
    total_duration_min: (
        float  # od odjazdu pierwszego legu do przyjazdu ostatniego (wliczając czekanie)
    )
    num_transfers: int
    transfer_warnings: list[TransferWarning] = field(default_factory=list)
    total_price_pln_high: float | None = None  # górna granica ceny łącznej (PLN), gdy któryś
    # odcinek ma przedział breakdown["zakres_cen"] (PKP SPI); None = cena jednoznaczna
    is_safe_fallback: bool = False  # ustawiane przez pick_recommendations: True = nawet ta
    # "bezpieczna" rekomendacja ma ryzykowną przesiadkę, bo żaden wariant nie był w pełni bezpieczny

    @property
    def price_verified(self) -> bool:
        """True, gdy żaden odcinek nie ma ceny niepotwierdzonej (PricedLeg.price_verified).
        Wariant z choć jednym takim odcinkiem nie wygrywa rankingu "Najtańsza" z wariantem o
        potwierdzonej cenie — patrz routing/scoring.py::pick_recommendations."""
        return all(pl.price_verified for pl in self.legs)

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

    @property
    def num_carriers(self) -> int:
        """Liczba różnych przewoźników w wariancie (każdy = osobny bilet), bez odcinków pieszych."""
        return len(
            {
                pl.leg.carrier_name or pl.leg.mode.value
                for pl in self.legs
                if pl.leg.mode.value != "pieszo"
            }
        )

    @property
    def num_risky_transfers(self) -> int:
        return sum(1 for w in self.transfer_warnings if not w.infeasible)

    @property
    def value_score(self) -> float:
        """Uogólniony koszt do "najlepszy stosunek cena/czas" (PLN, niżej = lepiej):
        cena + wartość czasu (VALUE_OF_TIME_PLN_PER_HOUR x godziny) + kary za ryzykowne
        przesiadki i dodatkowych przewoźników/bilety — patrz routing/scoring_config.py."""
        from .scoring_config import (
            EXTRA_CARRIER_PENALTY_MIN,
            EXTRA_CARRIER_PENALTY_PLN,
            RISKY_TRANSFER_PENALTY_MIN,
            RISKY_TRANSFER_PENALTY_PLN,
            VALUE_OF_TIME_PLN_PER_HOUR,
        )

        extra_carriers = max(self.num_carriers - 1, 0)
        price = (
            self.total_price_pln
            + self.num_risky_transfers * RISKY_TRANSFER_PENALTY_PLN
            + extra_carriers * EXTRA_CARRIER_PENALTY_PLN
        )
        minutes = (
            self.total_duration_min
            + self.num_risky_transfers * RISKY_TRANSFER_PENALTY_MIN
            + extra_carriers * EXTRA_CARRIER_PENALTY_MIN
        )
        return price + minutes / 60 * VALUE_OF_TIME_PLN_PER_HOUR


@dataclass
class SkippedVariant:
    """Wariant, którego nie udało się zbudować/wycenić (np. brak tokena API, brak połączenia w MOTIS)."""

    variant_name: str
    reason: str
