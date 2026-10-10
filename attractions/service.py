"""Serwis obsługujący katalog atrakcji, filtrowanie kategorii i kalkulator City Cards."""

import re
import unicodedata

from dataclasses import dataclass

from ._data_loading import load
from .model import (
    Attraction,
    AttractionCategory,
    CityCard,
    CityCardEvaluation,
    CityCardVariant,
    GroupPrice,
)


@dataclass
class DiscountProfile:
    """Tytuły do zniżki, jakie posiada dana osoba — niezależne od karty miejskiej."""

    age: int | None = None
    is_student: bool = False
    is_senior: bool = False

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



def _load_group_price(item: dict | None) -> GroupPrice | None:
    if not item:
        return None
    return GroupPrice(
        price=float(item["price"]),
        label=item["label"],
        min_age=item.get("min_age"),
        max_age=item.get("max_age"),
        requires_status=item.get("requires_status", ""),
        source_url=item.get("source_url", ""),
        verified_date=item.get("verified_date", ""),
        price_verified=bool(item.get("price_verified", False)),
    )


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
                child_price=_load_group_price(item.get("child_price")),
                student_price=_load_group_price(item.get("student_price")),
                senior_price=_load_group_price(item.get("senior_price")),
                family_price=_load_group_price(item.get("family_price")),
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
                existence_verified=bool(item.get("existence_verified", False)),
                existence_source_url=item.get("existence_source_url", ""),
                existence_verified_date=item.get("existence_verified_date", ""),
            )
        )
    return res


def get_city_cards(city: str | None = None) -> list[CityCard]:
    """Zwraca karty miejskie dla wskazanego miasta, TYLKO te z potwierdzonym istnieniem.

    Niepotwierdzona może być co najwyżej cena istniejącej karty (price_verified na
    wariancie, z adnotacją w UI) — samo istnienie i działanie karty dziś musi być
    potwierdzone (existence_verified), inaczej karta w ogóle nie trafia do
    użytkownika jako opcja. Użyj `get_all_city_cards()`, żeby zobaczyć też karty
    niepotwierdzone (np. do celów administracyjnych/audytu danych).
    """
    cards = [c for c in get_all_city_cards() if c.existence_verified]
    city_key = normalize_city(city) if city else None
    if not city_key:
        return cards
    return [c for c in cards if c.city == city_key]


def best_price_for_attraction(
    attraction: Attraction, profile: "DiscountProfile | None" = None
) -> tuple[float, str, GroupPrice | None]:
    """Najtańsza cena wstępu, do której dana osoba ma prawo z DOWOLNEGO tytułu
    (wiek, status ucznia/studenta, senior) — niezależnie od posiadania karty miejskiej.

    Zwraca (cena, etykieta, źródło-GroupPrice-albo-None-dla-ceny-standardowej).
    Nigdy nie zgaduje: tytuł jest brany pod uwagę tylko jeśli atrakcja ma dla
    niego wypełnione, potwierdzone-lub-nie pole GroupPrice w danych.
    """
    candidates: list[tuple[float, str, GroupPrice | None]] = [
        (attraction.normal_price, "Cena standardowa (dorosły)", None)
    ]
    if profile is not None:
        gp = attraction.child_price
        if gp is not None and profile.age is not None:
            if (gp.min_age is None or profile.age >= gp.min_age) and (
                gp.max_age is None or profile.age <= gp.max_age
            ):
                candidates.append((gp.price, gp.label, gp))

        gp = attraction.student_price
        if gp is not None and profile.is_student:
            candidates.append((gp.price, gp.label, gp))

        gp = attraction.senior_price
        if gp is not None and (
            profile.is_senior
            or (
                profile.age is not None
                and gp.min_age is not None
                and profile.age >= gp.min_age
            )
        ):
            candidates.append((gp.price, gp.label, gp))

    return min(candidates, key=lambda c: c[0])


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
    profile: "DiscountProfile | None" = None,
) -> CityCardEvaluation:
    """Wylicza opłacalność pojedynczego wariantu karty miejskiej dla podanej listy atrakcji.

    `profile`, jeśli podany, każdej atrakcji przypisuje najpierw jej własną
    najtańszą aplikowalną cenę (wiek/uczeń/senior — patrz `best_price_for_attraction`),
    a zniżka karty miejskiej liczy się DODATKOWO na tej cenie. To uproszczenie:
    w rzeczywistości część operatorów nie pozwala łączyć zniżki statusowej ze
    zniżką kartową — nie modelujemy tego wyjątku, dopóki nie znajdziemy go
    wprost u źródła dla konkretnej atrakcji.
    """
    price_without = 0.0
    price_with = 0.0

    for a in attractions:
        base_price, _label, _source = best_price_for_attraction(a, profile)
        price_without += base_price
        disc_pct = _calculate_attraction_discount_percent(card, variant, a)
        discounted = base_price * (1.0 - (disc_pct / 100.0))
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
    profile: "DiscountProfile | None" = None,
) -> list[CityCardEvaluation]:
    """Wylicza opłacalność wszystkich kart i ich wariantów dostępnych w danym mieście."""
    cards = get_city_cards(city)
    evaluations: list[CityCardEvaluation] = []
    for card in cards:
        for variant in card.variants:
            evaluations.append(
                evaluate_city_card_variant(
                    card, variant, attractions, estimated_transit_cost, profile
                )
            )
    return evaluations


def suggest_best_city_card(
    city: str,
    attractions: list[Attraction],
    estimated_transit_cost: float = 0.0,
    profile: "DiscountProfile | None" = None,
) -> CityCardEvaluation | None:
    """Zwraca najbardziej opłacalny wariant karty miejskiej dla podanych atrakcji (jeśli istnieje)."""
    evaluations = evaluate_city_cards(city, attractions, estimated_transit_cost, profile)
    profitable = [e for e in evaluations if e.is_recommended]
    if not profitable:
        return None
    # Sortuj malejąco po oszczędnościach netto
    profitable.sort(key=lambda e: e.net_savings, reverse=True)
    return profitable[0]
