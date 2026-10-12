"""Zniżki kart miejskich: bez pola źródła (source_url + data weryfikacji) = 0% + flaga
niezweryfikowanej zniżki; ze źródłem = bez zmian. Plus pole źródła strefy C (BER) w taryfie BVG."""

import json
import re
from pathlib import Path

import pytest

import attractions
from attractions import (
    Attraction,
    AttractionCategory,
    CityCard,
    CityCardVariant,
    DiscountSource,
    get_all_attractions,
    get_all_city_cards,
)
from attractions.service import evaluate_city_card_variant
from fares._data_loading import load

DATA = Path(attractions.__file__).parent / "data"
ZRODLO = DiscountSource("https://example.test/partnerzy", "2026-10-12")


def _attr(attr_id="a_test", default=0.0, source=None):
    return Attraction(
        id=attr_id,
        name=attr_id,
        city="testowo",
        category=AttractionCategory.CULTURE,
        description="",
        normal_price=100.0,
        currency="EUR",
        default_card_discount_percent=default,
        card_discount_source=source,
    )


def _card(custom=None, sources=None):
    variant = CityCardVariant("v", "V", 24, 10.0, "EUR", False, "-", "d")
    return CityCard(
        id="karta_test",
        city="testowo",
        name="Karta",
        description="",
        official_url="https://example.test",
        variants=[variant],
        custom_discounts=custom or {},
        custom_discount_sources=sources or {},
    )


def _eval(card, attr):
    ev = evaluate_city_card_variant(card, card.variants[0], [attr])
    return ev.attractions_price_with_card, ev


# --- custom_discounts karty ---


def test_znizka_karty_bez_zrodla_to_zero_procent_i_flaga():
    price, ev = _eval(_card(custom={"a_test": 25.0}), _attr())
    assert price == 100.0
    assert ev.unverified_discount_attraction_ids == ["a_test"]
    assert "niezweryfikowane" in ev.summary


@pytest.mark.parametrize(
    "zrodlo",
    [
        DiscountSource("", "2026-10-12"),
        DiscountSource("https://example.test", ""),
        DiscountSource(" ", " "),
    ],
)
def test_niekompletne_zrodlo_znizki_to_zero_procent_i_flaga(zrodlo):
    price, ev = _eval(_card(custom={"a_test": 25.0}, sources={"a_test": zrodlo}), _attr())
    assert price == 100.0
    assert ev.unverified_discount_attraction_ids == ["a_test"]


def test_znizka_karty_ze_zrodlem_bez_zmian():
    price, ev = _eval(_card(custom={"a_test": 25.0}, sources={"a_test": ZRODLO}), _attr())
    assert price == 75.0
    assert ev.unverified_discount_attraction_ids == []
    assert "niezweryfikowane" not in ev.summary


def test_jawne_zero_w_custom_discounts_to_znany_brak_znizki_bez_flagi():
    price, ev = _eval(_card(custom={"a_test": 0.0}), _attr())
    assert price == 100.0
    assert ev.unverified_discount_attraction_ids == []


# --- default_card_discount_percent atrakcji ---


def test_domyslna_znizka_atrakcji_bez_zrodla_to_zero_procent_i_flaga():
    price, ev = _eval(_card(), _attr(default=20.0))
    assert price == 100.0
    assert ev.unverified_discount_attraction_ids == ["a_test"]


def test_domyslna_znizka_atrakcji_ze_zrodlem_bez_zmian():
    price, ev = _eval(_card(), _attr(default=20.0, source=ZRODLO))
    assert price == 80.0
    assert ev.unverified_discount_attraction_ids == []


# --- dane w repo ---

MIASTA_ZEROWANIE = {"berlin", "krakow", "hamburg", "munchen", "poznan", "lublin"}

DATA_ZRODEL = "2026-10-12"

