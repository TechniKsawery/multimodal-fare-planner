"""Ekran wyniku (etap 3): karty z trasą, pełna lista wszystkich wariantów z sortowaniem i filtrem,
widoczna sekcja pominiętych, wybór wariantu bez kasowania wyniku. Tylko prezentacja - ceny i taryfy
nie są ruszane."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import i18n
from i18n import LANGUAGES, t
from routing import motis_client, search_service
from routing.model import Itinerary, Leg, LegMode, PricedLeg, SkippedVariant
from routing.scoring import pick_recommendations
from ui_helpers import (
    carriers_summary,
    clear_place,
    duration_text,
    place_kind,
    rank_places,
    recommended_variant,
    route_summary,
    time_span,
    transfers_text,
    unique_places,
    variant_list,
)

ROOT = Path(__file__).resolve().parent.parent


def _leg(a, b, mode=LegMode.RAIL, carrier="PKP Intercity", dep=6, arr=8, day=18):
    return Leg(
        mode=mode,
        origin_name=a,
        destination_name=b,
        depart=datetime(2026, 10, day, dep, tzinfo=UTC),
        arrive=datetime(2026, 10, day, arr, tzinfo=UTC),
        carrier_name=carrier,
    )


def _priced(leg, amount, price_type="oficjalna_taryfa", **breakdown):
    return PricedLeg(leg, amount, "PLN", price_type, breakdown=breakdown)


def _it(name, *priced, transfers=0, minutes=None):
    first, last = priced[0].leg, priced[-1].leg
    return Itinerary(
        variant_name=name,
        legs=list(priced),
        total_price_pln=sum(p.amount for p in priced if p.price_known),
        total_duration_min=minutes or (last.arrive - first.depart).total_seconds() / 60,
        num_transfers=transfers,
    )


def _rail(name, amount, transfers=0, minutes=None, confirmed=True):
    leg = _priced(
        _leg("Lublin", "Gdańsk Główny"),
        amount,
        "oficjalna_taryfa" if confirmed else "szacunek",
        **({} if confirmed else {"price_verified": False}),
    )
    return _it(name, leg, transfers=transfers, minutes=minutes)


# --- helpery ---------------------------------------------------------------------------------------


def test_skrot_trasy_zwija_powtorzenia_i_pokazuje_przesiadki():
    it = _it(
        "x",
        _priced(_leg("Lublin", "Warszawa Wschodnia"), 30.0),
        _priced(_leg("Warszawa Wschodnia", "Gdańsk Główny", dep=9, arr=12), 67.0),
    )
    assert route_summary(it) == "Lublin → Warszawa Wschodnia → Gdańsk Główny"
    assert carriers_summary(it) == "PKP Intercity"
    assert time_span(it) == "06:00 → 12:00"


def test_przewoznicy_lub_rodzaj_transportu_bez_pieszych():
    it = _it(
        "x",
        _priced(_leg("A", "B", LegMode.WALK, carrier=""), 0.0),
        _priced(_leg("B", "C", LegMode.BUS, carrier=""), 10.0),
        _priced(_leg("C", "D", carrier="Polregio"), 10.0),
    )
    assert carriers_summary(it) == f"{i18n.t('mode.autobus')}, Polregio"


def test_przyjazd_nastepnego_dnia_ma_plus_dzien():
    it = _it(
        "x",
        _priced(_leg("A", "B", dep=22, arr=23), 1.0),
        _priced(_leg("B", "C", dep=23, arr=23, day=19), 1.0),
    )
    assert time_span(it).endswith("+1")


def test_lista_zawiera_wszystkie_warianty_i_sortuje():
    built = [
        _rail(f"w{i}", 100.0 - i, transfers=i % 3, minutes=60 + 10 * (7 - i)) for i in range(9)
    ]
    assert sorted(variant_list(built)) == list(range(9))
    assert variant_list(built, "price")[0] == 8
    assert variant_list(built, "time")[0] == 8
    assert variant_list(built, "transfers")[0] in (0, 3, 6)


def test_sortowanie_po_cenie_stawia_brak_ceny_na_koncu():
    brak = _it("brak", _priced(_leg("A", "B"), 0.0, "szacunek", cena_nieznana=True))
    tani = _rail("tani", 20.0)
    assert variant_list([brak, tani], "price") == [1, 0]


def test_filtr_tylko_potwierdzone():
    built = [_rail("p", 80.0), _rail("s", 40.0, confirmed=False)]
    assert variant_list(built, "price", only_confirmed=True) == [0]
    assert variant_list(built, "price", only_confirmed=False) == [1, 0]


# --- ekran -------------------------------------------------------------------------------------------


def _backend(monkeypatch, built, skipped=()):
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text}],
    )
    monkeypatch.setattr(motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")
    monkeypatch.setattr(
        search_service,
        "search",
        lambda request: search_service.SearchResult(
            request=request,
            built=list(built),
            skipped=list(skipped),
            recommendations=pick_recommendations(list(built)),
        ),
    )


def _run(lang="pl"):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    return at


def _list_table(at):
    return next(d.value for d in at.dataframe if t("list.col.variant") in d.value.columns)


def test_wszystkie_warianty_na_liscie_bez_pokaz_wiecej(monkeypatch):
    built = [_rail(f"Wariant {i}", 50.0 + i, transfers=i % 3, minutes=300 + i) for i in range(12)]
    _backend(monkeypatch, built)
    at = _run()
    assert len(_list_table(at)) == 12
    assert not [c for c in at.checkbox if "Pokaż więcej" in c.label]
    assert len(at.tabs) == 11  # wszystkie kategorie rekomendacji, schowane pod „Zobacz wszystkie opcje”


def test_karta_pokazuje_trase_godziny_przewoznika_cene_i_status(monkeypatch):
    it = _it(
        "Pociąg",
        _priced(_leg("Lublin", "Warszawa Wschodnia"), 30.0),
        _priced(_leg("Warszawa Wschodnia", "Gdańsk Główny", dep=9, arr=12), 67.0),
        transfers=1,
    )
    _backend(monkeypatch, [it])
    at = _run()
    assert "Lublin → Warszawa Wschodnia → Gdańsk Główny" in [s.value for s in at.subheader]
    text = " ".join(m.value for m in at.markdown)
    assert "06:00 → 12:00" in text and "97 PLN" in text
    assert any("PKP Intercity" in c.value for c in at.caption)


def _flat(block):
    """Elementy drzewa AppTest w kolejności wyświetlania (z zagnieżdżonymi kontenerami)."""
    for child in block.children.values():
        if hasattr(child, "children"):
            yield child
            yield from _flat(child)
        else:
            yield child


def _order(at):
    out = []
    for e in _flat(at.main):
        text = getattr(e, "value", None)
        if not isinstance(text, str):
            text = getattr(e, "label", None)
        out.append(text if isinstance(text, str) else "")
    return out


def test_przycisk_szczegoly_wybiera_wariant_i_nie_czysci_wyniku(monkeypatch):
    potw = _rail("Potwierdzony", 80.0)
    szac = _rail("Szacunkowy", 40.0, confirmed=False)
    _backend(monkeypatch, [potw, szac])
    at = _run()
    title = t("details.title", name="Szacunkowy")
    assert title not in [s.value for s in at.subheader]  # domyślnie nic nie jest rozwinięte
    next(b for b in at.button if b.key == "show_estimate").click().run()
    assert not at.exception, at.exception
    assert title in [s.value for s in at.subheader]
    assert at.session_state["search_result"] is not None
    # sortowanie i filtr zostawiają wynik i wybór
    at.selectbox(key="w_variant_sort").set_value("time").run()
    at.checkbox(key="w_only_confirmed").check().run()
    assert not at.exception, at.exception
    assert len(_list_table(at)) == 1
    assert title in [s.value for s in at.subheader]
    assert t("res.recommendations") in [s.value for s in at.subheader]


def test_szczegoly_rozwijaja_sie_tuz_pod_wybrana_karta_i_karta_jest_zaznaczona(monkeypatch):
    # polecana (kompromis) to tańszy szacunek, więc trzy różne sloty: polecana=szacunek, potwierdzona
    # i ten sam szacunek jako "wg szacunku" - sprawdzamy, że szczegóły są pod KLIKNIĘTĄ kartą
    _backend(monkeypatch, [_rail("Potwierdzony", 80.0), _rail("Szacunkowy", 40.0, confirmed=False)])
    at = _run()
    next(b for b in at.button if b.key == "show_confirmed").click().run()
    assert not at.exception, at.exception
    order = _order(at)
    pos = {
        name: next(i for i, v in enumerate(order) if name in v)
        for name in (
            t("cards.recommended"),
            t("cards.confirmed"),
            t("details.title", name="Potwierdzony"),
            t("cards.estimate"),
        )
    }
    # szczegóły są po karcie „Najtańsza potwierdzona” i przed następną kartą
    assert pos[t("cards.confirmed")] < pos[t("details.title", name="Potwierdzony")] < pos[t("cards.estimate")]
    assert [v for v in order if v == t("details.title", name="Potwierdzony")] == [
        t("details.title", name="Potwierdzony")
    ]  # tylko raz: nie w sekcji niżej
    # wybrana karta ma plakietkę, pozostałe nie
    selected = [m.value for m in at.markdown if t("cards.selected") in m.value]
    assert len(selected) == 1 and t("cards.confirmed") in selected[0]
    assert next(b for b in at.button if b.key == "show_confirmed").label == t("cards.hide")
    # ponowne kliknięcie zwija szczegóły
    next(b for b in at.button if b.key == "show_confirmed").click().run()
    assert t("details.title", name="Potwierdzony") not in [s.value for s in at.subheader]
    assert not [m for m in at.markdown if t("cards.selected") in m.value]


def test_ten_sam_wariant_na_dwoch_kartach_rozwija_szczegoly_tylko_pod_jedna(monkeypatch):
    _backend(monkeypatch, [_rail("Jedyny", 50.0)])  # polecana == potwierdzona
    at = _run()
    next(b for b in at.button if b.key == "show_confirmed").click().run()
    assert [s.value for s in at.subheader].count(t("details.title", name="Jedyny")) == 1


def test_domyslny_widok_trzy_karty_a_reszta_zwinieta_pod_zobacz_wszystkie(monkeypatch):
    _backend(
        monkeypatch,
        [_rail("Potwierdzony", 80.0), _rail("Szacunkowy", 40.0, confirmed=False)],
        [SkippedVariant("Objazd", "brak dojazdu")],
    )
    at = _run()
    text = " ".join(m.value for m in at.markdown)
    for key in ("cards.recommended", "cards.confirmed", "cards.estimate"):
        assert t(key) in text
    see_all = [e for e in at.expander if e.label == t("res.see_all")]
    assert len(see_all) == 1
    # lista, sortowanie, zakładki i pominięte są wewnątrz jednego zwiniętego expandera
    inside = see_all[0]
    assert [x.key for x in inside.selectbox] == ["w_variant_sort"]
    assert len(inside.tabs) == 11
    assert any(t("list.col.variant") in d.value.columns for d in inside.dataframe)
    assert t("res.skipped") in [s.value for s in at.subheader]
    # poza expanderem jest tylko krótka informacja o liczbie pominiętych
    assert t("res.skipped_note", n=1) in [c.value for c in at.caption]


def test_pominiete_sa_widoczna_sekcja_z_powodem(monkeypatch):
    _backend(
        monkeypatch,
        [_rail("A", 50.0)],
        [SkippedVariant("Objazd przez Poznań", "brak dojazdu do lotniska")],
    )
    at = _run()
    assert t("res.skipped") in [s.value for s in at.subheader]  # powody w „Zobacz wszystkie opcje”
    assert "- **Objazd przez Poznań**: brak dojazdu do lotniska" in [m.value for m in at.markdown]
    assert not [e for e in at.expander if e.label == t("res.skipped")]
    assert t("res.skipped_note", n=1) in [c.value for c in at.caption]


def test_tanszy_niepotwierdzony_nie_ma_niebieskiej_informacji_a_jest_na_liscie(monkeypatch):
    _backend(monkeypatch, [_rail("Potwierdzony", 80.0), _rail("Szacunkowy", 40.0, confirmed=False)])
    at = _run()
    assert not any("Pominięto" in i.value for i in at.info)
    assert t("rank.cheaper_in_list") in [c.value for c in at.caption]
    assert "Szacunkowy" in " ".join(_list_table(at)[t("list.col.variant")])


def _flight_it():
    fl = _priced(
        _leg("Warszawa Chopin", "Düsseldorf", LegMode.FLIGHT, "Ryanair"),
        200.0,
        "szacunek",
        cena_biletu=150.0,
        bagaz=50.0,
        bagaz_zrodlo="cennik",
    )
    return _it("Lot", fl)


def _details_columns(at):
    return next(
        d.value
        for d in at.dataframe
        if t("col.route") in d.value.columns and t("col.hours") in d.value.columns
    )


def test_kolumny_lotu_tylko_gdy_w_tabeli_jest_lot(monkeypatch):
    _backend(monkeypatch, [_rail("Pociąg", 50.0)])
    at = _run()
    at.session_state["selected_variant"] = 0
    at.run()
    cols = _details_columns(at).columns
    assert t("col.flight_breakdown") not in cols and t("col.baggage_tariff") not in cols

    _backend(monkeypatch, [_flight_it()])
    at = _run()
    at.session_state["selected_variant"] = 0
    at.run()
    cols = _details_columns(at).columns
    assert t("col.flight_breakdown") in cols and t("col.baggage_tariff") in cols


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_ekran_w_kazdym_jezyku(monkeypatch, lang):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    _backend(monkeypatch, [_rail("Potwierdzony", 80.0), _rail("Szacunkowy", 40.0, confirmed=False)])
    at = _run(lang)
    assert t("res.all_variants", lang=lang) in [h.value for h in at.subheader]
    assert t("res.see_all", lang=lang) in [e.label for e in at.expander]
    next(b for b in at.button if b.key == "show_confirmed").click().run()
    assert not at.exception, at.exception
    assert t("details.title", lang=lang, name="Potwierdzony") in [h.value for h in at.subheader]


# --- jeden przepływ wyszukiwania ---------------------------------------------------------------------


def _count_backend(monkeypatch, built, suggestions):
    """_backend z licznikiem wywołań geokodera i wyszukiwarki oraz podaną listą adresów."""
    _backend(monkeypatch, built)
    calls = {"geocode": [], "search": 0}

    def geocode(text, limit=5):
        calls["geocode"].append(text)
        return [dict(s, name=f"{s['name']} ({text})") for s in suggestions]

    inner = search_service.search

    def counting_search(request):
        calls["search"] += 1
        return inner(request)

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    monkeypatch.setattr(search_service, "search", counting_search)
    return calls


def _pick(at, side):
    """Rozwijana lista wyboru miejsca; jej klucz zawiera numer wyszukiwania (pick_<strona>_<n>)."""
    return next(r for r in at.selectbox if r.key and r.key.startswith(f"pick_{side}_"))


def _picks(at):
    return [r for r in at.selectbox if r.key and r.key.startswith("pick_")]


ONE = [{"lat": 50.0, "lon": 19.9, "name": "Miejsce"}]
TWO = ONE + [{"lat": 51.0, "lon": 20.9, "name": "Inne miejsce"}]


def test_pola_skad_dokad_nic_nie_szukaja_przed_przyciskiem(monkeypatch):
    calls = _count_backend(monkeypatch, [_rail("A", 50.0)], ONE)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.text_input(key="origin_query").set_value("Kraków Główny").run()
    at.text_input(key="dest_query").set_value("Gdańsk Główny").run()
    assert calls["geocode"] == [] and calls["search"] == 0
    assert not at.exception, at.exception
    assert at.button[0].label == t("form.submit")
    # (AppTest zapomina wartości pól formularza między przebiegami, więc wpisujemy je ponownie)
    at.text_input(key="origin_query").set_value("Kraków Główny")
    at.text_input(key="dest_query").set_value("Gdańsk Główny")
    at.button[0].click().run()
    assert calls["search"] == 1 and len(calls["geocode"]) == 2
    assert calls["geocode"][0].startswith("Kraków Główny")


def test_jeden_adres_szuka_od_razu_i_pokazuje_skad_dokad_zmien(monkeypatch):
    calls = _count_backend(monkeypatch, [_rail("A", 50.0)], ONE)
    at = _run()
    assert calls["search"] == 1
    assert not _picks(at)
    searching = next(m.value for m in at.markdown if m.value.startswith("Szukamy z:"))
    assert "Miejsce (" in searching and " do: " in searching
    change = next(b for b in at.button if b.key == "change_route")
    assert change.label == t("res.change")
    change.click().run()
    assert not at.exception, at.exception
    assert "search_result" not in at.session_state
    # formularz zostaje z nazwami znalezionymi przez geokoder, do poprawienia
    assert at.text_input(key="origin_query").value.startswith("Miejsce (")


def test_kilka_adresow_pokazuje_krotki_wybor_i_szuka_dopiero_po_potwierdzeniu(monkeypatch):
    calls = _count_backend(monkeypatch, [_rail("A", 50.0)], TWO)
    at = _run()
    assert calls["search"] == 0
    assert t("choose.title") in [s.value for s in at.subheader]
    origin_pick = _pick(at, "origin")
    assert origin_pick.label == t("choose.origin")
    assert len(origin_pick.options) == 2
    assert _pick(at, "dest").label == t("choose.dest")
    assert "search_result" not in at.session_state
    _pick(at, "dest").select_index(1).run()  # zmiana wyboru nic nie szuka
    assert calls["search"] == 0
    next(b for b in at.button if b.key == "pick_submit").click().run()
    assert not at.exception, at.exception
    assert calls["search"] == 1
    assert at.session_state["search_result"]["request"].destination_label.startswith("Inne miejsce")
    assert not _picks(at)


def test_wybor_tylko_dla_pola_z_wieloma_wynikami(monkeypatch):
    _count_backend(monkeypatch, [_rail("A", 50.0)], ONE)
    answers = {"Skad": TWO, "Dokad": ONE}
    monkeypatch.setattr(
        motis_client, "geocode_suggestions", lambda text, limit=5: answers[text.split()[0]]
    )
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.text_input(key="origin_query").set_value("Skad x")
    at.text_input(key="dest_query").set_value("Dokad y")
    at.button[0].click().run()
    assert [r.key for r in _picks(at)] == [_pick(at, "origin").key]


def test_brak_wynikow_geokodera_to_czytelny_blad_bez_szukania(monkeypatch):
    calls = _count_backend(monkeypatch, [_rail("A", 50.0)], [])
    at = _run()
    assert calls["search"] == 0
    assert any("nie znaleźliśmy" in e.value.lower() for e in at.error)


# --- prostszy język ----------------------------------------------------------------------------------


def test_czas_i_przesiadki_zwyklym_jezykiem():
    assert duration_text(510) == "8 h 30 min"
    assert duration_text(480) == "8 h"
    assert duration_text(45) == "45 min"
    assert [transfers_text(n, "pl") for n in (0, 1, 2, 4, 5, 12, 22)] == [
        "bez przesiadek",
        "1 przesiadka",
        "2 przesiadki",
        "4 przesiadki",
        "5 przesiadek",
        "12 przesiadek",
        "22 przesiadki",
    ]
    for lang in LANGUAGES:
        assert "3" in transfers_text(3, lang) and transfers_text(0, lang) != transfers_text(1, lang)


def test_karta_nie_uzywa_zargonu_przesiadek_dwukropek(monkeypatch):
    it = _rail("Pociąg", 50.0, transfers=1, minutes=510)
    _backend(monkeypatch, [it])
    at = _run()
    captions = [c.value for c in at.caption]
    assert "8 h 30 min • 1 przesiadka" in captions
    assert not any("przesiadek:" in c for c in captions)


def test_unikalne_miejsca_i_polecana_trasa():
    a = {"lat": 50.0, "lon": 19.9, "name": "Kraków"}
    assert unique_places([a, dict(a, name="kraków "), {"lat": 51.0, "lon": 20.0, "name": "Kraków"}]) == [
        a,
        {"lat": 51.0, "lon": 20.0, "name": "Kraków"},
    ]
    built = [_rail("A", 50.0), _rail("B", 40.0)]
    recs = pick_recommendations(built)
    assert recommended_variant(built, recs) is recs["najlepszy_kompromis_bezpieczny"]
    assert recommended_variant(built, {}) is built[0]


# --- filtr i ranking kandydatów geokodera, wybór tylko przy realnej niejednoznaczności ---------------

WROCLAW = {"lat": 51.11, "lon": 17.03, "name": "Wrocław", "type": "PLACE", "category": "city"}
WROCLAW_GL = {"lat": 51.09, "lon": 17.04, "name": "Wrocław Główny", "type": "STOP"}
PRZYSTANEK = {"lat": 51.10, "lon": 17.00, "name": "Wrocław, Rynek", "type": "STOP"}
ULICA = {"lat": 51.10, "lon": 17.02, "name": "Rynek 1, Wrocław", "type": "ADDRESS"}
KLOCKI = {"lat": 51.2, "lon": 17.1, "name": "KLOCKI.wroclaw.pl", "type": "PLACE"}
SUYU = {"lat": 41.0, "lon": 29.0, "name": "Lublin suyu", "type": "PLACE"}


def test_smieci_z_geokodera_odpadaja_a_dworce_i_miasta_ida_na_gore():
    got = rank_places([KLOCKI, ULICA, PRZYSTANEK, SUYU, WROCLAW_GL, WROCLAW], "Wroclaw")
    # w grupie miast i dworców wygrywa dokładna nazwa ("Wrocław"), potem reszta wg dopasowania
    assert [s["name"] for s in got] == [
        "Wrocław",
        "Wrocław Główny",
        "Wrocław, Rynek",
        "Rynek 1, Wrocław",
    ]


def test_rodzaj_miejsca_wg_typu_geokodera():
    assert place_kind(WROCLAW_GL) == "stop" and place_kind(ULICA) == "address"
    assert place_kind(KLOCKI, "Wroclaw") is None and place_kind(SUYU, "Lublin") is None
    # PLACE bez kategorii jest miastem tylko, gdy nazwa to wpisany tekst (bez diakrytyków)
    assert place_kind({"lat": 1, "lon": 1, "name": "Wrocław", "type": "PLACE"}, "wroclaw") == "city"
    assert place_kind({"lat": 1, "lon": 1, "name": "Wrocław", "type": "PLACE"}, "Lublin") is None
    # nazwa-adres WWW odpada nawet z miejską kategorią; brak typu = nie oceniamy
    assert place_kind(dict(KLOCKI, category="city"), "x") is None
    assert place_kind({"lat": 1, "lon": 1, "name": "Cokolwiek"}) == "unknown"


def test_pierwszy_jednoznaczny_wynik_miasta_nie_wymaga_wyboru():
    assert clear_place([WROCLAW, WROCLAW_GL, ULICA], "Wroclaw") is WROCLAW
    # pierwszy wynik to nie miasto o tej nazwie -> pytamy
    assert clear_place([WROCLAW_GL, WROCLAW], "Wroclaw") is None
    assert clear_place([PRZYSTANEK, ULICA], "Wrocław, Rynek") is None
    # dwie miejscowości o tej samej nazwie w różnych miejscach -> realna niejednoznaczność
    inne = dict(WROCLAW, lat=40.0, lon=20.0)
    assert clear_place([WROCLAW, inne], "Wrocław") is None
    assert clear_place([], "x") is None


def test_geocode_suggestions_przekazuje_typ_miejsca(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": "A", "lat": 1, "lon": 2, "type": "STOP", "id": "x", "category": "c"}]

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    assert motis_client.geocode_suggestions("A") == [
        {"name": "A", "lat": 1, "lon": 2, "type": "STOP", "category": "c"}
    ]


def _answers(monkeypatch, by_prefix):
    _backend(monkeypatch, [_rail("A", 50.0)])
    monkeypatch.setattr(
        motis_client, "geocode_suggestions", lambda text, limit=5: by_prefix.get(text.strip(), [])
    )


def _submit(at, origin, dest):
    at.text_input(key="origin_query").set_value(origin)
    at.text_input(key="dest_query").set_value(dest)
    at.button[0].click().run()


def test_jednoznaczne_miasto_szuka_od_razu_bez_smieci_w_wyborze(monkeypatch):
    _answers(monkeypatch, {"Wroclaw": [KLOCKI, WROCLAW, SUYU, WROCLAW_GL], "Gdansk": [WROCLAW_GL, ULICA]})
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _submit(at, "Wroclaw", "Gdansk")  # skąd: jednoznaczne miasto; dokąd: dworzec + adres
    assert "search_result" not in at.session_state  # dokąd wymaga wyboru
    assert not [r for r in _picks(at) if r.key.startswith("pick_origin")]
    assert list(_pick(at, "dest").options) == ["🚉  Wrocław Główny", "📍  Rynek 1, Wrocław"]
    _submit_pick = next(b for b in at.button if b.key == "pick_submit")
    _submit_pick.click().run()
    request = at.session_state["search_result"]["request"]
    assert request.origin_label == "Wrocław" and request.destination_label == "Wrocław Główny"


def test_dwa_jednoznaczne_miasta_nie_pytaja_o_wybor(monkeypatch):
    _answers(monkeypatch, {"Wroclaw": [KLOCKI, WROCLAW, SUYU], "Lublin": [dict(WROCLAW, name="Lublin")]})
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _submit(at, "Wroclaw", "Lublin")
    request = at.session_state["search_result"]["request"]
    assert (request.origin_label, request.destination_label) == ("Wrocław", "Lublin")


def test_baner_pokazuje_cel_zaznaczony_na_liscie_a_nie_stary_wybor(monkeypatch):
    """Regresja: ponowne wysłanie formularza przy otwartym wyborze zostawiało zaznaczony stary indeks
    radia przy nowej liście kandydatów (np. baner „KLOCKI.wroclaw.pl” zamiast „Wroclaw”)."""
    first = [WROCLAW_GL, ULICA, PRZYSTANEK]
    second = [dict(WROCLAW_GL, name="Gdańsk Główny"), dict(ULICA, name="Gdańsk 1"), dict(PRZYSTANEK, name="Gdańsk 2")]
    _answers(monkeypatch, {"a x": first, "b y": second, "Wroclaw": [WROCLAW]})
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _submit(at, "Wroclaw", "a x")
    _pick(at, "dest").select_index(2).run()  # użytkownik klika trzecią opcję, ale nie potwierdza
    _submit(at, "Wroclaw", "b y")  # i wysyła formularz od nowa, z tyloma samymi kandydatami
    pick = _pick(at, "dest")
    assert pick.value == 0 and pick.options[0].endswith("Gdańsk Główny")
    next(b for b in at.button if b.key == "pick_submit").click().run()
    searching = next(m.value for m in at.markdown if m.value.startswith("Szukamy z:"))
    assert "**Gdańsk Główny**" in searching


# --- dopasowanie przy błędnym zapisie, duplikaty adresów, odznaczanie wiersza -------------------------


def test_poprawianie_literowek_i_brakujacych_ogonkow_w_nazwie_miasta():
    from ui_helpers import correct_place_text

    assert correct_place_text("lodz") == "Łódź"
    assert correct_place_text("Warzsawa") == "Warszawa"
    assert correct_place_text("Rynek 1, Wroclaw") == "Rynek 1, Wrocław"
    assert correct_place_text("Munchen, Hbf") == "München, Hbf"
    # człony z numerem domu i nieznane nazwy zostają bez zmian
    assert correct_place_text("Krakowskie Przedmieście 50, Lublin") == "Krakowskie Przedmieście 50, Lublin"
    assert correct_place_text("Bahnhofstraße") == "Bahnhofstraße"


def test_najlepiej_pasujace_wyniki_sa_pierwsze_a_numer_domu_decyduje():
    from ui_helpers import match_score

    assert match_score("Łódź", "lodz") > match_score("Łódź Widzew", "lodz")
    assert match_score("Łódź Widzew", "lodz") > match_score("Lublin", "lodz")
    # numer domu liczy się tylko dokładnie: "50" nie łapie "500"
    assert match_score("Krakowskie Przedmieście 46/50", "Krakowskie Przedmieście 50") > match_score(
        "Krakowskie Przedmieście", "Krakowskie Przedmieście 50"
    )
    assert match_score("Ulica 500", "Ulica 50") < match_score("Ulica 50", "Ulica 50")
    lodz = [
        {"lat": 51.77, "lon": 19.54, "name": "Łódź Widzew", "type": "STOP"},
        {"lat": 51.77, "lon": 19.45, "name": "Łódź", "type": "PLACE", "category": "city"},
        {"lat": 51.76, "lon": 19.47, "name": "Łódź Fabryczna", "type": "STOP"},
    ]
    assert [s["name"] for s in rank_places(lodz, "lodz")] == ["Łódź", "Łódź Fabryczna", "Łódź Widzew"]


def test_duplikaty_tego_samego_adresu_w_poblizu_sa_zwijane():
    near = [
        {"lat": 51.2500, "lon": 22.5700, "name": "Krakowskie Przedmieście 46-50"},
        {"lat": 51.2502, "lon": 22.5701, "name": "Krakowskie Przedmieście 46/50"},
        {"lat": 51.2504, "lon": 22.5702, "name": "Krakowskie Przedmieście 46/50"},
    ]
    assert unique_places(near) == near[:1]
    # ta sama nazwa daleko stąd (inna miejscowość) zostaje
    far = near[:1] + [dict(near[0], lat=52.0, lon=21.0)]
    assert len(unique_places(far)) == 2


def test_literowka_w_miescie_pyta_geokoder_poprawiona_nazwa(monkeypatch):
    asked = []
    lodz = {"lat": 51.77, "lon": 19.45, "name": "Łódź", "type": "PLACE", "category": "city"}

    def geocode(text, limit=5):
        asked.append(text)
        return [lodz] if text == "Łódź" else []

    _backend(monkeypatch, [_rail("A", 50.0)])
    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _submit(at, "lodz", "lodz")
    assert "Łódź" in asked and "lodz" in asked  # geokoder dostał poprawiony i wpisany zapis
    request = at.session_state["search_result"]["request"]
    assert request.origin_label == "Łódź" and request.destination_label == "Łódź"


def test_odznaczenie_wiersza_listy_zwija_szczegoly_ale_nie_karty(monkeypatch):
    from types import SimpleNamespace

    import ui_helpers

    def state(rows, slot):
        table = SimpleNamespace(selection=SimpleNamespace(rows=rows))
        return {"tbl": table, ui_helpers.SELECTED_KEY: 1, ui_helpers.SELECTED_SLOT_KEY: slot}

    monkeypatch.setattr(ui_helpers.st, "session_state", state([], ui_helpers.SLOT_LIST))
    ui_helpers._on_row_select("tbl", [3, 1])
    assert ui_helpers.SELECTED_KEY not in ui_helpers.st.session_state
    assert ui_helpers.SELECTED_SLOT_KEY not in ui_helpers.st.session_state
    # szczegóły otwarte pod kartą na górze zostają, gdy odznaczamy wiersz tabeli
    monkeypatch.setattr(ui_helpers.st, "session_state", state([], "confirmed"))
    ui_helpers._on_row_select("tbl", [3, 1])
    assert ui_helpers.st.session_state[ui_helpers.SELECTED_KEY] == 1
    # zaznaczenie wiersza wybiera wariant z listy wg kolejności sortowania
    monkeypatch.setattr(ui_helpers.st, "session_state", state([1], ui_helpers.SLOT_LIST))
    ui_helpers._on_row_select("tbl", [3, 2])
    assert ui_helpers.st.session_state[ui_helpers.SELECTED_KEY] == 2


@pytest.mark.parametrize("lang", [code for code in LANGUAGES if code != "pl"])
def test_opisy_atrakcji_zmieniaja_jezyk_razem_z_interfejsem(monkeypatch, lang):
    """Regresja: po zmianie języka karty atrakcji zostawały z polskimi opisami."""
    from attractions import get_attractions, localized_description

    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    _backend(monkeypatch, [_rail("A", 50.0)])
    at = _run(lang)
    shown = {m.value for m in at.markdown}
    attractions = get_attractions(city="gelsenkirchen")
    assert attractions
    for a in attractions:
        assert localized_description(a, lang) in shown, a.id
        assert a.description not in shown, a.id
