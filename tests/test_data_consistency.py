"""Testy spójności plików danych (atrakcje, karty miejskie, taryfy).

Pilnują reguł, których wcześniej nic nie egzekwowało, a których złamanie dawało
cichy, błędny wynik dla użytkownika (cena dziecięca bez granicy wieku, mieszanie
walut, cena bez źródła, karta bez potwierdzonego istnienia). Działają wyłącznie
na plikach JSON i kodzie — bez MOTIS i bez sieci.
"""

import json
import re
from pathlib import Path

import pytest

from attractions.service import (
    evaluate_city_cards,
    get_all_attractions,
    get_all_city_cards,
    get_attractions,
    get_city_cards,
)

ROOT = Path(__file__).resolve().parent.parent
ATTRACTIONS_JSON = ROOT / "attractions" / "data" / "attractions.json"
CARDS_JSON = ROOT / "attractions" / "data" / "city_cards.json"
FARE_FILES = sorted((ROOT / "fares" / "data").glob("*.json"))

CURRENCIES = {"PLN", "EUR"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GROUPS = ("child_price", "student_price", "senior_price", "family_price")


# Istniejące rekordy, w których warunek (wiek/status) jest zapisany tylko w tekście `label`, a nie w
# polach strukturalnych min_age/max_age/requires_status. To znany dług z PR #52: uzupełnienie
# wymaga sprawdzenia warunku u źródła dla każdej atrakcji (nie zgadujemy). NOWE rekordy muszą
# mieć pola strukturalne; wpis znika z listy, gdy rekord zostanie uzupełniony (test pilnuje).
KNOWN_UNSTRUCTURED_CONDITIONS = {
    "berlin_olympiastadion.family_price",
    "berlin_alte_foersterei.family_price",
    "warszawa_pge_narodowy.family_price",
    "warszawa_muzeum_powstania.senior_price",
    "hamburg_st_michaelis.student_price",
    "hamburg_st_michaelis.family_price",
    "hamburg_speicherstadtmuseum.student_price",
    "hamburg_imm.student_price",
    "hamburg_imm.family_price",
    "hamburg_elbphilharmonie_plaza.student_price",
    "hamburg_hagenbeck.family_price",
    "hamburg_miniatur_wunderland.student_price",
    "munchen_fcbayern_erlebniswelt.student_price",
    "munchen_fcbayern_erlebniswelt.family_price",
    "munchen_deutsches_museum.student_price",
    "munchen_deutsches_museum.family_price",
    "munchen_residenz.student_price",
    "munchen_schloss_nymphenburg.student_price",
    "munchen_frauenkirche.student_price",
    "munchen_frauenkirche.family_price",
    "munchen_skylift_olympiapark.student_price",
    "munchen_skylift_olympiapark.senior_price",
    "munchen_hellabrunn.student_price",
    "munchen_hellabrunn.family_price",
    "munchen_hellabrunn.senior_price",
    "munchen_bier_oktoberfest_museum.student_price",
    "munchen_botanischer_garten.student_price",
    "koln_rheinenergiestadion.student_price",
    "koln_dom.student_price",
    "koln_triangle.student_price",
    "koln_schokoladenmuseum.student_price",
    "koln_schokoladenmuseum.family_price",
    "koln_schokoladenmuseum.senior_price",
    "wroclaw_panorama_raclawicka.student_price",
    "wroclaw_panorama_raclawicka.family_price",
    "wroclaw_hydropolis.student_price",
    "wroclaw_hydropolis.family_price",
    "poznan_termy_maltanskie.student_price",
    "poznan_termy_maltanskie.family_price",
    "poznan_brama_poznania.student_price",
    "poznan_brama_poznania.family_price",
    "poznan_nowe_zoo.student_price",
    "poznan_nowe_zoo.family_price",
    "poznan_fotoplastykon.student_price",
    "poznan_fotoplastykon.family_price",
    "poznan_rogalowe_muzeum.student_price",
    "poznan_palmiarnia.student_price",
}

# Płatne atrakcje oznaczone price_verified bez official_url — cena jest "potwierdzona", ale nie da
# się jej zweryfikować po URL. Realny, istniejący brak: trzeba dopisać źródło albo ustawić
# price_verified:false. Nowych takich rekordów nie wolno dodawać.
KNOWN_VERIFIED_WITHOUT_URL: set[str] = set()

# Pliki taryf, w których URL źródła nie jest zapisany w polu `_zrodlo*` (znane braki, do uzupełnienia).
KNOWN_FARE_FILES_WITHOUT_URL = {
    "flixbus_fallback.json",  # wciąż bez URL operatora: zgrubny fallback, nie cennik
    "bilet_graniczny_zasieki_forst.json",  # regulamin PDF odczytany, URL pliku do uzupełnienia
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


ATTRACTIONS = _load(ATTRACTIONS_JSON)["atrakcje"]
CARDS = _load(CARDS_JSON)["karty"]


def _ids(items):
    return [i["id"] for i in items]


# --- Atrakcje ---------------------------------------------------------------


def test_attraction_ids_unique():
    ids = _ids(ATTRACTIONS)
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("a", ATTRACTIONS, ids=_ids(ATTRACTIONS))
def test_attraction_base_price_and_currency(a):
    assert a["currency"] in CURRENCIES
    assert a["normal_price"] >= 0
    # cena bez potwierdzenia musi być jawnie oznaczona, a potwierdzona ma mieć URL
    if a.get("price_verified") and a["normal_price"] > 0:
        has_url = a.get("official_url", "").startswith("http")
        if a["id"] in KNOWN_VERIFIED_WITHOUT_URL:
            assert not has_url, "ma już official_url — usuń z KNOWN_VERIFIED_WITHOUT_URL"
        else:
            assert has_url, "price_verified bez official_url"


@pytest.mark.parametrize("a", ATTRACTIONS, ids=_ids(ATTRACTIONS))
@pytest.mark.parametrize("group", GROUPS)
def test_discount_price_has_conditions_and_source(a, group):
    gp = a.get(group)
    if gp is None:
        return
    where = f"{a['id']}.{group}"
    assert isinstance(gp["price"], (int, float)) and gp["price"] >= 0, where
    assert gp.get("label"), f"{where}: brak label"
    has_age = gp.get("min_age") is not None or gp.get("max_age") is not None
    has_status = bool(gp.get("requires_status"))
    structured = group != "child_price" and (has_age or has_status)
    key = f"{a['id']}.{group}"
    if key in KNOWN_UNSTRUCTURED_CONDITIONS:
        assert (
            not structured
        ), f"{key} jest już uzupełnione — usuń wpis z KNOWN_UNSTRUCTURED_CONDITIONS"
    elif group == "child_price":
        assert has_age, f"{where}: cena dziecięca bez granicy wieku"
    elif group == "senior_price":
        assert has_age or has_status, f"{where}: senior bez wieku/statusu"
    elif group == "student_price":
        assert has_status or has_age, f"{where}: student bez statusu/wieku"
    else:  # family
        assert has_status or has_age, f"{where}: rodzinna bez warunku"
    if gp.get("min_age") is not None and gp.get("max_age") is not None:
        assert gp["min_age"] <= gp["max_age"], where
    # cena ulgowa jednej osoby nie przekracza normalnej (rodzinna to cena za całą rodzinę)
    if group != "family_price" and a.get("price_verified"):
        assert gp["price"] <= a["normal_price"], f"{where}: ulgowa droższa od normalnej"
    if gp.get("price_verified"):
        assert gp.get("source_url", "").startswith("http"), f"{where}: brak source_url"
        assert ISO_DATE.match(gp.get("verified_date", "")), f"{where}: brak/zła verified_date"


# --- Karty miejskie ---------------------------------------------------------


def test_city_card_ids_unique():
    ids = _ids(CARDS)
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("c", CARDS, ids=_ids(CARDS))
def test_card_existence_fields(c):
    if c.get("existence_verified"):
        assert c.get("existence_source_url", "").startswith("http"), "brak URL istnienia"
        assert ISO_DATE.match(c.get("existence_verified_date", "")), "brak daty istnienia"


@pytest.mark.parametrize("c", CARDS, ids=_ids(CARDS))
def test_card_variants_currency_and_prices(c):
    assert c["variants"], "karta bez wariantów"
    for v in c["variants"]:
        assert v["currency"] in CURRENCIES, v["id"]
        assert v["price"] > 0, v["id"]


def test_unverified_cards_never_returned():
    unverified = {c["id"] for c in CARDS if not c.get("existence_verified")}
    returned = {c.id for c in get_city_cards()}
    assert not (unverified & returned)
    assert {c.id for c in get_all_city_cards() if not c.existence_verified} <= unverified


def test_custom_discounts_reference_existing_attractions():
    known = set(_ids(ATTRACTIONS))
    for c in CARDS:
        for aid in c.get("custom_discounts", {}):
            assert aid in known, f"{c['id']}: custom_discounts wskazuje nieistniejącą {aid}"


@pytest.mark.parametrize("city", sorted({a["city"] for a in ATTRACTIONS}))
def test_evaluation_single_currency_and_consistent(city):
    """Atrakcje i karty w różnych walutach: wynik ma jedną walutę i sumuje się poprawnie."""
    attractions = get_attractions(city=city)
    for ev in evaluate_city_cards(city, attractions, estimated_transit_cost=10.0):
        assert ev.currency in CURRENCIES
        assert ev.total_cost_without_card - ev.total_cost_with_card == pytest.approx(
            ev.net_savings, abs=0.02
        )
        # koszt transportu bez zwolnienia w cenie karty nie może być liczony jako oszczędność
        if not ev.variant.includes_public_transit:
            assert ev.estimated_transit_savings == 0


def test_mixed_currency_evaluation_converts_card_price():
    """Karta w EUR i atrakcje w PLN (lub odwrotnie) nie mogą być po prostu dodane."""
    for card in get_all_city_cards():
        attractions = [a for a in get_all_attractions() if a.city == card.city]
        for v in card.variants:
            other = "PLN" if v.currency == "EUR" else "EUR"
            foreign = [a for a in attractions if a.currency == other]
            if not foreign:
                continue
            ev = evaluate_city_cards(card.city, foreign, 0.0)
            assert all(e.currency == other for e in ev)
            # 1 EUR > 1 PLN: cena karty w walucie rozliczenia nie może być równa nominałowi
            match = [e for e in ev if e.variant.id == v.id]
            assert match and match[0].card_price != pytest.approx(v.price)
            return
    pytest.skip("brak miasta z mieszanymi walutami w danych")


# --- Taryfy -----------------------------------------------------------------


@pytest.mark.parametrize("path", FARE_FILES, ids=[p.name for p in FARE_FILES])
def test_fare_file_has_source_and_single_currency(path):
    data = _load(path)
    if "waluta" in data:
        assert data["waluta"] in CURRENCIES
    source_keys = [k for k in data if k.startswith("_zrodlo") or k == "source"]
    text = " ".join(str(data[k]) for k in source_keys)
    if path.name in KNOWN_FARE_FILES_WITHOUT_URL:
        assert "http" not in text, f"{path.name} ma już URL — usuń z KNOWN_FARE_FILES_WITHOUT_URL"
    else:
        assert "http" in text, f"{path.name}: brak URL źródła"


@pytest.mark.parametrize("path", FARE_FILES, ids=[p.name for p in FARE_FILES])
def test_fare_file_dated_and_discount_not_above_full(path):
    data = _load(path)
    if "as_of" in data:
        assert ISO_DATE.match(str(data["as_of"])), f"{path.name}: zła as_of"
    for t in data.get("bilety_czasowe", []):
        if "normalny" in t and "ulgowy" in t:
            assert t["ulgowy"] <= t["normalny"], f"{path.name}: ulgowy > normalny: {t}"