# Zniżki wyzerowane w #101 i przywrócone ze źródłem wg raportu research/zrodla-znizek-kart.md
# (źródło wg Gemini, niezweryfikowane niezależnie): atrakcja -> (karta, zniżka %, domena URL).
PRZYWROCONE = {
    "berlin_fernsehturm": ("berlin_welcomecard", 25.0, "berlin-welcomecard.de"),
    "berlin_olympiastadion": ("berlin_welcomecard", 22.7, "berlin-welcomecard.de"),  # 8,50 z 11,00 EUR
    "hamburg_speicherstadtmuseum": ("hamburg_card", 25.0, "speicherstadtmuseum.de"),
    "munchen_fcbayern_erlebniswelt": ("munchen_citytourcard", 8.0, "citytourcard-muenchen.com"),
    "munchen_residenz": ("munchen_citytourcard", 13.3, "citytourcard-muenchen.com"),
    "munchen_frauenkirche": ("munchen_citytourcard", 33.3, "citytourcard-muenchen.com"),
    "munchen_sealife": ("munchen_citytourcard", 20.0, "citytourcard-muenchen.com"),
    "munchen_bavaria_filmstadt": ("munchen_citytourcard", 10.0, "citytourcard-muenchen.com"),
    "poznan_brama_poznania": ("poznan_city_card", 40.0, "karta.visitpoznan.pl"),
    "poznan_fotoplastykon": ("poznan_city_card", 100.0, "karta.visitpoznan.pl"),
}

# Nadal 0% z flagą niezweryfikowanej zniżki: brak źródła albo nieprzeliczalne na %.
NADAL_ZERO_Z_FLAGA = {
    "berlin_museumsinsel": 25.0,  # Classic: raport nie potwierdza zniżki
    "munchen_schloss_nymphenburg": 10.0,  # cena bazowa (20 EUR) != cena z raportu (10 EUR)
    "lublin_zamek_muzeum": 20.0,  # brak źródła
    "hamburg_imm": 22.0,  # cena bazowa w danych (17 EUR) != cennik (18 EUR)
    "krakow_schindler_factory": 20.0,  # źródło opisuje inny produkt (Krakowska Karta Turystyczna)
}

# Wawel: źródło (krakow.travel) mówi, że Kraków Card go nie obejmuje -> jawne 0%, bez flagi.
WAWEL_ZRODLO = "https://krakow.travel/artykul/155/krakowska-karta-turystyczna"


def test_dane_kazda_zniezka_wieksza_od_zera_ma_kompletne_zrodlo():
    for card in get_all_city_cards():
        for aid, pct in card.custom_discounts.items():
            if pct > 0:
                src = card.custom_discount_sources.get(aid)
                assert src is not None and src.is_complete, (card.id, aid)
    for a in get_all_attractions():
        if a.default_card_discount_percent > 0:
            assert a.card_discount_source is not None and a.card_discount_source.is_complete, a.id


def test_dane_zrodla_nie_wskazuja_zniezek_ktorych_nie_ma():
    for card in get_all_city_cards():
        assert set(card.custom_discount_sources) <= set(card.custom_discounts), card.id


def _karty():
    return {c.id: c for c in get_all_city_cards()}


def _atrakcje():
    return {a.id: a for a in get_all_attractions()}


def test_dane_przywrocone_znizki_maja_zrodlo_url_i_date_z_raportu():
    karty = _karty()
    for aid, (card_id, pct, domena) in PRZYWROCONE.items():
        card = karty[card_id]
        assert card.custom_discounts[aid] == pct, aid
        src = card.custom_discount_sources[aid]
        assert src.is_complete, aid
        assert re.fullmatch(rf"https://([a-z0-9-]+\.)*{re.escape(domena)}/\S+", src.source_url), (
            aid,
            src.source_url,
        )
        assert src.verified_date == DATA_ZRODEL, aid


