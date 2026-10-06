"""Serwis obsługujący katalog atrakcji, filtrowanie kategorii i kalkulator City Cards."""

import re
import unicodedata

from ._data_loading import load
from .model import (
    Attraction,
    AttractionCategory,
    CityCard,
    CityCardEvaluation,
    CityCardVariant,
)

_CITY_ALIASES = {
    "gelsenkirchen": "gelsenkirchen",
    "buer": "gelsenkirchen",
    "essen": "gelsenkirchen",
    "dortmund": "gelsenkirchen",
    "bochum": "gelsenkirchen",
    "duisburg": "gelsenkirchen",
    "oberhausen": "gelsenkirchen",
    "ruhr": "gelsenkirchen",
    "vrr": "gelsenkirchen",
    "berlin": "berlin",
    "krakow": "krakow",
    "kraków": "krakow",
    "lublin": "lublin",
    "warszawa": "warszawa",
    "warsaw": "warszawa",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))



def normalize_city(query: str | None) -> str | None:
    """Rozpoznaje identyfikator miasta z tekstu adresu lub nazwy miejscowości."""
    if not query:
        return None
    # Sprawdzamy najpierw segmenty po przecinku od końca (tam zwykle jest miasto, np. "Ulica 1, Lublin")
    segments = [s.strip() for s in query.split(",") if s.strip()]
    if not segments:
        segments = [query.strip()]

    # Szukamy od końca
    for seg in reversed(segments):
        cleaned = _strip_accents(seg.lower())
        for token, canonical in _CITY_ALIASES.items():
            token_clean = _strip_accents(token)
            # Wymagamy pełnego dopasowania słowa (\b), aby uniknąć np. "krakow" w "krakowskie"
            if re.search(rf"\b{re.escape(token_clean)}\b", cleaned):
                return canonical

    # Jeśli nie znaleziono w pojedynczych segmentach po przecinku, przeszukaj całość z \b
    whole_cleaned = _strip_accents(query.lower())
    for token, canonical in _CITY_ALIASES.items():
        token_clean = _strip_accents(token)
        if re.search(rf"\b{re.escape(token_clean)}\b", whole_cleaned):
            return canonical

    return None



def get_all_attractions() -> list[Attraction]:
    """Wczytuje wszystkie atrakcje z bazy danych JSON."""
    raw = load("attractions.json")["atrakcje"]
    res = []
    for item in raw:
        res.append(
            Attraction(
                id=item["id"],
                name=item["name"],
                city=item["city"],
                category=AttractionCategory(item["category"]),
                description=item["description"],
                normal_price=float(item["normal_price"]),
                currency=item["currency"],
                default_card_discount_percent=float(item.get("default_card_discount_percent", 0.0)),
                address=item.get("address", ""),
                official_url=item.get("official_url", ""),
                highlight=bool(item.get("highlight", False)),
                tags=list(item.get("tags", [])),
                price_verified=bool(item.get("price_verified", False)),
            )
        )
    return res


def get_attractions(
    city: str | None = None, category: AttractionCategory | str | None = None
) -> list[Attraction]:
    """Zwraca atrakcje, opcjonalnie przefiltrowane po mieście lub kategorii."""
    attractions = get_all_attractions()
    city_key = normalize_city(city) if city else None
    cat_enum = AttractionCategory(category) if isinstance(category, str) else category

    filtered = []
    for a in attractions:
        if city_key and a.city != city_key:
            continue
        if cat_enum and a.category != cat_enum:
            continue
        filtered.append(a)
    return filtered


def get_all_city_cards() -> list[CityCard]:
    """Wczytuje wszystkie karty miejskie z bazy danych JSON."""
    raw = load("city_cards.json")["karty"]
    res = []
    for item in raw:
        variants = [
            CityCardVariant(
                id=v["id"],
                name=v["name"],
                duration_hours=int(v["duration_hours"]),
                price=float(v["price"]),
                currency=v["currency"],
                includes_public_transit=bool(v["includes_public_transit"]),
                transit_zones=v["transit_zones"],
                description=v["description"],
                price_verified=bool(v.get("price_verified", False)),
            )
            for v in item["variants"]
        ]
        res.append(
            CityCard(
                id=item["id"],
                city=item["city"],
                name=item["name"],
                description=item["description"],
                official_url=item["official_url"],
                variants=variants,
                default_discount_percent=float(item.get("default_discount_percent", 25.0)),
                custom_discounts=dict(item.get("custom_discounts", {})),
            )
        )
    return res


