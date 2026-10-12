"""Testy modułu atrakcji i kart miejskich (attractions/)."""

from attractions import (
    Attraction,
    AttractionCategory,
    CityCard,
    DiscountProfile,
    GroupPrice,
    HeldDocument,
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
        assert a.city in (
            "gelsenkirchen",
            "berlin",
            "krakow",
            "lublin",
            "warszawa",
            "hamburg",
            "munchen",
            "koln",
            "wroclaw",
            "poznan",
        )
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


def test_poznan_city_card_zweryfikowana_z_pelnym_cennikiem():
    """Poznańska Karta Turystyczna (zweryfikowana w przeglądarce 2026-10-10 na
    visitpoznan.pl/karta, strona datowana "Ostatnia aktualizacja: 2026-09-14")."""
    poznan_cards = get_city_cards("Poznań")
    assert len(poznan_cards) == 1
    card = poznan_cards[0]
    assert card.id == "poznan_city_card"
    assert len(card.variants) == 6
    by_id = {v.id for v in card.variants}
    assert "poznan_card_24h_transport" in by_id
    assert all(v.price_verified for v in card.variants)


def test_warsaw_pass_zweryfikowany_komercyjna_karta():
    """Warsaw Pass: komercyjna karta OTA (nie oficjalna karta miasta), tylko wariant 24h,
    cena niepotwierdzona u pierwotnego źródła (przeliczenie z ceny w USD) — warianty 48h/72h
    nieustalone, patrz opis karty w city_cards.json."""
    cards = get_city_cards("Warszawa")
    assert len(cards) == 1
    card = cards[0]
    assert card.id == "warsaw_pass"
    assert len(card.variants) == 1
    assert all(not v.price_verified and not v.includes_public_transit for v in card.variants)


def test_krakow_card_warianty_glowne_zweryfikowane_student_pass_nie():
    """Kraków Card: warianty 1/2/3 dni zweryfikowane na żywo 2026-10-09 na discovercracow.com
    (ceny w EUR). Krakow Museum Pass for Students to osobny produkt z ceną zależną od daty —
    pozostaje niepotwierdzony."""
    card = next(c for c in get_all_city_cards() if c.id == "krakow_card")
    by_id = {v.id: v for v in card.variants}
    assert all(
        by_id[v].price_verified
        for v in ("krakow_card_1_dzien", "krakow_card_2_dni", "krakow_card_3_dni")
    )
    assert by_id["krakow_museum_pass_student_3d"].price_verified is False


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


def _berlin_attrs_3():
    selected = [
        a
        for a in get_attractions(city="Berlin")
        if a.id in ("berlin_fernsehturm", "berlin_olympiastadion", "berlin_museumsinsel")
    ]
    assert len(selected) == 3
    return selected


def _berlin_card_ze_zrodlem():
    """Berlin WelcomeCard z 25% na 3 atrakcje ZE ŹRÓDŁEM (syntetyczne — w danych te zniżki
    nie mają dziś pola źródła, więc są wyzerowane)."""
    import dataclasses

    from attractions import DiscountSource

    card = _card("berlin_welcomecard")
    ids = ("berlin_fernsehturm", "berlin_olympiastadion", "berlin_museumsinsel")
    return dataclasses.replace(
        card,
        custom_discounts={i: 25.0 for i in ids},
        custom_discount_sources={i: DiscountSource("https://example.test/zrodlo", "2026-10-12") for i in ids},
    )


def test_evaluate_city_cards_profitable_with_many_attractions_and_transit():
    # Zniżki 25% ZE ŹRÓDŁEM + 19 EUR komunikacji: wariant 48h AB (28,50 EUR) się opłaca.
    # Bez karty: 20 + 11 + 24 + 19 = 74,00; z kartą: 28,50 + 0,75 * 55 = 69,75 -> zysk 4,25 EUR.
    from attractions.service import evaluate_city_card_variant

    card = _berlin_card_ze_zrodlem()
    variant = next(v for v in card.variants if v.id == "bwc_48h_ab")
    ev = evaluate_city_card_variant(card, variant, _berlin_attrs_3(), estimated_transit_cost=19.0)
    assert ev.is_recommended
    assert ev.net_savings == 4.25
    assert "Zaoszczędzisz" in ev.summary
    assert not ev.unverified_discount_attraction_ids


def test_suggest_best_city_card_wybiera_oplacalny_wariant_ze_zrodlem(monkeypatch):
    import attractions.service as service

    card = _berlin_card_ze_zrodlem()
    monkeypatch.setattr(service, "get_city_cards", lambda city=None: [card])
    best = suggest_best_city_card("Berlin", _berlin_attrs_3(), estimated_transit_cost=19.0)
    assert best is not None
    assert best.is_recommended
    assert best.net_savings > 0


def test_berlin_znizki_ze_zrodlem_liczone_a_museumsinsel_classic_zostaje_zerem_z_flaga():
    # Dane w repo (źródło wg raportu Gemini, 2026-10-12): Fernsehturm i Olympiastadion 25% ze
    # źródłem; Museumsinsel dla wariantów Classic bez źródła zniżki -> 0% + flaga.
    evals = evaluate_city_cards("Berlin", _berlin_attrs_3(), estimated_transit_cost=19.0)
    assert evals
    for ev in evals:
        if ev.variant.id == "bwc_72h_museumsinsel":
            continue  # ten wariant ma 100% na Museumsinsel z definicji produktu
        # bez karty: 20 + 11 + 24 = 55; z kartą: 0,75 * 31 + 24 = 47,25
        assert ev.attractions_price_without_card == 55.0
        assert ev.attractions_price_with_card == 47.25
        assert ev.unverified_discount_attraction_ids == ["berlin_museumsinsel"]
        assert "niezweryfikowane" in ev.summary


def test_special_variant_discount_museumsinsel():
    # Berlin WelcomeCard 72h + Museumsinsel daje 100% zniżki na muzea wyspy
    attrs = get_attractions(city="Berlin")
    museumsinsel = [a for a in attrs if a.id == "berlin_museumsinsel"]
    assert len(museumsinsel) == 1

    evals = evaluate_city_cards("Berlin", museumsinsel, estimated_transit_cost=20.0)
    museum_variant_eval = next(e for e in evals if e.variant.id == "bwc_72h_museumsinsel")
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


def test_get_city_cards_pomija_karty_bez_potwierdzonego_istnienia():
    # Wszystkie karty w danych mają dziś existence_verified=True (potwierdzone na żywo).
    all_cards = get_all_city_cards()
    assert all(c.existence_verified for c in all_cards)
    assert all(c.existence_source_url and c.existence_verified_date for c in all_cards)


def test_get_city_cards_filtruje_po_existence_verified(monkeypatch):
    # Symulujemy martwy produkt (jak dawna WelcomeCard Ruhr) obok prawdziwej karty: filtr
    # get_city_cards ma pokazać tylko tę z potwierdzonym istnieniem.
    confirmed = CityCard(
        id="real_card",
        city="krakow",
        name="Prawdziwa karta",
        description="",
        official_url="https://example.test/real",
        variants=[],
        existence_verified=True,
        existence_source_url="https://example.test/real",
        existence_verified_date="2026-10-10",
    )
    dead = CityCard(
        id="fake_dead_card",
        city="krakow",
        name="Martwa karta testowa",
        description="",
        official_url="",
        variants=[],
        existence_verified=False,
    )
    import attractions.service as service_module

    monkeypatch.setattr(service_module, "get_all_city_cards", lambda: [confirmed, dead])
    result_ids = [c.id for c in service_module.get_city_cards("Kraków")]
    assert "real_card" in result_ids
    assert "fake_dead_card" not in result_ids


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
    assert "Rekomendacja: żadna karta miejska nie zwraca kosztu" in text


def test_demo_format_city_section_etykieta_bez_miasta_uzywa_tekstu_uzytkownika():
    import demo

    assert "nie rozpoznano" in demo.format_city_section("Buerer Straße 8")
    text = demo.format_city_section(
        "Buerer Straße 8", fallback_text="Buerer Straße 8, Gelsenkirchen"
    )
    assert "Veltins-Arena" in text


def test_demo_format_city_section_nieznane_miasto():
    import demo

    assert "nie rozpoznano" in demo.format_city_section("Nieznane miasto, Atlantyda")


def test_demo_format_city_section_pokazuje_tytul_znizki_z_profilem():
    import demo

    text = demo.format_city_section(
        "Buerer Straße 8, Gelsenkirchen", demo.AttractionDiscountProfile(is_student=True)
    )
    assert "Uczeń/student" in text
    assert "17.50" in text or "17,50" in text


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
    # Atrakcja bez skonfigurowanych cen grupowych (np. Curry 36) ma zawsze zwrócić cenę normalną.
    curry36 = next(a for a in get_all_attractions() if a.id == "berlin_curry36")
    price, _label, source = best_price_for_attraction(curry36, DiscountProfile(age=10, is_student=True))
    assert price == curry36.normal_price
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


def test_best_price_dla_dokumentu_bez_ograniczenia_krajowego():
    # Osoba NIE ma is_student=True, ale ma polską legitymację szkolną — GroupPrice bez
    # recognized_countries (nieznane/nieograniczone) ma mimo to zadziałać (bez zgadywania
    # ograniczeń, których źródło nie podaje).
    zoom = next(a for a in get_all_attractions() if a.id == "gelsenkirchen_zoom_erlebniswelt")
    profile = DiscountProfile(documents=[HeldDocument(doc_type="legitymacja_szkolna", issuing_country="PL")])
    price, _label, source = best_price_for_attraction(zoom, profile)
    assert price == 17.50
    assert source is zoom.student_price


def test_best_price_respektuje_jawne_ograniczenie_kraju_dokumentu():
    # Atrakcja testowa, której zniżka studencka jest JAWNIE ograniczona do dokumentów
    # wydanych w Niemczech (recognized_countries=["DE"]) — osoba z WYŁĄCZNIE polską
    # legitymacją nie powinna jej dostać, ale z niemiecką już tak.
    student_price = GroupPrice(
        price=10.0,
        label="Uczeń/student (tylko DE)",
        requires_status="legitymacja niemiecka",
        recognized_countries=["DE"],
    )
    attr = Attraction(
        id="test_restricted_student",
        name="Testowa atrakcja",
        city="gelsenkirchen",
        category=AttractionCategory.CULTURE,
        description="",
        normal_price=20.0,
        currency="EUR",
        student_price=student_price,
    )

    only_polish = DiscountProfile(
        documents=[HeldDocument(doc_type="legitymacja_studencka", issuing_country="PL")]
    )
    price, _label, source = best_price_for_attraction(attr, only_polish)
    assert price == attr.normal_price
    assert source is None

    with_german = DiscountProfile(
        documents=[
            HeldDocument(doc_type="legitymacja_studencka", issuing_country="PL"),
            HeldDocument(doc_type="legitymacja_studencka", issuing_country="DE"),
        ]
    )
    price, _label, source = best_price_for_attraction(attr, with_german)
    assert price == 10.0
    assert source is student_price
def test_nowe_miasta_rozpoznawane_i_maja_atrakcje():
    """Miasta dodane 2026-10-09 (Warszawa doprecyzowana, Hamburg, Monachium, Kolonia, Wrocław)."""
    cases = {
        "Plac Defilad 1, Warszawa": "warszawa",
        "Speersort 1, Hamburg": "hamburg",
        "Marienplatz 1, München": "munchen",
        "Domkloster 4, Köln": "koln",
        "Rynek 1, Wrocław": "wroclaw",
    }
    for address, expected_city in cases.items():
        assert normalize_city(address) == expected_city
        attrs = get_attractions(city=expected_city)
        assert len(attrs) >= 5, f"{expected_city}: oczekiwano co najmniej 5 atrakcji"


def test_poznan_ma_fares_i_atrakcje_pelny_pakiet():
    """Poznań miał już kalkulator transportu (fares/ztm_poznan.py) — dociągnęliśmy atrakcje, żeby domknąć pełny pakiet."""
    attrs = get_attractions(city="Poznań")
    assert len(attrs) >= 5
    card_ids = [c.id for c in get_city_cards("Poznań")]
    assert "poznan_city_card" in card_ids
    poznan_card = next(c for c in get_all_city_cards() if c.id == "poznan_city_card")
    assert all(v.price_verified for v in poznan_card.variants)
    # Brama Poznania 40% i Fotoplastykon 100%: zniżki ze źródłem (karta.visitpoznan.pl, raport 2026-10-12)
    assert poznan_card.custom_discounts == {"poznan_brama_poznania": 40.0, "poznan_fotoplastykon": 100.0}
    assert set(poznan_card.custom_discount_sources) == set(poznan_card.custom_discounts)
    assert _card_discount_percent("poznan_city_card", "poznan_brama_poznania") == 40.0
    assert _card_discount_percent("poznan_city_card", "poznan_fotoplastykon") == 100.0


def test_nowe_karty_miejskie_maja_jasno_oznaczona_niepewnosc():
    """Hamburg CARD/KölnCard/München CityTourCard/Warsaw Pass: tam gdzie cena nie jest
    potwierdzona u operatora (lub dwa źródła podają rozbieżne ceny), price_verified musi być
    False. Dane zweryfikowane w przeglądarce 2026-10-09 (Remote Control + Claude in Chrome)."""
    cards_by_id = {
        c.id: c
        for c in get_all_city_cards()
        if c.id in ("hamburg_card", "koln_card", "munchen_citytourcard", "warsaw_pass")
    }
    assert set(cards_by_id) == {"hamburg_card", "koln_card", "munchen_citytourcard", "warsaw_pass"}

    hamburg_card = cards_by_id["hamburg_card"]
    assert all(v.price_verified for v in hamburg_card.variants)
    # 25% (Speicherstadtmuseum) i 22% (IMM): zniżki ze źródłem (raport 2026-10-12)
    assert hamburg_card.custom_discounts == {
        "hamburg_speicherstadtmuseum": 25.0,
        "hamburg_imm": 22.0,
    }

    munchen_card = cards_by_id["munchen_citytourcard"]
    assert all(v.price_verified for v in munchen_card.variants)
    for not_a_partner in ("munchen_bmw_museum", "munchen_deutsches_museum", "munchen_hellabrunn", "munchen_skylift_olympiapark"):
        assert not_a_partner not in munchen_card.custom_discounts

    # KölnCard: flyer oficjalny i VRS-Ticketshop podają rozbieżne ceny dla 48h-single/24h-group —
    # te dwa warianty muszą być oznaczone jako niepewne, podczas gdy 24h-single/48h-group (oba
    # źródła zgodne) są potwierdzone.
    koln_card = cards_by_id["koln_card"]
    verified_by_id = {v.id: v.price_verified for v in koln_card.variants}
    assert verified_by_id["koln_card_einzelkarte_24h"] is True
    assert verified_by_id["koln_card_gruppenkarte_48h"] is True
    assert verified_by_id["koln_card_einzelkarte_48h"] is False
    assert verified_by_id["koln_card_gruppenkarte_24h"] is False
    assert not koln_card.custom_discounts

    warsaw_card = cards_by_id["warsaw_pass"]
    assert all(not v.price_verified for v in warsaw_card.variants)
    assert not warsaw_card.custom_discounts


# --- Regresje po audycie PR #52 (2026-10-11) ---


def _attr(**kw):
    base = dict(
        id="x", name="X", city="berlin", category=AttractionCategory.CULTURE,
        description="d", normal_price=10.0, currency="EUR",
    )
    base.update(kw)
    return Attraction(**base)


def test_child_price_without_max_age_never_applies_to_adults():
    a = _attr(child_price=GroupPrice(price=5.0, label="Kinder"))
    assert best_price_for_attraction(a, DiscountProfile(age=35))[0] == 10.0
    assert best_price_for_attraction(a, DiscountProfile(age=8))[0] == 10.0


def test_all_child_prices_have_max_age():
    for a in get_all_attractions():
        if a.child_price is not None:
            assert a.child_price.max_age is not None, a.id


def test_student_price_respects_age_bounds_and_countries():
    gp = GroupPrice(price=1.0, label="uczący się", min_age=7, max_age=26, recognized_countries=["PL"])
    a = _attr(student_price=gp)
    assert best_price_for_attraction(a, DiscountProfile(age=30, is_student=True))[0] == 10.0
    # sama flaga bez dokumentu z PL nie wystarcza przy ograniczeniu krajowym
    assert best_price_for_attraction(a, DiscountProfile(age=20, is_student=True))[0] == 10.0
    de = DiscountProfile(age=20, documents=[HeldDocument("legitymacja_studencka", "DE")])
    assert best_price_for_attraction(a, de)[0] == 10.0
    pl = DiscountProfile(age=20, documents=[HeldDocument("legitymacja_studencka", "PL")])
    assert best_price_for_attraction(a, pl)[0] == 1.0
    pl30 = DiscountProfile(age=30, documents=[HeldDocument("legitymacja_studencka", "PL")])
    assert best_price_for_attraction(a, pl30)[0] == 10.0


def test_student_flag_still_works_without_restrictions():
    a = _attr(student_price=GroupPrice(price=6.0, label="Student"))
    assert best_price_for_attraction(a, DiscountProfile(age=30, is_student=True))[0] == 6.0


def test_card_without_transit_does_not_count_transit_as_savings():
    from attractions import CityCardVariant
    from attractions.service import evaluate_city_card_variant

    card = get_all_city_cards()[0]
    v = CityCardVariant("v", "V", 24, 10.0, "EUR", False, "-", "d")
    atts = [_attr(normal_price=20.0)]
    n0 = evaluate_city_card_variant(card, v, atts, 0.0).net_savings
    n30 = evaluate_city_card_variant(card, v, atts, 30.0).net_savings
    assert n0 == n30
    vt = CityCardVariant("v", "V", 24, 10.0, "EUR", True, "AB", "d")
    assert evaluate_city_card_variant(card, vt, atts, 30.0).net_savings == (
        evaluate_city_card_variant(card, vt, atts, 0.0).net_savings + 30.0
    )


def test_card_in_eur_is_converted_for_pln_attractions():
    from attractions import CityCardVariant
    from attractions.service import evaluate_city_card_variant
    from routing.currency import convert

    card = get_all_city_cards()[0]
    v = CityCardVariant("v", "V", 24, 10.0, "EUR", False, "-", "d")
    a = _attr(normal_price=100.0, currency="PLN", default_card_discount_percent=0.0)
    ev = evaluate_city_card_variant(card, v, [a], 0.0)
    assert ev.currency == "PLN"
    assert ev.card_price == round(convert(10.0, "EUR", "PLN"), 2)
    assert ev.total_cost_with_card == round(convert(10.0, "EUR", "PLN") + ev.attractions_price_with_card, 2)


def test_audit_pr52_data_fixes():
    A = {a.id: a for a in get_all_attractions()}
    adult = DiscountProfile(age=35)
    for i in ("hamburg_st_michaelis", "hamburg_speicherstadtmuseum", "munchen_skylift_olympiapark", "koln_odysseum"):
        assert best_price_for_attraction(A[i], adult)[0] == A[i].normal_price
    assert best_price_for_attraction(A["koln_odysseum"], DiscountProfile(age=10))[0] == 16.0
    # Powstanie: operator (bilety.1944.pl/cennik.html) podaje normalny 35 / ulgowy 30 PLN;
    # cena studencka 1 PLN i rodzinna 95 PLN nie mają potwierdzenia i zostały usunięte
    p = A["warszawa_muzeum_powstania"]
    assert p.normal_price == 35.0
    assert p.student_price is None and p.family_price is None
    pl = DiscountProfile(age=20, documents=[HeldDocument("legitymacja_studencka", "PL")])
    assert best_price_for_attraction(p, pl)[0] != 1.0
    # weryfikacja 2026-10-11: Museum Ludwig 15,40 EUR, nie 10 EUR; niepotwierdzone ceny oznaczone
    assert A["koln_museum_ludwig"].normal_price == 15.4
    # BMW Museum (17 EUR) i Ogrod Botaniczny Wroclaw (30 zl) potwierdzone u operatora 2026-10-11;
    # Wallraf-Richartz zamkniety do konca 2028 - cena niepotwierdzona
    assert A["munchen_bmw_museum"].price_verified is True
    assert A["wroclaw_ogrod_botaniczny"].price_verified is True
    assert A["koln_wallraf_richartz"].price_verified is False
    # Filmstadt: brak ceny studenckiej, jest senioralna 60+
    f = A["munchen_bavaria_filmstadt"]
    assert f.student_price is None and f.senior_price.min_age == 60
    assert best_price_for_attraction(f, DiscountProfile(age=22, is_student=True))[0] == f.normal_price
    assert best_price_for_attraction(A["munchen_botanischer_garten"], DiscountProfile(age=17))[0] == 0.0
    assert best_price_for_attraction(A["munchen_botanischer_garten"], DiscountProfile(age=18))[0] != 0.0


def _by_id(attr_id):
    return next(a for a in get_all_attractions() if a.id == attr_id)


def test_zmienne_ceny_flagi_dla_zollverein_fernsehturm_zoo():
    assert _by_id("essen_zeche_zollverein").price_is_from
    assert not _by_id("essen_zeche_zollverein").dynamic_pricing
    for aid in ("berlin_fernsehturm", "koln_zoo"):
        a = _by_id(aid)
        assert a.price_is_from and a.dynamic_pricing
        assert "ulgi możliwe" in a.variable_pricing_note or "ulgi" in a.variable_pricing_note


def test_ceny_dynamiczne_nie_zgaduja_ulg():
    a = _by_id("berlin_fernsehturm")
    assert a.child_price is not None  # dane zostają, ale kalkulator ich nie używa
    price, label, source = best_price_for_attraction(a, DiscountProfile(age=8, is_student=True))
    assert price == a.normal_price and source is None


def test_cena_od_bez_dynamiki_nadal_stosuje_potwierdzona_ulge():
    a = _by_id("essen_zeche_zollverein")
    price, _label, source = best_price_for_attraction(a, DiscountProfile(is_student=True))
    assert price == 9.5 and source is not None


def test_price_from_note_pusta_dla_stalej_ceny_i_api_zwraca_pola():
    from attractions import price_from_note

    assert price_from_note(_by_id("krakow_wawel")) == ""
    assert price_from_note(_by_id("koln_zoo"))
    from fastapi.testclient import TestClient
    from api.main import app

    items = TestClient(app).get("/attractions", params={"city": "berlin"}).json()
    ft = next(i for i in items if i["id"] == "berlin_fernsehturm")
    assert ft["price_is_from"] is True and ft["dynamic_pricing"] is True


def test_zamkniete_muzeum_nie_trafia_do_wynikow():
    from datetime import date

    from attractions import get_all_attractions, get_attractions
    from attractions.service import is_closed

    wallraf = next(a for a in get_all_attractions() if a.id == "koln_wallraf_richartz")
    assert wallraf.closed_until == "2028-12-31" and wallraf.closed_source_url
    assert is_closed(wallraf, today=date(2026, 10, 11))
    assert not is_closed(wallraf, today=date(2029, 1, 1))
    assert "koln_wallraf_richartz" not in {a.id for a in get_attractions(city="koln")}
    assert "koln_wallraf_richartz" in {a.id for a in get_attractions(city="koln", include_closed=True)}
    # pozostałe muzea bez flagi zachowują się jak dotąd
    assert "koln_museum_ludwig" in {a.id for a in get_attractions(city="koln")}


# --- Brak zgadywania zniżek kart (zasada źródeł z CONTRIBUTING.md) ---------------------------


def _card(card_id):
    return next(c for c in get_all_city_cards() if c.id == card_id)


def _card_discount_percent(card_id, attraction_id):
    """Zniżka karty na atrakcję wyliczona przez kalkulator, jako % (z cen przed/po karcie)."""
    from attractions.service import evaluate_city_card_variant

    card = _card(card_id)
    attraction = next(a for a in get_all_attractions() if a.id == attraction_id)
    ev = evaluate_city_card_variant(card, card.variants[0], [attraction])
    without, with_card = ev.attractions_price_without_card, ev.attractions_price_with_card
    return round(100.0 * (without - with_card) / without, 2)


def test_karty_nie_maja_domyslnego_rabatu_calej_karty():
    """Wcześniej atrakcja bez wpisu dostawała card.default_discount_percent (Kraków Card: 100%,
    Berlin WelcomeCard: 25%) — czyste zgadywanie. Pole nie istnieje ani w modelu, ani w danych."""
    import json
    from pathlib import Path

    import attractions

    raw = json.loads(
        (Path(attractions.__file__).parent / "data" / "city_cards.json").read_text(encoding="utf-8")
    )
    for card in raw["karty"]:
        assert "default_discount_percent" not in card, card["id"]
    for card in get_all_city_cards():
        assert not hasattr(card, "default_discount_percent"), card.id


def test_krakow_card_nie_daje_100_procent_na_katedre_wawelska():
    # Katedra Wawelska nie jest w custom_discounts; zniżka Kraków Card nie jest potwierdzona
    # u źródła (verification/zestawienie-atrakcje-karty-2026-10-10.md) -> 0%, nie 100%.
    assert _card_discount_percent("krakow_card", "krakow_katedra_wawelska") == 0.0


def test_berlin_welcomecard_nie_daje_25_procent_bez_zrodla_na_curry36_i_alte_foersterei():
    assert _card_discount_percent("berlin_welcomecard", "berlin_curry36") == 0.0
    assert _card_discount_percent("berlin_welcomecard", "berlin_alte_foersterei") == 0.0


def test_zniszki_ze_zrodlem_dzialaja_jak_dotad():
    # RUHR.TOPCARD: źródło (ruhrtopcard.de/alle-ausflugsziele, 2026-10-09) jest w polach
    # custom_discount_sources -> zniżki bez zmian.
    assert _card_discount_percent("ruhrtopcard", "essen_zeche_zollverein") == 100.0
    assert _card_discount_percent("ruhrtopcard", "gelsenkirchen_veltins_arena") == 50.0
    assert _card_discount_percent("ruhrtopcard", "dortmund_signal_iduna_park") == 50.0
    assert _card_discount_percent("ruhrtopcard", "dortmund_fussballmuseum") == 50.0


def test_zoom_nie_jest_partnerem_ruhrtopcard_wiec_bez_zniszki():
    # katalog partnerów RUHR.TOPCARD (city_cards.json::_UWAGA_partnerzy) nie zawiera ZOOM
    assert _card_discount_percent("ruhrtopcard", "gelsenkirchen_zoom_erlebniswelt") == 0.0


def test_atrakcja_bez_wpisu_nie_dostaje_zniszki_na_zadnej_karcie():
    from attractions import CityCardVariant
    from attractions.service import evaluate_city_card_variant

    variant = CityCardVariant("v", "V", 24, 10.0, "EUR", False, "-", "d")
    for card in get_all_city_cards():
        attr = _attr(id="atrakcja_spoza_katalogu", normal_price=40.0)
        ev = evaluate_city_card_variant(card, variant, [attr])
        assert ev.attractions_price_with_card == ev.attractions_price_without_card == 40.0, card.id


def test_kazda_zapisana_zniszka_karty_wskazuje_atrakcje_z_tego_samego_miasta():
    by_id = {a.id: a for a in get_all_attractions()}
    for card in get_all_city_cards():
        for attraction_id, percent in card.custom_discounts.items():
            assert 0.0 <= percent <= 100.0, (card.id, attraction_id)
            assert by_id[attraction_id].city == card.city, (card.id, attraction_id)


def test_brak_zapisanej_znizki_karty_jest_zerem_z_flaga_niezweryfikowane():
    from attractions.service import evaluate_city_cards, get_attractions

    attr = next(a for a in get_attractions(city="krakow") if a.id == "krakow_katedra_wawelska")
    evals = evaluate_city_cards("krakow", [attr])
    assert evals
    for ev in evals:
        assert ev.attractions_price_with_card == ev.attractions_price_without_card
        assert "krakow_katedra_wawelska" in ev.unverified_discount_attraction_ids
        assert "niezweryfikowane" in ev.summary


def test_komunikat_waluty_nie_mowi_o_placeholderze():
    import pytest
    from common.currency import UnsupportedCurrencyError, normalize_currency

    with pytest.raises(UnsupportedCurrencyError) as exc:
        normalize_currency("GBP")
    assert "PLACEHOLDER" not in str(exc.value)
    assert "EUR" in str(exc.value)