def test_dane_przywrocone_znizki_licza_sie_bez_flagi():
    karty, atrakcje = _karty(), _atrakcje()
    for aid, (card_id, pct, _) in PRZYWROCONE.items():
        card, attr = karty[card_id], atrakcje[aid]
        # pomijamy wariant specjalny Museumsinsel (nie dotyczy tych atrakcji)
        ev = evaluate_city_card_variant(card, card.variants[0], [attr])
        assert ev.unverified_discount_attraction_ids == [], aid
        assert ev.attractions_price_with_card == pytest.approx(
            attr.normal_price * (1 - pct / 100), abs=0.01
        ), aid


def test_dane_nadal_zerowane_zniezki_licza_sie_jako_zero_z_flaga():
    karty, atrakcje = _karty(), _atrakcje()
    for aid in NADAL_ZERO_Z_FLAGA:
        attr = atrakcje[aid]
        cards_city = [c for c in karty.values() if c.city == attr.city]
        assert cards_city, aid
        for card in cards_city:
            ev = evaluate_city_card_variant(card, card.variants[0], [attr])
            assert ev.attractions_price_with_card == ev.attractions_price_without_card, (
                card.id,
                aid,
            )
            assert aid in ev.unverified_discount_attraction_ids, (card.id, aid)


def test_dane_olympiastadion_procent_z_cen_zrodla_a_nie_deklarowane_25():
    card = _karty()["berlin_welcomecard"]
    attr = _atrakcje()["berlin_olympiastadion"]
    assert attr.normal_price == 11.0
    assert card.custom_discounts["berlin_olympiastadion"] == pytest.approx(
        (11.0 - 8.5) / 11.0 * 100, abs=0.05
    )
    variant = next(v for v in card.variants if v.id == "bwc_48h_ab")
    ev = evaluate_city_card_variant(card, variant, [attr])
    assert ev.attractions_price_with_card == pytest.approx(8.50, abs=0.01)


def test_dane_schindler_zero_z_flaga_we_wszystkich_wariantach_krakow_card():
    # Źródło opisuje Krakowską Kartę Turystyczną; nasz wpis to Krakow City Pass -> produkt
    # niepotwierdzony. Dotyczy też osobnego produktu krakow_museum_pass_student_3d.
    card = _karty()["krakow_card"]
    schindler = _atrakcje()["krakow_schindler_factory"]
    assert "krakow_schindler_factory" not in card.custom_discounts
    assert "krakow_museum_pass_student_3d" in {v.id for v in card.variants}
    for variant in card.variants:
        ev = evaluate_city_card_variant(card, variant, [schindler])
        assert ev.attractions_price_with_card == ev.attractions_price_without_card, variant.id
        assert ev.unverified_discount_attraction_ids == ["krakow_schindler_factory"], variant.id


def test_dane_imm_zero_z_flaga_do_uzgodnienia_ceny_bazowej():
    card = _karty()["hamburg_card"]
    imm = _atrakcje()["hamburg_imm"]
    assert imm.normal_price == 17.0  # cennik wg raportu: 18 EUR
    assert "hamburg_imm" not in card.custom_discounts
    ev = evaluate_city_card_variant(card, card.variants[0], [imm])
    assert ev.attractions_price_with_card == ev.attractions_price_without_card
    assert ev.unverified_discount_attraction_ids == ["hamburg_imm"]


def test_dane_wawel_jawne_zero_ze_zrodlem_bez_flagi():
    card = _karty()["krakow_card"]
    wawel = _atrakcje()["krakow_wawel"]
    assert card.custom_discounts["krakow_wawel"] == 0.0
    for variant in card.variants:
        ev = evaluate_city_card_variant(card, variant, [wawel])
        assert ev.attractions_price_with_card == ev.attractions_price_without_card
        assert ev.unverified_discount_attraction_ids == []
    raw = json.loads((DATA / "city_cards.json").read_text(encoding="utf-8"))["karty"]
    nota = next(c for c in raw if c["id"] == "krakow_card")["_zrodla_znizek_2026_10_12"]["krakow_wawel"]
    assert nota["url"] == WAWEL_ZRODLO
    assert "Nie obejmuje zwiedzania Wawelu" in nota["cytat"]
    assert "niezweryfikowane niezależnie" in nota["weryfikacja"]