def get_city_cards(city: str | None = None) -> list[CityCard]:
    """Zwraca karty miejskie dla wskazanego miasta."""
    cards = get_all_city_cards()
    city_key = normalize_city(city) if city else None
    if not city_key:
        return cards
    return [c for c in cards if c.city == city_key]


def _calculate_attraction_discount_percent(
    card: CityCard, variant: CityCardVariant, attraction: Attraction
) -> float:
    # Specjalne uprawnienia dla konkretnych wariantów (np. BWC Museumsinsel daje 100% zniżki na muzea)
    if (
        variant.id == "bwc_72h_museumsinsel"
        and attraction.id == "berlin_museumsinsel"
    ):
        return 100.0

    if attraction.id in card.custom_discounts:
        return card.custom_discounts[attraction.id]

    if attraction.default_card_discount_percent > 0:
        return attraction.default_card_discount_percent

    return card.default_discount_percent


def evaluate_city_card_variant(
    card: CityCard,
    variant: CityCardVariant,
    attractions: list[Attraction],
    estimated_transit_cost: float = 0.0,
) -> CityCardEvaluation:
    """Wylicza opłacalność pojedynczego wariantu karty miejskiej dla podanej listy atrakcji."""
    price_without = 0.0
    price_with = 0.0

    for a in attractions:
        price_without += a.normal_price
        disc_pct = _calculate_attraction_discount_percent(card, variant, a)
        discounted = a.normal_price * (1.0 - (disc_pct / 100.0))
        price_with += max(0.0, discounted)

    transit_savings = estimated_transit_cost if variant.includes_public_transit else 0.0
    total_without = price_without + estimated_transit_cost
    total_with = variant.price + price_with

    net_savings = round(total_without - total_with, 2)
    is_recommended = net_savings > 0.0

    if is_recommended:
        summary = (
            f"Kupno {variant.name} opłaca się! Zaoszczędzisz łącznie {net_savings:.2f} {variant.currency} "
            f"(wstępy: {price_without - price_with:.2f} {variant.currency} zniżki"
            + (
                ", transport: darmowy w cenie karty"
                if variant.includes_public_transit and transit_savings > 0
                else ""
            )
            + ")."
        )
    else:
        diff = abs(net_savings)
        summary = (
            f"{variant.name} kosztuje {variant.price:.2f} {variant.currency}. "
            f"Przy obecnym zestawie atrakcji zabraknie około {diff:.2f} {variant.currency} "
            f"do zwrotu kosztu karty."
        )

    return CityCardEvaluation(
        card_name=card.name,
        variant=variant,
        attractions_count=len(attractions),
        attractions_price_without_card=round(price_without, 2),
        attractions_price_with_card=round(price_with, 2),
        card_price=variant.price,
        estimated_transit_savings=round(transit_savings, 2),
        total_cost_without_card=round(total_without, 2),
        total_cost_with_card=round(total_with, 2),
        net_savings=net_savings,
        currency=variant.currency,
        is_recommended=is_recommended,
        summary=summary,
    )


def evaluate_city_cards(
    city: str,
    attractions: list[Attraction],
    estimated_transit_cost: float = 0.0,
) -> list[CityCardEvaluation]:
    """Wylicza opłacalność wszystkich kart i ich wariantów dostępnych w danym mieście."""
    cards = get_city_cards(city)
    evaluations: list[CityCardEvaluation] = []
    for card in cards:
        for variant in card.variants:
            evaluations.append(
                evaluate_city_card_variant(
                    card, variant, attractions, estimated_transit_cost
                )
            )
    return evaluations


def suggest_best_city_card(
    city: str,
    attractions: list[Attraction],
    estimated_transit_cost: float = 0.0,
) -> CityCardEvaluation | None:
    """Zwraca najbardziej opłacalny wariant karty miejskiej dla podanych atrakcji (jeśli istnieje)."""
    evaluations = evaluate_city_cards(city, attractions, estimated_transit_cost)
    profitable = [e for e in evaluations if e.is_recommended]
    if not profitable:
        return None
    # Sortuj malejąco po oszczędnościach netto
    profitable.sort(key=lambda e: e.net_savings, reverse=True)
    return profitable[0]
