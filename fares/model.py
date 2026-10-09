"""Wspólny model danych dla modułu taryf: segment podróży i wynik szacowania ceny."""

from dataclasses import dataclass, field
from enum import Enum


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
    ZTM_WARSZAWA = "ztm_warszawa"
    MPK_KRAKOW = "mpk_krakow"
    ZTM_POZNAN = "ztm_poznan"
    MPK_WROCLAW = "mpk_wroclaw"
    BVG_BERLIN = "bvg_berlin"
    INTERNATIONAL_PL_DE = "international_pl_de"  # bilet PL<->DE przekraczający granicę jednym
    # ciągłym odcinkiem kolejowym (np. Berlin-Warszawa-Express) — SZTYWNE kategorie cenowe
    # (Super Sparpreis Europa), nie tabela pasm jak krajowe kalkulatory PKP/DB. Zob. fares/international.py.


@dataclass
class DiscountProfile:
    """Profil ulg pasażera, wspólny dla wszystkich przewoźników w segmencie."""

    pkp_ulga_kod: str = "brak"  # klucz z fares/data/pkp_intercity.json -> ulgi_procent
    bahncard: str | None = None  # None, "25", "50" lub "100" (DB, oficjalne rabaty Flexpreis)
    ztm_lublin_ulgowy: bool = False  # ZTM Lublin: bilet ulgowy zamiast normalnego
    ztm_warszawa_ulgowy: bool = False  # ZTM/WTP Warszawa: bilet ulgowy (50%)
    mpk_krakow_ulgowy: bool = False  # MPK Kraków (ZTP): bilet ulgowy (50%)
    ztm_poznan_ulgowy: bool = False  # ZTM Poznań: bilet ulgowy (50%)
    mpk_wroclaw_ulgowy: bool = False  # MPK Wrocław: bilet ulgowy (50%)
    bvg_berlin_ulgowy: bool = False  # BVG/VBB Berlin: taryfa ulgowa (Ermäßigungstarif)
    vrr_dziecko: bool = (
        False  # VRR/eezy.nrw: Kindertarif (6-14 lat), 50% rabatu wliczając sufity cenowe
    )
    age: int | None = None
    """Wiek pasażera w dniu podróży. Używany przez fares/international.py (bilet DB PL-DE) do
    wyboru taryfy wiekowej: dziecko/niemowlę (bis 5 lat gratis, 6-14 lat zależnie od
    `child_with_guardian`), "Super Sparpreis Europa Young" (15-26 lat) albo taryfa normalna —
    i przez fares/international_pkp.py (własna oferta PKP) do ulgi dziecięcej (6-14 -50%,
    <6 gratis) — nie wpływa na żaden INNY moduł taryf (PKP/DB/VRR/ZTM krajowe mają własne,
    osobne pola ulg wyżej, bo te zniżki zależą od STATUSU, nie samego wieku). Przed tym polem
    `age` z CLI/API trafiał tylko do routing/card_suggestions.py (sugestia zakupu BahnCard),
    nigdy do ceny biletu — zob. audyt zniżek w projekcie (2026-10-07)."""
    child_with_guardian: bool = False
    """Tylko bilet międzynarodowy PL-DE, dziecko 6-14 lat (`age`): czy dziecko podróżuje w
    towarzystwie osoby od 15 lat zgłoszonej przy tej samej rezerwacji — bahn.de: takie dziecko
    jedzie bezpłatnie na ofercie DB (zob. fares/data/international_pl_de.json::_zrodlo_dziecko).
    Domyślnie False (dziecko liczone jako podróżujące SAMODZIELNIE -> tylko 50% zniżki na
    niemiecki odcinek, NIE za darmo) — bezpieczniejszy domyślny wybór: nie zakładamy opiekuna,
    którego nie potwierdzono, żeby nie zaniżyć ceny biletu. PKP (fares/international_pkp.py) nie
    rozróżnia opiekuna — jego ulga dziecięca 50%/100% obowiązuje niezależnie od tego pola."""


@dataclass
class Segment:
    """Jeden odcinek podróży u jednego przewoźnika."""

    carrier: Carrier
    origin: str
    destination: str
    distance_km: float | None = None  # wymagane dla PKP, DB i VRR (VRR: odległość w linii prostej)
    ride_duration_min: float | None = None  # wymagane dla ZTM Lublin (taryfa czasowa)
    discounts: DiscountProfile = field(default_factory=DiscountProfile)
    travel_date: str | None = None  # "YYYY-MM-DD"; wymagane dla FlixBus (ceny dynamiczne per data)
    german_portion_fraction: float | None = None
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
