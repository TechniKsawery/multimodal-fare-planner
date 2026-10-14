"""Wersje językowe UI (i18n/): komplet kluczy, spójne pola {…}, polski jako domyślny i zapasowy
oraz przebieg całej aplikacji Streamlit w każdym języku (MOTIS mockowany, bez sieci)."""

import json
import string
from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import i18n
from attractions import CATEGORY_LABELS, AttractionCategory
from i18n import DEFAULT_LANG, LANGUAGES, TRANSLATIONS, label_or, t
from routing import motis_client, search_service
from routing.model import (
    OTHER_DAY_SECTION_TITLE,
    Itinerary,
    Leg,
    LegMode,
    PricedLeg,
    TransferWarning,
)
from routing.scoring import RECOMMENDATION_LABELS, pick_recommendations
from tests.test_price_status_ui import leg_table, open_details

ROOT = Path(__file__).resolve().parent.parent
PL = TRANSLATIONS["pl"]


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_obslugiwane_jezyki():
    assert list(LANGUAGES) == ["pl", "en", "de", "es", "fr", "nl"]
    assert DEFAULT_LANG == "pl"
    assert set(TRANSLATIONS) == set(LANGUAGES)


@pytest.mark.parametrize("lang", [l for l in LANGUAGES if l != "pl"])
def test_komplet_kluczy_i_te_same_pola(lang):
    tr = TRANSLATIONS[lang]
    assert set(PL) - set(tr) == set(), f"{lang}: brak kluczy"
    assert set(tr) - set(PL) == set(), f"{lang}: nadmiarowe klucze"
    for key, text in PL.items():
        assert _fields(tr[key]) == _fields(text), f"{lang}/{key}: inne pola {{…}} niż w PL"
        assert tr[key].strip(), f"{lang}/{key}: pusty tekst"


def test_polski_domyslny_i_zapasowy():
    assert t("form.submit") == "Szukaj połączeń"
    assert t("form.submit", lang="de") == "Verbindungen suchen"
    assert t("form.submit", lang="xx") == "Szukaj połączeń"  # nieznany język -> polski
    assert t("klucz.ktorego.nie.ma") == "klucz.ktorego.nie.ma"
    assert t("list.hint", lang="en", shown=3, total=5).startswith("All options: 3 of 5")


def test_tlumaczenia_etykiet_domenowych_pokrywaja_slowniki():
    assert set(RECOMMENDATION_LABELS) == {k[4:] for k in PL if k.startswith("rec.")}
    for key, label in RECOMMENDATION_LABELS.items():
        assert PL[f"rec.{key}"] == label
        assert label_or("rec", key, "?") == label
    for cat in AttractionCategory:
        assert PL[f"cat.{cat.value}"] == CATEGORY_LABELS[cat]
    assert PL["other_day.title"] == OTHER_DAY_SECTION_TITLE
    pkp = json.loads((ROOT / "fares/data/pkp_intercity.json").read_text(encoding="utf-8"))
    assert {f"pkp.{k}" for k in pkp["ulgi_procent"]} <= set(PL)
    assert label_or("pkp", "nie_ma_takiej_ulgi", "surowy") == "surowy"


# --- cała aplikacja w każdym języku -------------------------------------------------------------


def _itinerary() -> Itinerary:
    def leg(a, b, h1, h2):
        return Leg(
            mode=LegMode.RAIL,
            origin_name=a,
            destination_name=b,
            depart=datetime(2026, 10, 18, h1, 0, tzinfo=UTC),
            arrive=datetime(2026, 10, 18, h2, 0, tzinfo=UTC),
            carrier_name="PKP Intercity",
            distance_km=100.0,
        )

    legs = [
        PricedLeg(leg("Kraków", "Katowice", 6, 8), 40.0, "PLN", "oficjalna_taryfa"),
        PricedLeg(
            leg("Katowice", "Berlin", 8, 14),
            60.0,
            "PLN",
            "szacunek",
            breakdown={"price_verified": False, "wartosc_zastepcza": True},
        ),
    ]
    return Itinerary(
        variant_name="Tylko kolej",
        legs=legs,
        total_price_pln=100.0,
        total_duration_min=480.0,
        num_transfers=1,
        transfer_warnings=[
            TransferWarning(after_leg_index=0, gap_minutes=5, minimum_required_minutes=10, reason="x")
        ],
    )


