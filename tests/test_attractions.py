"""Testy modułu atrakcji i kart miejskich (attractions/)."""


from attractions import (
    Attraction,
    AttractionCategory,
    DiscountProfile,
    best_price_for_attraction,
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
    assert "ruhrtopcard" in card_ids
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


def test_gelsenkirchen_destination_ma_atrakcje_i_karte_ruhr():
    """Trasa testowa Lublin -> Buerer Straße, Gelsenkirchen: demo ma pokazać atrakcje i karty."""
    assert normalize_city("Buerer Straße 8, Gelsenkirchen") == "gelsenkirchen"
    attrs = get_attractions(city="Buerer Straße 8, Gelsenkirchen")
    assert len(attrs) >= 5
    categories = {a.category for a in attrs}
    assert AttractionCategory.SPORT in categories
    assert AttractionCategory.CULTURE in categories
    card_ids = [c.id for c in get_city_cards("Gelsenkirchen")]
    assert "ruhrtopcard" in card_ids


def test_niepotwierdzone_ceny_sa_oznaczone():
    """Ceny bez potwierdzenia w źródle muszą mieć price_verified=False (flaga w UI)."""
    by_id = {a.id: a for a in get_all_attractions()}
    assert by_id["gelsenkirchen_zoom_erlebniswelt"].price_verified is True
    assert by_id["gelsenkirchen_veltins_arena"].price_verified is True
    assert by_id["krakow_kazimierz_zapiekanki"].price_verified is False
    ruhr = next(c for c in get_all_city_cards() if c.id == "ruhrtopcard")
    assert ruhr.variants and all(v.price_verified is True for v in ruhr.variants)


def test_demo_format_city_section_dla_gelsenkirchen():
    import demo

    text = demo.format_city_section("Buerer Straße 8, Gelsenkirchen")
    assert "Veltins-Arena" in text
    assert "ZOOM Erlebniswelt" in text
    assert "RUHR.TOPCARD 2026" in text
    assert "cena niepotwierdzona" in text
    assert "Rekomendacja" in text


def test_demo_format_city_section_nieznane_miasto():
    import demo

    assert "nie rozpoznano" in demo.format_city_section("Nieznane miasto, Atlantyda")


def test_best_price_for_attraction_bez_profilu_to_cena_normalna():
    zoom = next(a for a in get_all_attractions() if a.id == "gelsenkirchen_zoom_erlebniswelt")
    price, label, source = best_price_for_attraction(zoom)
    assert price == zoom.normal_price
    assert label == "Cena standardowa (dorosły)"
    assert source is None


def test_best_price_for_attraction_dziecko_dostaje_cene_dziecieca():
    zoom = next(a for a in get_all_attractions() if a.id == "gelsenkirchen_zoom_erlebniswelt")
    price, label, source = best_price_for_attraction(zoom, DiscountProfile(age=8))
    assert price == 15.50
    assert "Dziecko" in label
    assert source is zoom.child_price


def test_best_price_for_attraction_uczen_dostaje_cene_studencka_nawet_bez_wieku():
    zoom = next(a for a in get_all_attractions() if a.id == "gelsenkirchen_zoom_erlebniswelt")
    price, label, source = best_price_for_attraction(zoom, DiscountProfile(is_student=True))
    assert price == 17.50
    assert source is zoom.student_price


def test_best_price_for_attraction_bierze_najtansza_z_kilku_tytulow():
    # Fußballmuseum: dziecko do 6 lat 0 EUR, uczeń/student <26 15 EUR — 5-latek-uczeń (niemożliwe
    # w praktyce, ale testuje logikę "bierz minimum") powinien dostać cenę dziecięcą (tańszą).
    museum = next(a for a in get_all_attractions() if a.id == "dortmund_fussballmuseum")
    price, _label, source = best_price_for_attraction(
        museum, DiscountProfile(age=5, is_student=True)
    )
    assert price == 0.0
    assert source is museum.child_price


def test_best_price_for_attraction_dorosly_bez_zniżek_dostaje_cene_normalna():
    museum = next(a for a in get_all_attractions() if a.id == "dortmund_fussballmuseum")
    price, label, source = best_price_for_attraction(museum, DiscountProfile(age=40))
    assert price == museum.normal_price
    assert source is None
    assert label == "Cena standardowa (dorosły)"


def test_best_price_for_attraction_bez_pol_grupowych_nie_wybucha():
    # Atrakcja bez skonfigurowanych cen grupowych (np. Zeche Zollverein) ma zawsze zwrócić cenę normalną.
    zollverein = next(a for a in get_all_attractions() if a.id == "essen_zeche_zollverein")
    price, _label, source = best_price_for_attraction(zollverein, DiscountProfile(age=10, is_student=True))
    assert price == zollverein.normal_price
    assert source is None


def test_evaluate_city_card_variant_z_profilem_uwzglednia_zniżke_tytulowa():
    attrs = get_attractions(city="Gelsenkirchen")
    zoom = [a for a in attrs if a.id == "gelsenkirchen_zoom_erlebniswelt"]
    assert len(zoom) == 1

    bez_profilu = evaluate_city_cards("Gelsenkirchen", zoom, estimated_transit_cost=0.0)
    z_profilem = evaluate_city_cards(
        "Gelsenkirchen", zoom, estimated_transit_cost=0.0, profile=DiscountProfile(is_student=True)
    )
    base_bez = next(e for e in bez_profilu if e.variant.id == "ruhrtopcard_2026_adult")
    base_z = next(e for e in z_profilem if e.variant.id == "ruhrtopcard_2026_adult")

    assert base_bez.attractions_price_without_card == zoom[0].normal_price
    assert base_z.attractions_price_without_card == 17.50
    assert base_z.attractions_price_without_card < base_bez.attractions_price_without_card
