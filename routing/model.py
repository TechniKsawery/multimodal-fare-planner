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
    def price_known(self) -> bool:
        """False, gdy kwoty nie znamy (breakdown["cena_nieznana"]): amount=0.0 to wtedy BRAK
        ceny, nie cena zero — odcinek nie jest wliczony w sumę wariantu."""
        return not self.breakdown.get("cena_nieznana")

    @property
    def price_verified(self) -> bool:
        """Czy cena jest potwierdzona. Jawna flaga breakdown["price_verified"] zawsze wygrywa
        (True = np. pasmo POLREGIO z oficjalnej tabeli, które mimo linii prostej zostaje
        "szacunkiem"; False = fallback bez cennika). Gdy flagi brak, rozstrzyga price_type:
        "szacunek" bez jawnego potwierdzenia NIE jest potwierdzony (np. migawka z API FlixBusa,
        tabela pasm DB, cena lotu z Travelpayouts) — wcześniej brak klucza oznaczał
        "potwierdzone" i takie odcinki dostawały verified=True."""
        if not self.price_known:
            return False
        flag = self.breakdown.get("price_verified")
        if isinstance(flag, bool):
            return flag
        return self.price_type != "szacunek"

    @property
    def unverified_label(self) -> str:
        """Dopisek przy cenie odcinka w UI i demo.py; pusty dla ceny z taryfy/oferty."""
        if self.price_verified:
            return ""
        if self.breakdown.get("cena_nieznana"):
            return "cena nieznana (odcinek nie wliczony w sumę)"
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
    def price_status(self) -> str:
        """"pelna" (każdy odcinek ma kwotę), "czesciowa" (część odcinków bez ceny — total_price_pln
        to tylko suma znanych, dolne ograniczenie) albo "brak" (żaden odcinek poza pieszymi nie ma
        ceny; total_price_pln=0 to wtedy brak informacji, nie 0 zł). Nie zgadujemy kwot."""
        if all(pl.price_known for pl in self.legs):
            return "pelna"
        has_known = any(pl.price_known and pl.leg.mode is not LegMode.WALK for pl in self.legs)
        return "czesciowa" if has_known else "brak"

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


def _days_phrase(days_offset: int) -> str:
    """"za 2 dni" / "1 dzień wcześniej" — odległość wariantu od dnia zapytania."""
    n = abs(days_offset)
    unit = "dzień" if n == 1 else "dni"
    return f"za {n} {unit}" if days_offset > 0 else f"{n} {unit} wcześniej"


OTHER_DAY_SECTION_TITLE = "Najbliższe połączenia w innym dniu"


@dataclass
class OtherDayVariant:
    """Połączenie z INNEGO dnia niż zapytany — pokazywane tylko jako podpowiedź, gdy w dniu
    zapytania nic nie jedzie (patrz routing/variants.py::build_rail_only_variants). To NIE jest
    wariant głównego wyniku: nie wchodzi do `built` ani do rankingów "Najtańsza"/"Najszybsza"."""

    itinerary: Itinerary
    date: str  # "YYYY-MM-DD", dzień odjazdu tego połączenia (czas lokalny)
    requested_date: str  # "YYYY-MM-DD", dzień, o który pytał użytkownik
    days_offset: int  # date - requested_date w dniach (ujemne = wcześniej)
    label: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.label = (
            f"INNY DZIEŃ: {self.date} ({_days_phrase(self.days_offset)}, zapytano o "
            f"{self.requested_date}) — to NIE jest dzień zapytania"
        )
