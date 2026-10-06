"""Wspólny model danych dla modułu cen lotów: segment lotu i wynik szacowania ceny."""

from dataclasses import dataclass
from enum import Enum


class PriceType(str, Enum):
    """Czy cena pochodzi z realnych danych (cache Travelpayouts), czy jest naszym szacunkiem."""

    ESTIMATE = "szacunek"
    OFFICIAL = "oficjalna_taryfa"


@dataclass
class ExtrasProfile:
    """Koszty poza samym biletem — osobne pola, bo różnią się między liniami i miastami."""

    baggage_cost: float = 0.0
    airport_access_cost: float = 0.0
    destination_transfer_cost: float = 0.0
    currency: str = "PLN"
    note: str = ""

    @property
    def total(self) -> float:
        return self.baggage_cost + self.airport_access_cost + self.destination_transfer_cost


@dataclass
class FlightSegment:
    """Jeden odcinek lotu do wycenienia."""

    origin: str  # kod IATA miasta/lotniska wylotu, np. "WAW"
    destination: str  # kod IATA miasta/lotniska przylotu, np. "DUS"
    depart_date: str  # "YYYY-MM-DD" lub "YYYY-MM"
    return_date: str | None = None
    currency: str = "PLN"
    extras: ExtrasProfile | None = None  # None -> dociągnięte z placeholderowej tabeli


@dataclass
class PriceEstimate:
    """Wynik wyceny segmentu lotu: cena biletu + koszty dodatkowe."""

    origin: str
    destination: str
    amount: float
    currency: str
    price_type: PriceType
    breakdown: dict
    notes: str = ""

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency} ({self.price_type.value}) — {self.origin}->{self.destination}"
