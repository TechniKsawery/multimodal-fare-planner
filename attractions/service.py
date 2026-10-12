"""Serwis obsługujący katalog atrakcji, filtrowanie kategorii i kalkulator City Cards."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from routing.currency import convert

from ._data_loading import load
from .model import (
    Attraction,
    AttractionCategory,
    CityCard,
    CityCardEvaluation,
    CityCardVariant,
    DiscountSource,
    GroupPrice,
    HeldDocument,
)

# Typy dokumentów traktowane jako "status ucznia/studenta" / "status seniora" przy
# dopasowywaniu HeldDocument do GroupPrice.student_price / .senior_price.
_STUDENT_DOC_TYPES = {"legitymacja_szkolna", "legitymacja_studencka", "ISIC"}
_SENIOR_DOC_TYPES = {"karta_seniora"}


@dataclass
class DiscountProfile:
    """Tytuły do zniżki, jakie posiada dana osoba — niezależne od karty miejskiej.

    `is_student`/`is_senior` to proste flagi (bez info o kraju) — zachowane dla
    wstecznej zgodności i prostych wywołań. `documents` pozwala opisać dokładniej
    PRZYPADEK WIELU DOKUMENTÓW naraz z różnych krajów (np. osoba chodząca do szkoły
    niemieckiej I dodatkowej szkoły polskiej w Niemczech, z legitymacją niemiecką
    i polską) — wtedy różne atrakcje/przewoźnicy mogą uznawać różne z nich.
    """

    age: int | None = None
    is_student: bool = False
    is_senior: bool = False
    documents: list[HeldDocument] = field(default_factory=list)

    def has_recognized_document(
        self, doc_types: set[str], recognized_countries: list[str] | None
    ) -> bool:
        """Czy profil ma dokument pasującego typu, którego kraj wydania jest
        uznawany przez daną zniżkę (recognized_countries=None = źródło nie
        ogranicza wg kraju, więc każdy pasujący typ dokumentu się liczy)."""
        for doc in self.documents:
            if doc.doc_type not in doc_types:
                continue
            if recognized_countries is None or doc.issuing_country in recognized_countries:
                return True
        return False

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
    "poznan": "poznan",
    "poznań": "poznan",
    "hamburg": "hamburg",
    "munchen": "munchen",
    "münchen": "munchen",
    "munich": "munchen",
    "monachium": "munchen",
    "koln": "koln",
    "köln": "koln",
    "cologne": "koln",
    "kolonia": "koln",
    "wroclaw": "wroclaw",
    "wrocław": "wroclaw",
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



def _load_discount_source(item: dict | None) -> DiscountSource | None:
    if not item:
        return None
    return DiscountSource(
        source_url=str(item.get("source_url", "")),
        verified_date=str(item.get("verified_date", "")),
    )


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
        recognized_countries=item.get("recognized_countries"),
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
                card_discount_source=_load_discount_source(item.get("card_discount_source")),
                address=item.get("address", ""),
                official_url=item.get("official_url", ""),
                highlight=bool(item.get("highlight", False)),
                tags=list(item.get("tags", [])),
                price_verified=bool(item.get("price_verified", False)),
                child_price=_load_group_price(item.get("child_price")),
                student_price=_load_group_price(item.get("student_price")),
                senior_price=_load_group_price(item.get("senior_price")),
                family_price=_load_group_price(item.get("family_price")),
                dynamic_pricing=bool(item.get("dynamic_pricing", False)),
                price_is_from=bool(
                    item.get("price_is_from", False) or item.get("dynamic_pricing", False)
                ),
                variable_pricing_note=item.get("variable_pricing_note", ""),
                closed_until=item.get("closed_until", ""),
                closed_source_url=item.get("closed_source_url", ""),
            )
        )
    return res


def is_closed(attraction: Attraction, today: date | None = None) -> bool:
    """True, gdy atrakcja ma flagę zamknięcia i data końca zamknięcia jeszcze nie minęła."""
    if not attraction.closed_until:
        return False
    return (today or date.today()) <= date.fromisoformat(attraction.closed_until)


def get_attractions(
    city: str | None = None,
    category: AttractionCategory | str | None = None,
    include_closed: bool = False,
) -> list[Attraction]:
    """Zwraca atrakcje, opcjonalnie przefiltrowane po mieście lub kategorii.

    Tymczasowo zamknięte atrakcje (closed_until) są pomijane, chyba że include_closed=True."""
    attractions = get_all_attractions()
    city_key = normalize_city(city) if city else None
    cat_enum = AttractionCategory(category) if isinstance(category, str) else category

    filtered = []
    for a in attractions:
        if city_key and a.city != city_key:
            continue
        if cat_enum and a.category != cat_enum:
            continue
        if not include_closed and is_closed(a):
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
                custom_discounts=dict(item.get("custom_discounts", {})),
                custom_discount_sources={
                    aid: src
                    for aid, raw_src in item.get("custom_discount_sources", {}).items()
                    if (src := _load_discount_source(raw_src)) is not None
                },
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


def _age_in_range(gp: GroupPrice, age: int | None) -> bool:
    """Czy wiek mieści się w granicach min_age/max_age ceny. Gdy cena ma granicę wieku,
    a wiek jest nieznany, nie przyznajemy zniżki (nie zgadujemy)."""
    if gp.min_age is None and gp.max_age is None:
        return True
    if age is None:
        return False
    return (gp.min_age is None or age >= gp.min_age) and (
        gp.max_age is None or age <= gp.max_age
    )


def _status_title_applies(
    gp: GroupPrice, profile: "DiscountProfile", flag: bool, doc_types: set[str]
) -> bool:
    """Czy tytuł statusowy (uczeń/student, senior) przysługuje: wiek w granicach ceny ORAZ
    status. Gdy źródło ogranicza zniżkę do dokumentów z konkretnych krajów
    (recognized_countries), sama flaga nie wystarcza - trzeba dokumentu z takiego kraju."""
    if not _age_in_range(gp, profile.age):
        return False
    if gp.recognized_countries is not None:
        return profile.has_recognized_document(doc_types, gp.recognized_countries)
    return flag or profile.has_recognized_document(doc_types, None)


def price_from_note(attraction: Attraction) -> str:
    """Adnotacja do ceny wyświetlanej użytkownikowi ("" gdy cena jest stała)."""
    if not attraction.price_is_from:
        return ""
    note = attraction.variable_pricing_note or "ceny zależą od terminu/wariantu, ulgi możliwe"
    return note


def best_price_for_attraction(
    attraction: Attraction, profile: "DiscountProfile | None" = None
) -> tuple[float, str, GroupPrice | None]:
    """Najtańsza cena wstępu, do której dana osoba ma prawo z DOWOLNEGO tytułu
    (wiek, status ucznia/studenta, senior) — niezależnie od posiadania karty miejskiej.

    Zwraca (cena, etykieta, źródło-GroupPrice-albo-None-dla-ceny-standardowej).
    Nigdy nie zgaduje: tytuł jest brany pod uwagę tylko jeśli atrakcja ma dla
    niego wypełnione, potwierdzone-lub-nie pole GroupPrice w danych.

    Osoba może posiadać KILKA dokumentów naraz z różnych krajów (np. legitymacja
    niemiecka i polska) — `profile.documents` + `GroupPrice.recognized_countries`
    pozwalają dopasować właściwy dokument, gdy źródło jawnie ogranicza zniżkę do
    dokumentów z konkretnych krajów (patrz docstring `GroupPrice`).
    """
    candidates: list[tuple[float, str, GroupPrice | None]] = [
        (attraction.normal_price, "Cena standardowa (dorosły)", None)
    ]
    # Ceny dynamiczne: nie ma stałej kwoty ulgi, więc nie zgadujemy - zostaje cena "od".
    if profile is not None and not attraction.dynamic_pricing:
        gp = attraction.child_price
        if gp is not None and profile.age is not None:
            # Cena dziecięca bez ŻADNEJ granicy wieku nie może przysługiwać dorosłemu:
            # wymagamy górnej granicy (dane bez max_age są traktowane jak niekompletne).
            if gp.max_age is not None and _age_in_range(gp, profile.age):
                candidates.append((gp.price, gp.label, gp))

        gp = attraction.student_price
        if gp is not None and _status_title_applies(
            gp, profile, profile.is_student, _STUDENT_DOC_TYPES
        ):
            candidates.append((gp.price, gp.label, gp))

        gp = attraction.senior_price
        if gp is not None and (
            _status_title_applies(gp, profile, profile.is_senior, _SENIOR_DOC_TYPES)
            or (
                profile.age is not None
                and gp.min_age is not None
                and profile.age >= gp.min_age
                and (gp.max_age is None or profile.age <= gp.max_age)
            )
        ):
            candidates.append((gp.price, gp.label, gp))

    return min(candidates, key=lambda c: c[0])


def _resolve_card_discount(
    card: CityCard, variant: CityCardVariant, attraction: Attraction
) -> tuple[float, bool]:
    """Zniżka karty na atrakcję: (procent, czy_niezweryfikowana).

    Zniżka > 0% liczy się TYLKO ze źródłem (URL + data weryfikacji: `custom_discount_sources`
    karty albo `card_discount_source` atrakcji). Zapisana zniżka bez kompletnego źródła, jak
    i brak jakiegokolwiek wpisu, daje 0% i flagę niezweryfikowanej zniżki (karta mogłaby ją
    dawać, tylko nie mamy tego w danych ze źródłem). Jawne 0.0 w custom_discounts to znany
    brak zniżki, nie flaga.
    """
    # Specjalne uprawnienia dla konkretnych wariantów (np. BWC Museumsinsel daje 100% zniżki na muzea)
    if (
        variant.id == "bwc_72h_museumsinsel"
        and attraction.id == "berlin_museumsinsel"
    ):
        return 100.0, False

    if attraction.id in card.custom_discounts:
        percent = card.custom_discounts[attraction.id]
        source = card.custom_discount_sources.get(attraction.id)
    else:
        percent = attraction.default_card_discount_percent
        source = attraction.card_discount_source

    if percent == 0.0 and attraction.id in card.custom_discounts:
        return 0.0, False
    if percent > 0.0 and source is not None and source.is_complete:
        return percent, False
    # Brak wpisu albo wpis bez źródła: nie zgadujemy rabatu "całej karty" (np. 100% na Katedrę
    # Wawelską, 25% na Curry 36).
    return 0.0, True


def _calculate_attraction_discount_percent(
    card: CityCard, variant: CityCardVariant, attraction: Attraction
) -> float:
    return _resolve_card_discount(card, variant, attraction)[0]


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

    # Waluta rozliczenia = waluta wybranych atrakcji (gdy jednolita), inaczej waluta wariantu
    # karty. Ceny kart i atrakcji w innej walucie są przeliczane (routing.currency), a
    # estimated_transit_cost jest podawany już w walucie rozliczenia.
    currencies = {a.currency for a in attractions}
    currency = currencies.pop() if len(currencies) == 1 else variant.currency
    card_price = convert(variant.price, variant.currency, currency)

    unverified: list[str] = []
    for a in attractions:
        base_price, _label, _source = best_price_for_attraction(a, profile)
        base_price = convert(base_price, a.currency, currency)
        price_without += base_price
        disc_pct, is_unverified = _resolve_card_discount(card, variant, a)
        if is_unverified:
            unverified.append(a.id)
        discounted = base_price * (1.0 - (disc_pct / 100.0))
        price_with += max(0.0, discounted)

    transit_savings = estimated_transit_cost if variant.includes_public_transit else 0.0
    total_without = price_without + estimated_transit_cost
    # Wariant BEZ transportu w cenie nie zwalnia z kosztu komunikacji: płacimy go tak samo
    # z kartą jak bez niej, więc nie może wchodzić do "oszczędności".
    total_with = card_price + price_with + (
        0.0 if variant.includes_public_transit else estimated_transit_cost
    )

    net_savings = round(total_without - total_with, 2)
    is_recommended = net_savings > 0.0

    if is_recommended:
        summary = (
            f"Kupno {variant.name} opłaca się! Zaoszczędzisz łącznie {net_savings:.2f} {currency} "
            f"(wstępy: {price_without - price_with:.2f} {currency} zniżki"
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
            f"{variant.name} kosztuje {card_price:.2f} {currency}. "
            f"Przy obecnym zestawie atrakcji zabraknie około {diff:.2f} {currency} "
            f"do zwrotu kosztu karty."
        )

    if unverified:
        summary += (
            f" Brak zapisanej zniżki karty dla: {', '.join(unverified)} — liczone jako 0% "
            "(niezweryfikowane, karta może dawać zniżkę, której nie mamy w danych)."
        )

    return CityCardEvaluation(
        card_name=card.name,
        variant=variant,
        attractions_count=len(attractions),
        attractions_price_without_card=round(price_without, 2),
        attractions_price_with_card=round(price_with, 2),
        card_price=round(card_price, 2),
        estimated_transit_savings=round(transit_savings, 2),
        total_cost_without_card=round(total_without, 2),
        total_cost_with_card=round(total_with, 2),
        net_savings=net_savings,
        currency=currency,
        is_recommended=is_recommended,
        summary=summary,
        unverified_discount_attraction_ids=unverified,
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