def test_dane_stara_wartosc_nadal_zerowanej_znizki_zostaje_w_notatce():
    raw_cards = json.loads((DATA / "city_cards.json").read_text(encoding="utf-8"))["karty"]
    zapisane = {}
    for card in raw_cards:
        for aid, info in card.get("_zerowane_znizki_bez_zrodla_2026_10_12", {}).items():
            zapisane[aid] = info["stara_znizka_proc"]
    custom_only = {aid: v for aid, v in NADAL_ZERO_Z_FLAGA.items() if aid != "lublin_zamek_muzeum"}
    assert zapisane == custom_only
    raw_attr = {
        a["id"]: a
        for a in json.loads((DATA / "attractions.json").read_text(encoding="utf-8"))["atrakcje"]
    }
    assert raw_attr["lublin_zamek_muzeum"]["default_card_discount_percent"] == 0.0
    assert "bez pola źródła" in raw_attr["lublin_zamek_muzeum"]["_UWAGA_zniezka_karty"]


def test_dane_zrodla_znizek_oznaczone_jako_niezweryfikowane_niezaleznie():
    raw_cards = json.loads((DATA / "city_cards.json").read_text(encoding="utf-8"))["karty"]
    for card in raw_cards:
        for aid, nota in card.get("_zrodla_znizek_2026_10_12", {}).items():
            assert "niezweryfikowane niezależnie" in nota["weryfikacja"], aid


def test_dane_ruhr_topcard_zachowuje_znizki_ze_zrodlem():
    card = next(c for c in get_all_city_cards() if c.id == "ruhrtopcard")
    assert card.custom_discounts == {
        "gelsenkirchen_veltins_arena": 50.0,
        "essen_zeche_zollverein": 100.0,
        "dortmund_signal_iduna_park": 50.0,
        "dortmund_fussballmuseum": 50.0,
    }
    assert set(card.custom_discount_sources) == set(card.custom_discounts)
    for src in card.custom_discount_sources.values():
        assert src.source_url == "https://ruhrtopcard.de/alle-ausflugsziele"
        assert src.verified_date == "2026-10-09"


# --- strefa C (BER) w taryfie BVG ---


def test_bvg_pole_zrodla_strefy_c_ber_istnieje_a_ceny_bez_zmian():
    tabela = load("bvg_berlin.json")
    zrodlo = tabela["zrodlo_strefa_c_ber"]
    assert set(zrodlo) >= {"vbb_url", "bvg_url", "data_weryfikacji"}
    # ceny nietknięte
    ceny = {b["strefa"]: (b["normalny"], b["ulgowy"]) for b in tabela["bilety_czasowe"]}
    assert ceny == {"Kurzstrecke": (2.80, 2.10), "AB": (4.00, 2.50), "ABC": (5.00, 3.50)}


def test_bvg_zrodlo_strefy_c_ber_wpisane_z_domen_przewoznikow():
    """URL-e z raportu (vbb.de / bvg.de) wpisane, https z właściwej domeny, data YYYY-MM-DD."""
    zrodlo = load("bvg_berlin.json")["zrodlo_strefa_c_ber"]
    assert zrodlo["bvg_url"] == "https://www.bvg.de/de/touristen/verkehrsmittel-tarifbereiche"
    assert zrodlo["vbb_url"] == "https://www.vbb.de/tickets/einzelfahrausweise/"
    assert zrodlo["data_weryfikacji"] == "2026-10-12"
    for pole, domena in (("vbb_url", "vbb.de"), ("bvg_url", "bvg.de")):
        assert re.fullmatch(
            rf"https://([a-z0-9-]+\.)*{re.escape(domena)}(/\S*)?", zrodlo[pole]
        ), (pole, zrodlo[pole])
    for url in zrodlo["dodatkowe_url"]:
        assert re.fullmatch(r"https://www\.(bvg|vbb)\.de/\S+", url), url
    assert "niezweryfikowane niezależnie" in zrodlo["uwaga"]
