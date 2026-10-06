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
