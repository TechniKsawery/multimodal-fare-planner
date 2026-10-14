"""Podpowiedzi w polach „Skąd” i „Dokąd” przy pisaniu: limity zapytań do geokodera, pamięć podręczna,
filtr śmieci, literówki, odczyt stanu pola i to, że pisanie nie kasuje pokazanego wyniku.

Sam komponent (streamlit-searchbox) działa w przeglądarce; AppTest go nie wykonuje, więc tu sprawdzamy
logikę po stronie Pythona (funkcja podpowiedzi, odczyt stanu), a przepływ z przeglądarką opisuje PR.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ui_helpers
from routing import motis_client, search_service
from routing.model import Itinerary, Leg, LegMode, PricedLeg
from routing.scoring import pick_recommendations
from ui_helpers import MIN_SUGGEST_CHARS, place_input, suggest_places

ROOT = Path(__file__).resolve().parent.parent

LODZ = {"lat": 51.77, "lon": 19.45, "name": "Łódź", "type": "PLACE", "category": "city"}
LODZ_FABRYCZNA = {"lat": 51.76, "lon": 19.47, "name": "Łódź Fabryczna", "type": "STOP"}
KLOCKI = {"lat": 51.2, "lon": 17.1, "name": "KLOCKI.wroclaw.pl", "type": "PLACE"}
SKLEP = {
    "lat": 51.7,
    "lon": 19.4,
    "name": "Łódź Sklep Sp. z o.o.",
    "type": "PLACE",
    "category": "shop",
}


@pytest.fixture
def geocoder(monkeypatch):
    """Podstawia geokoder odpowiadający wg słownika {tekst: wyniki}; zapisuje zapytania."""
    asked: list[str] = []
    answers: dict[str, list[dict]] = {}

    def geocode(text, limit=5):
        asked.append(text)
        return [dict(s) for s in answers.get(text, [])]

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    return asked, answers


# --- limity zapytań do MOTIS -----------------------------------------------------------------------------


def test_krotki_tekst_nie_pyta_geokodera(geocoder):
    asked, answers = geocoder
    answers["Łó"] = [LODZ]
    for text in ("", " ", "a", "Łó", "  Łó  "):
        assert suggest_places(text) == []
    assert asked == [] and MIN_SUGGEST_CHARS == 3


def test_od_minimalnej_dlugosci_pyta_a_odstepy_nie_licza_sie(geocoder):
    asked, answers = geocoder
    answers["Łódź"] = [LODZ]
    assert [o["name"] for _, o in suggest_places("  Łódź ")] == ["Łódź"]
    assert asked == ["Łódź"]  # tekst bez odstępów, jedno zapytanie


def test_jeden_wpis_to_najwyzej_dwa_zapytania_i_powtorka_idzie_z_pamieci(geocoder):
    asked, answers = geocoder
    answers["Łódź"] = [LODZ]
    suggest_places("lodz")  # poprawiona nazwa + wpisany zapis
    assert set(asked) == {"Łódź", "lodz"} and len(asked) == 2
    for _ in range(5):  # cofnięcie znaku, ponowny wybór, wysłanie formularza
        suggest_places("lodz")
        suggest_places("LODZ ")
    assert len(asked) == 2


def test_pamiec_wygasa_po_ttl_i_ma_limit_wpisow(geocoder, monkeypatch):
    asked, answers = geocoder
    now = [1000.0]
    monkeypatch.setattr(motis_client.time, "monotonic", lambda: now[0])
    motis_client.geocode_suggestions_cached("Lublin")
    motis_client.geocode_suggestions_cached("lublin ")
    assert asked == ["Lublin"]
    now[0] += motis_client.GEOCODE_CACHE_TTL_S + 1
    motis_client.geocode_suggestions_cached("Lublin")
    assert asked == ["Lublin", "Lublin"]
    monkeypatch.setattr(motis_client, "GEOCODE_CACHE_MAX", 3)
    for i in range(10):
        motis_client.geocode_suggestions_cached(f"Miasto {i}")
    assert len(motis_client._GEOCODE_CACHE) <= 3


def test_wynik_z_pamieci_to_kopia_i_blad_nie_jest_zapamietany(monkeypatch):
    calls = []

    def geocode(text, limit=5):
        calls.append(text)
        if len(calls) == 1:
            raise motis_client.MotisError("brak MOTIS")
        return [{"lat": 1.0, "lon": 2.0, "name": "A"}]

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    with pytest.raises(motis_client.MotisError):
        motis_client.geocode_suggestions_cached("abc")
    first = motis_client.geocode_suggestions_cached("abc")  # po błędzie pyta jeszcze raz
    first[0]["name"] = "zmieniona"
    assert motis_client.geocode_suggestions_cached("abc")[0]["name"] == "A"
    assert len(calls) == 2


def test_blad_geokodera_idzie_wyzej_do_obslugi_w_ui(monkeypatch):
    def geocode(text, limit=5):
        raise motis_client.MotisError("brak MOTIS")

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    with pytest.raises(motis_client.MotisError):
        suggest_places("Lublin")


# --- co pokazują podpowiedzi -----------------------------------------------------------------------------


def test_smieciowe_trafienia_sa_odfiltrowane_a_miasto_i_dworzec_na_gorze(geocoder):
    asked, answers = geocoder
    adres = {"lat": 51.7, "lon": 19.5, "name": "Łódzka 5", "type": "ADDRESS"}
    answers["Łódź"] = [KLOCKI, adres, SKLEP, LODZ_FABRYCZNA, LODZ]
    got = suggest_places("Łódź")
    assert [o["name"] for _, o in got] == ["Łódź", "Łódź Fabryczna", "Łódzka 5"]
    assert [label for label, _ in got][:2] == ["🏙️  Łódź", "🚉  Łódź Fabryczna"]


def test_literowki_i_brak_ogonkow_dzialaja_jak_przy_wyszukiwaniu(geocoder):
    asked, answers = geocoder
    answers["Łódź"] = [LODZ_FABRYCZNA, LODZ]
    answers["Warszawa"] = [
        {"lat": 52.2, "lon": 21.0, "name": "Warszawa", "type": "PLACE", "category": "city"}
    ]
    assert suggest_places("lodz")[0][1]["name"] == "Łódź"
    assert suggest_places("Warzsawa")[0][1]["name"] == "Warszawa"
    assert "Łódź" in asked and "Warszawa" in asked


def test_podpowiedzi_w_jezyku_interfejsu_z_nazwa_lokalna(geocoder):
    asked, answers = geocoder
    koln = {"lat": 50.94, "lon": 6.96, "name": "Köln", "type": "PLACE", "category": "city"}
    koln_hbf = {"lat": 50.94, "lon": 6.96, "name": "Köln Hbf", "type": "STOP"}
    answers["Köln"] = [koln_hbf, koln]
    assert [l for l, _ in suggest_places("Cologne", "en")] == [
        "🏙️  Cologne · Köln",
        "🚉  Cologne Hbf · Köln Hbf",
    ]
    assert [l for l, _ in suggest_places("Keulen", "pl")] == [
        "🏙️  Kolonia · Köln",
        "🚉  Kolonia Hbf · Köln Hbf",
    ]
    assert "Köln" in asked  # geokoder dostał nazwę lokalną


# --- stan pola i wynik wyszukiwania ---------------------------------------------------------------------


def test_place_input_czyta_wybor_wpisany_tekst_albo_zapamietany_tekst(monkeypatch):
    state = {"origin_query": "Lublin"}
    monkeypatch.setattr(ui_helpers.st, "session_state", state)
    assert place_input("origin") == ("Lublin", None)  # pole jeszcze nie istnieje
    state["origin_sb"] = {"result": "Wroc", "search": "Wroc"}
    assert place_input("origin") == ("Wroc", None)  # wpisano, nic nie wybrano
    state["origin_sb"] = {"result": LODZ, "search": "lod"}
    assert place_input("origin") == ("Łódź", LODZ)  # wybrana podpowiedź
    state["origin_sb"] = {"result": None, "search": ""}
    assert place_input("origin") == ("Lublin", None)


def _fake_search(request):
    leg = Leg(
        mode=LegMode.RAIL,
        origin_name="A",
        destination_name="B",
        depart=datetime(2026, 10, 18, 6, tzinfo=UTC),
        arrive=datetime(2026, 10, 18, 8, tzinfo=UTC),
        carrier_name="PKP Intercity",
    )
    it = Itinerary(
        variant_name="Pociąg",
        legs=[PricedLeg(leg, 50.0, "PLN", "oficjalna_taryfa", breakdown={})],
        total_price_pln=50.0,
        total_duration_min=120,
        num_transfers=0,
    )
    return search_service.SearchResult(
        request=request, built=[it], skipped=[], recommendations=pick_recommendations([it])
    )


def test_pisanie_w_polach_nie_kasuje_pokazanego_wyniku(monkeypatch):
    """Pisanie przeładowuje tylko pola (fragment), a nawet pełny przebieg bez wysłania formularza zostawia
    wynik z st.session_state["search_result"] na ekranie."""
    searches = []
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text, "type": "STOP"}],
    )
    monkeypatch.setattr(search_service, "search", lambda r: searches.append(r) or _fake_search(r))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.button[0].click().run()
    assert len(searches) == 1 and "search_result" in at.session_state
    shown = {m.value for m in at.markdown if m.value.startswith("Szukamy z:")}
    assert len(shown) == 1
    for typed in ("Wro", "Wroc", "Wrocław Gł"):  # kolejne „naciśnięcia klawiszy” w polu Dokąd
        at.session_state["dest_query"] = typed
        at.run()
        assert not at.exception, at.exception
        assert "search_result" in at.session_state
        assert {m.value for m in at.markdown if m.value.startswith("Szukamy z:")} == shown
    assert len(searches) == 1  # i nic nie szukało samo


def test_przycisk_szuka_bez_wybranej_podpowiedzi_najlepszym_dopasowaniem(geocoder, monkeypatch):
    asked, answers = geocoder
    answers["Łódź"] = [LODZ_FABRYCZNA, KLOCKI, LODZ]
    searches = []
    monkeypatch.setattr(search_service, "search", lambda r: searches.append(r) or _fake_search(r))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.session_state["origin_query"] = "lodz"  # tylko wpisane, bez wyboru z listy
    at.session_state["dest_query"] = "lodz"
    at.button[0].click().run()
    assert not at.exception, at.exception
    (request,) = searches
    assert request.origin_label == "Łódź" and request.destination_label == "Łódź"
    assert request.origin_stop_id == "51.77,19.45"


def test_pole_zalozone_od_nowa_po_zmianie_tekstu_z_zewnatrz(geocoder):
    """„zmień” ustawia tekst w session_state; pole musi go przejąć, a nie zostać przy starej wartości."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.session_state["origin_query"] = "Gdańsk Główny"
    at.run()
    assert at.session_state["origin_sb"]["result"] == "Gdańsk Główny"
    assert at.session_state["origin_query"] == "Gdańsk Główny"
    assert not at.exception, at.exception
