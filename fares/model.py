"""Wspólny model danych dla modułu taryf: segment podróży i wynik szacowania ceny."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PriceType(str, Enum):
    """Czy cena jest oficjalną taryfą przewoźnika, czy naszym szacunkiem (np. z placeholderów)."""

    ESTIMATE = "szacunek"
    OFFICIAL = "oficjalna_taryfa"


class Carrier(str, Enum):
    PKP_INTERCITY = "pkp_intercity"
    DB = "db"
    VRR = "vrr"
    FLIXBUS = "flixbus"
    ZTM_LUBLIN = "ztm_lublin"
    INTERNATIONAL_PL_DE = "international_pl_de"  # bilet PL<->DE przekraczający granicę jednym
    # ciągłym odcinkiem kolejowym (np. Berlin-Warszawa-Express) — SZTYWNE kategorie cenowe
    # (Super Sparpreis Europa), nie tabela pasm jak krajowe kalkulatory PKP/DB. Zob. fares/international.py.


@dataclass
class DiscountProfile:
    """Profil ulg pasażera, wspólny dla wszystkich przewoźników w segmencie."""

    pkp_ulga_kod: str = "brak"          # klucz z fares/data/pkp_intercity.json -> ulgi_procent
    bahncard: Optional[str] = None      # None, "25", "50" lub "100" (DB, oficjalne rabaty Flexpreis)
    ztm_lublin_ulgowy: bool = False     # ZTM Lublin: bilet ulgowy zamiast normalnego
    vrr_dziecko: bool = False           # VRR/eezy.nrw: Kindertarif (6-14 lat), 50% rabatu wliczając sufity cenowe


@dataclass
class Segment:
    """Jeden odcinek podróży u jednego przewoźnika."""

    carrier: Carrier
    origin: str
    destination: str
    distance_km: Optional[float] = None   # wymagane dla PKP, DB i VRR (VRR: odległość w linii prostej)
    ride_duration_min: Optional[float] = None  # wymagane dla ZTM Lublin (taryfa czasowa)
    discounts: DiscountProfile = field(default_factory=DiscountProfile)
    travel_date: Optional[str] = None     # "YYYY-MM-DD"; wymagane dla FlixBus (ceny dynamiczne per data)
    german_portion_fraction: Optional[float] = None
    """Tylko Carrier.INTERNATIONAL_PL_DE: szacowany udział (0-1) niemieckiego odcinka trasy w
    całym dystansie (linia prosta), używany do proporcjonalnego naliczenia rabatu BahnCard,
    który oficjalnie dotyczy TYLKO niemieckiej części trasy (patrz fares/international.py).
    None = brak danych geograficznych do oszacowania -> rabat naliczany od całej ceny
    (zawyża realny rabat, ale to jedyny dostępny fallback bez współrzędnych stacji)."""


@dataclass
class PriceEstimate:
    """Wynik wyceny segmentu."""

    carrier: Carrier
    amount: float
    currency: str
    price_type: PriceType
    breakdown: dict
    notes: str = ""

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency} ({self.price_type.value}) — {self.carrier.value}"
