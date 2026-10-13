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
from ui_helpers import carriers_summary, route_summary, time_span, variant_list

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
    assert len(at.tabs) == 11  # wszystkie kategorie rekomendacji od razu


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


def test_przycisk_szczegoly_wybiera_wariant_i_nie_czysci_wyniku(monkeypatch):
    potw = _rail("Potwierdzony", 80.0)
    szac = _rail("Szacunkowy", 40.0, confirmed=False)
    _backend(monkeypatch, [potw, szac])
    at = _run()
    assert t("details.none") in [c.value for c in at.caption]
    next(b for b in at.button if b.key == "show_estimate").click().run()
    assert not at.exception, at.exception
    assert t("details.title", name="Szacunkowy") in [h.value for h in at.header]
    assert at.session_state["search_result"] is not None
    # sortowanie i filtr zostawiają wynik i wybór
    at.selectbox(key="w_variant_sort").set_value("time").run()
    at.checkbox(key="w_only_confirmed").check().run()
    assert not at.exception, at.exception
    assert len(_list_table(at)) == 1
    assert t("details.title", name="Szacunkowy") in [h.value for h in at.header]
    assert t("res.recommendations") in [h.value for h in at.header]


def test_pominiete_sa_widoczna_sekcja_z_powodem(monkeypatch):
    _backend(
        monkeypatch,
        [_rail("A", 50.0)],
        [SkippedVariant("Objazd przez Poznań", "brak dojazdu do lotniska")],
    )
    at = _run()
    assert t("res.skipped") in [s.value for s in at.subheader]
    assert "- **Objazd przez Poznań**: brak dojazdu do lotniska" in [m.value for m in at.markdown]
    assert not [e for e in at.expander if e.label == t("res.skipped")]


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
    assert t("res.all_variants", lang=lang) in [h.value for h in at.header]
    next(b for b in at.button if b.key == "show_confirmed").click().run()
    assert not at.exception, at.exception
    assert any(
        h.value.startswith(t("details.title", lang=lang, name="").strip()[:5]) for h in at.header
    )