@pytest.fixture
def mocked_backend(monkeypatch):
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text}],
    )
    monkeypatch.setattr(motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")

    def fake_search(request):
        it = _itinerary()
        return search_service.SearchResult(
            request=request, built=[it], skipped=[], recommendations=pick_recommendations([it])
        )

    monkeypatch.setattr(search_service, "search", fake_search)


def _app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)


def test_aplikacja_startuje_po_polsku(mocked_backend):
    at = _app().run()
    assert not at.exception
    assert at.title[0].value == PL["app.title"]
    assert at.radio[0].value == "pl"


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_aplikacja_w_kazdym_jezyku_wyszukuje_i_renderuje_wyniki(mocked_backend, monkeypatch, lang):
    # AppTest wywołuje format_func selectboxów POZA skryptem (t() widzi wtedy domyślny język) i
    # trzyma ich stan jako sformatowaną etykietę — stąd podmiana current_lang i ustawienie
    # języka przed pierwszym przebiegiem. W prawdziwym Streamlicie stan to indeks.
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    at = _app()
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception
    assert at.radio[0].value == lang
    assert at.title[0].value == t("app.title", lang=lang)

    at.button[0].click().run()  # formularz wyszukiwania
    assert not at.exception, at.exception
    assert t("res.see_all", lang=lang) in [e.label for e in at.expander]
    assert t("res.recommendations", lang=lang) in [h.value for h in at.subheader]
    assert t("res.all_variants", lang=lang) in [h.value for h in at.subheader]
    open_details(at)
    near_miss = t("transfer.near_miss", lang=lang, station="Katowice", shortfall="5", gap="5", required="10")
    # Streamlit zamienia początkowe emoji komunikatu na ikonę, więc w .value go już nie ma
    assert near_miss.removeprefix("🟡 ") in [i.value for i in at.info]
    assert t("price.unverified_total", lang=lang) in [c.value for c in at.caption]
    # ceny odcinków nie zależą od języka
    rows = leg_table(at, lang)
    assert t("col.price", lang=lang) in rows.columns
    prices = list(rows[t("col.price", lang=lang)])
    assert prices[0].startswith("40.00 PLN") and prices[1].startswith("60.00 PLN")
    assert t("price.unverified_fallback", lang=lang) in prices[1]
    assert [t(f"rec.{k}", lang=lang) for k in ("najtansza", "najszybsza")] == [
        tab.label for tab in at.tabs
    ][:2]
    assert at.metric[1].value == t("metric.price_exact", lang=lang, price="100.00")


def test_zmiana_jezyka_zachowuje_wynik_wyszukiwania(mocked_backend):
    at = _app().run()
    at.button[0].click().run()
    assert PL["res.recommendations"] in [h.value for h in at.subheader]
    at.radio[0].set_value("de").run()
    assert not at.exception
    assert t("res.recommendations", lang="de") in [h.value for h in at.subheader]


def test_html_lang_script_ustawia_lang_dokumentu_nadrzednego():
    from ui_helpers import html_lang_script

    for lang in LANGUAGES:
        js = html_lang_script(lang)
        assert f'h.lang="{lang}"' in js
        assert "window.parent.document" in js


def test_html_lang_script_wylacza_tlumaczenie_chrome():
    from ui_helpers import html_lang_script

    for lang in LANGUAGES:
        js = html_lang_script(lang)
        assert "h.setAttribute('translate','no')" in js
        assert "d.body.setAttribute('translate','no')" in js
        assert "m.name='google'" in js and "m.content='notranslate'" in js


def test_aplikacja_renderuje_skrypt_lang_i_aktualizuje_go_po_zmianie_jezyka(mocked_backend):
    # AppTest nie ma przeglądarki, więc nie wykona skryptu ani nie sprawdzi realnego <html lang>;
    # weryfikujemy, że w każdym przebiegu do drzewa trafia iframe z właściwym językiem.
    from ui_helpers import html_lang_script

    at = _app().run()
    assert not at.exception
    assert [e.proto.srcdoc for e in at.get("iframe")] == [html_lang_script("pl")]
    at.radio[0].set_value("de").run()
    assert not at.exception
    assert [e.proto.srcdoc for e in at.get("iframe")] == [html_lang_script("de")]
    # Świeża sesja na każdy język (zmiana języka w jednej sesji zmienia etykiety innych widżetów,
    # czego AppTest nie obsługuje), żeby skrypt został sprawdzony dla wszystkich 6 języków.
    for lang in LANGUAGES:
        at = _app()
        at.session_state["lang"] = lang
        at.run()
        assert not at.exception
        assert [e.proto.srcdoc for e in at.get("iframe")] == [html_lang_script(lang)]
