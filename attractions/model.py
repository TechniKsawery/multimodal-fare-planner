"""Modele danych dla modułu atrakcji, miejsc i kart miejskich (City Cards)."""

from dataclasses import dataclass, field
from enum import Enum


class AttractionCategory(str, Enum):
    SPORT = "sport"  # stadiony, areny sportowe, muzea klubowe
    CULTURE = "turystyka_kultura"  # zabytki, muzea, galerie, pałace
    ENTERTAINMENT = "rozrywka"  # punkty widokowe, zoo, parki rozrywki, teatry
    GASTRONOMY = "gastronomia"  # kultowe targowiska, słynne punkty gastronomiczne
    NATURE = "natura"  # parki, ogrody botaniczne, tereny rekreacyjne


CATEGORY_LABELS = {
    AttractionCategory.SPORT: "⚽ Sport i stadiony",
    AttractionCategory.CULTURE: "🏛️ Turystyka i zabytki",
    AttractionCategory.ENTERTAINMENT: "🎡 Rozrywka i punkty widokowe",
    AttractionCategory.GASTRONOMY: "🍕 Gastronomia i kultowe smaki",
    AttractionCategory.NATURE: "🌳 Natura i parki",
}


@dataclass
class GroupPrice:
    """Konkretna, potwierdzona (lub nie) cena dla jednego tytułu do zniżki.

    Nigdy procent — zawsze kwota wprost z cennika operatora, bo zniżki
    różnią się mocno per atrakcja i nie da się ich zgadnąć uniwersalnym %.
    """

    price: float
    label: str
    min_age: int | None = None
    max_age: int | None = None
    # Opis dodatkowego wymogu poza wiekiem, np. "ważna legitymacja ucznia/studenta"
    requires_status: str = ""
    source_url: str = ""
    verified_date: str = ""
    # False = cena nie została potwierdzona w oficjalnym źródle
    price_verified: bool = False


@dataclass
class Attraction:
    """Pojedyncza atrakcja / miejsce warte odwiedzenia."""

    id: str
    name: str
    city: str
    category: AttractionCategory
    description: str
    normal_price: float
    currency: str
    default_card_discount_percent: float = 0.0
    address: str = ""
    official_url: str = ""
    highlight: bool = False
    tags: list[str] = field(default_factory=list)
    # False = cena nie została potwierdzona w oficjalnym źródle (oznaczana w UI jako niepotwierdzona)
    price_verified: bool = False
    # Zniżki z tytułu wieku/statusu, niezależne od posiadania jakiejkolwiek karty miejskiej.
    # None = nie znaleziono/nie dotyczy tej atrakcji (nigdy zgadywane).
    child_price: "GroupPrice | None" = None
    student_price: "GroupPrice | None" = None
    senior_price: "GroupPrice | None" = None
    family_price: "GroupPrice | None" = None


@dataclass
class CityCardVariant:
    """Wariant czasowy lub strefowy karty miejskiej."""

    id: str
    name: str
    duration_hours: int
    price: float
    currency: str
    includes_public_transit: bool
    transit_zones: str
    description: str
    # False = cena nie została potwierdzona w oficjalnym cenniku na dziś
    price_verified: bool = False


@dataclass
class CityCard:
    """Karta miejska łącząca transport i/lub zniżki na atrakcje."""

    id: str
    city: str
    name: str
    description: str
    official_url: str
    variants: list[CityCardVariant]
    default_discount_percent: float = 25.0
    custom_discounts: dict[str, float] = field(default_factory=dict)
    # Czy POTWIERDZONO (u źródła, z datą), że karta w ogóle istnieje i działa DZIŚ —
    # niezależnie od tego, czy jej cena jest potwierdzona (price_verified na wariancie).
    # False domyślnie: karta nie pojawia się w get_city_cards()/kalkulatorze/rekomendacji,
    # dopóki ktoś nie potwierdzi jej istnienia na żywo (np. martwe produkty jak dawna
    # WelcomeCard Ruhr nie mają prawa trafić do użytkownika jako opcja).
    existence_verified: bool = False
    existence_source_url: str = ""
    existence_verified_date: str = ""


@dataclass
class CityCardEvaluation:
    """Wynik kalkulacji opłacalności zakupu wariantu karty miejskiej."""

    card_name: str
    variant: CityCardVariant
    attractions_count: int
    attractions_price_without_card: float
    attractions_price_with_card: float
    card_price: float
    estimated_transit_savings: float
    total_cost_without_card: float
    total_cost_with_card: float
    net_savings: float
    currency: str
    is_recommended: bool
    summary: str
