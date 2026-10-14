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
    duration_text,
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
    assert not [r for r in at.radio if r.key and r.key.startswith("pick_")]
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
    origin_pick = at.radio(key="pick_origin")
    assert origin_pick.label == t("choose.origin")
    assert len(origin_pick.options) == 2
    assert at.radio(key="pick_dest").label == t("choose.dest")
    assert "search_result" not in at.session_state
    at.radio(key="pick_dest").set_value(1).run()  # zmiana wyboru nic nie szuka
    assert calls["search"] == 0
    next(b for b in at.button if b.key == "pick_submit").click().run()
    assert not at.exception, at.exception
    assert calls["search"] == 1
    assert at.session_state["search_result"]["request"].destination_label.startswith("Inne miejsce")
    assert not [r for r in at.radio if r.key and r.key.startswith("pick_")]


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
    assert [r.key for r in at.radio if r.key.startswith("pick_")] == ["pick_origin"]


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
