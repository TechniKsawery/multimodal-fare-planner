"""Testy modułu atrakcji i kart miejskich (attractions/)."""


from attractions import (
    Attraction,
    AttractionCategory,
    evaluate_city_cards,
    get_all_attractions,
    get_all_city_cards,
    get_attractions,
    get_city_cards,
    normalize_city,
    suggest_best_city_card,
)


def test_get_all_attractions():
    attractions = get_all_attractions()
    assert len(attractions) >= 15
    for a in attractions:
        assert a.id
        assert a.name
        assert a.city in ("gelsenkirchen", "berlin", "krakow", "lublin")
        assert isinstance(a.category, AttractionCategory)
        assert a.normal_price >= 0.0
        assert a.currency in ("EUR", "PLN")


def test_normalize_city():
    assert normalize_city("Bahnhofstraße, Gelsenkirchen") == "gelsenkirchen"
    assert normalize_city("Gelsenkirchen-Buer") == "gelsenkirchen"
    assert normalize_city("Essen Hbf") == "gelsenkirchen"
    assert normalize_city("Dortmund Hauptbahnhof") == "gelsenkirchen"
    assert normalize_city("Alexanderplatz, Berlin") == "berlin"
    assert normalize_city("Kraków Główny") == "krakow"
    assert normalize_city("ul. Lipowa, Kraków") == "krakow"
    assert normalize_city("Krakowskie Przedmieście 50, Lublin") == "lublin"
    assert normalize_city("Warszawa Centralna") == "warszawa"
    assert normalize_city("Unknown Location") is None
    assert normalize_city(None) is None


def test_get_attractions_by_city():
    berlin_attractions = get_attractions(city="Berlin")
    assert len(berlin_attractions) >= 5
    assert all(a.city == "berlin" for a in berlin_attractions)

    gelsenkirchen_attractions = get_attractions(city="Gelsenkirchen")
    assert len(gelsenkirchen_attractions) >= 5
    assert any("Veltins-Arena" in a.name for a in gelsenkirchen_attractions)


def test_get_attractions_by_category():
    sport_attractions = get_attractions(category=AttractionCategory.SPORT)
    assert len(sport_attractions) >= 4
    for a in sport_attractions:
        assert a.category == AttractionCategory.SPORT

    # Przekazanie kategorii jako string
    culture_attractions = get_attractions(category="turystyka_kultura")
    assert len(culture_attractions) >= 5
    for a in culture_attractions:
        assert a.category == AttractionCategory.CULTURE


def test_get_attractions_by_city_and_category():
    berlin_sport = get_attractions(city="Berlin", category=AttractionCategory.SPORT)
    assert len(berlin_sport) >= 2
    assert any(a.id == "berlin_olympiastadion" for a in berlin_sport)
    assert all(a.city == "berlin" and a.category == AttractionCategory.SPORT for a in berlin_sport)


def test_get_city_cards():
    cards = get_all_city_cards()
    assert len(cards) >= 3
    card_ids = [c.id for c in cards]
    assert "berlin_welcomecard" in card_ids
    assert "welcomecard_ruhr" in card_ids
    assert "krakow_card" in card_ids

    berlin_cards = get_city_cards("Berlin")
    assert len(berlin_cards) == 1
    assert berlin_cards[0].id == "berlin_welcomecard"
    assert len(berlin_cards[0].variants) >= 4


def test_evaluate_city_cards_not_profitable_when_few_attractions():
    # Przy tylko jednej darmowej atrakcji karta nie ma prawa się opłacać
    free_attr = Attraction(
        id="free_gate",
        name="Darmowa brama",
        city="berlin",
        category=AttractionCategory.CULTURE,
        description="Wstęp wolny",
        normal_price=0.0,
        currency="EUR",
    )
    evals = evaluate_city_cards("Berlin", [free_attr], estimated_transit_cost=0.0)
    assert len(evals) > 0
    assert all(not e.is_recommended for e in evals)
    assert all(e.net_savings < 0 for e in evals)
    assert suggest_best_city_card("Berlin", [free_attr], estimated_transit_cost=0.0) is None


def test_evaluate_city_cards_profitable_with_many_attractions_and_transit():
    # Odwiedzamy kilka płatnych atrakcji w Berlinie i korzystamy z komunikacji (np. koszt 15 EUR)
    berlin_attrs = get_attractions(city="Berlin")
    # Wybieramy wieżę telewizyjną (24.50 EUR), stadion (15 EUR), wyspę muzeów (14 EUR) -> 53.50 EUR
    selected = [
        a for a in berlin_attrs
        if a.id in ("berlin_fernsehturm", "berlin_olympiastadion", "berlin_museumsinsel")
    ]
    assert len(selected) == 3

    # Transit w Berlinie za 2 dni: ~19 EUR
    evals = evaluate_city_cards("Berlin", selected, estimated_transit_cost=19.0)
    # Z kartą 48h (27 EUR):
    # Koszt bez karty: 53.50 + 19.0 = 72.50 EUR
    # Z kartą: 27.0 (karta z transportem) + zniżki 25% na bilety (~40.12 EUR) = ~67.12 EUR -> zysk ok. 5.38 EUR
    profitable = [e for e in evals if e.is_recommended]
    assert len(profitable) > 0

    best = suggest_best_city_card("Berlin", selected, estimated_transit_cost=19.0)
    assert best is not None
    assert best.is_recommended
    assert best.net_savings > 0
    assert "Zaoszczędzisz" in best.summary


def test_special_variant_discount_museumsinsel():
    # Berlin WelcomeCard 72h + Museumsinsel daje 100% zniżki na muzea wyspy
    attrs = get_attractions(city="Berlin")
    museumsinsel = [a for a in attrs if a.id == "berlin_museumsinsel"]
    assert len(museumsinsel) == 1

    evals = evaluate_city_cards("Berlin", museumsinsel, estimated_transit_cost=20.0)
    museum_variant_eval = next(
        e for e in evals if e.variant.id == "bwc_72h_museumsinsel"
    )
    # Zniżka na bilet wynosi pełne 100% (bilet 14 EUR staje się darmowy 0 EUR)
    assert museum_variant_eval.attractions_price_with_card == 0.0
