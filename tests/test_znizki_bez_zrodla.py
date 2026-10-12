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

# atrakcja -> zniżka sprzed zerowania 2026-10-12 (żadna nie miała pola źródła)
WYZEROWANE = {
    "berlin_museumsinsel": 25.0,
    "berlin_fernsehturm": 25.0,
    "berlin_olympiastadion": 25.0,
    "krakow_wawel": 20.0,
    "krakow_schindler_factory": 20.0,
    "hamburg_speicherstadtmuseum": 25.0,
    "hamburg_imm": 22.0,
    "munchen_fcbayern_erlebniswelt": 8.0,
    "munchen_residenz": 13.3,
    "munchen_schloss_nymphenburg": 10.0,
    "munchen_frauenkirche": 33.3,
    "munchen_sealife": 20.0,
    "munchen_bavaria_filmstadt": 10.0,
    "poznan_brama_poznania": 40.0,
    "poznan_fotoplastykon": 100.0,
    "lublin_zamek_muzeum": 20.0,
}


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


def test_dane_wyzerowane_zniezki_licza_sie_jako_zero_z_flaga():
    cards = {c.id: c for c in get_all_city_cards() if c.city in MIASTA_ZEROWANIE}
    by_id = {a.id: a for a in get_all_attractions()}
    for aid in WYZEROWANE:
        attr = by_id[aid]
        cards_city = [c for c in cards.values() if c.city == attr.city]
        assert cards_city, aid
        for card in cards_city:
            ev = evaluate_city_card_variant(card, card.variants[0], [attr])
            assert ev.attractions_price_with_card == ev.attractions_price_without_card, (
                card.id,
                aid,
            )
            assert aid in ev.unverified_discount_attraction_ids, (card.id, aid)


def test_dane_stara_wartosc_wyzerowanej_znizki_zostaje_w_notatce():
    raw_cards = json.loads((DATA / "city_cards.json").read_text(encoding="utf-8"))["karty"]
    zapisane = {}
    for card in raw_cards:
        for aid, info in card.get("_zerowane_znizki_bez_zrodla_2026_10_12", {}).items():
            zapisane[aid] = info["stara_znizka_proc"]
    custom_only = {aid: v for aid, v in WYZEROWANE.items() if aid != "lublin_zamek_muzeum"}
    assert zapisane == custom_only
    raw_attr = {
        a["id"]: a
        for a in json.loads((DATA / "attractions.json").read_text(encoding="utf-8"))["atrakcje"]
    }
    for aid in ("lublin_zamek_muzeum", "krakow_wawel", "berlin_fernsehturm"):
        assert raw_attr[aid]["default_card_discount_percent"] == 0.0
        assert "bez pola źródła" in raw_attr[aid]["_UWAGA_zniezka_karty"]


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


def test_bvg_zrodlo_strefy_c_ber_nie_jest_wymyslone():
    """Pole może być puste (URL-i nie podano), ale wpisane musi być prawdziwym adresem https
    z domeny vbb.de / bvg.de i mieć datę YYYY-MM-DD."""
    zrodlo = load("bvg_berlin.json")["zrodlo_strefa_c_ber"]
    for pole, domena in (("vbb_url", "vbb.de"), ("bvg_url", "bvg.de")):
        url = zrodlo[pole]
        if url:
            assert re.fullmatch(rf"https://([a-z0-9-]+\.)*{re.escape(domena)}(/\S*)?", url), (
                pole,
                url,
            )
    if zrodlo["vbb_url"] or zrodlo["bvg_url"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", zrodlo["data_weryfikacji"])
    else:
        assert zrodlo["data_weryfikacji"] == ""
