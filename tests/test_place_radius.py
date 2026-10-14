"""Błąd „Toruń”: wieś o tej samej nazwie wygrywała z miastem, bo geokoder zwrócił ją pierwszą.

Gdy wpisany tekst to miasto z places/aliases.json, kandydaci są rozstrzygani po odległości od jego
współrzędnych (promień CITY_RADIUS_KM), najbliższy jest pierwszy, a wpisy o tej samej nazwie różnią się
opisem (region, kraj, odległość, na końcu współrzędne)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from places.aliases import CITY_RADIUS_KM, load_cities
from routing import motis_client, search_service
from ui_helpers import best_place, place_candidates, place_label, suggest_places

ROOT = Path(__file__).resolve().parent.parent
CITIES = {c.key: c for c in load_cities()}


def _place(name, lat, lon, kind="PLACE", category="city", **extra):
    out = {"lat": lat, "lon": lon, "name": name, "type": kind}
    if category:
        out["category"] = category
    return {**out, **extra}


# wsie z raportu: pierwsza to dokładnie ta spod Zamościa
WIES_WSCHOD = _place("Toruń", 51.0949792, 23.1326053, category="village")
WIES_2 = _place("Toruń", 52.0, 20.0, category="village")
TORUN = _place("Toruń", 53.0138, 18.5984)
TORUN_GL = _place("Toruń Główny", 53.0116, 18.6107, kind="STOP", category=None)
TORUN_MIASTO = _place("Toruń Miasto", 53.0150, 18.6030, kind="STOP", category=None)


@pytest.fixture
def geocoder(monkeypatch):
    asked: list[str] = []
    answer: list[dict] = []

    def geocode(text, limit=5):
        asked.append(text)
        return [dict(s) for s in answer]

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)
    return asked, answer


def test_torun_wpisany_bez_wyboru_idzie_do_torunia_a_nie_do_wsi(geocoder):
    asked, answer = geocoder
    answer[:] = [WIES_WSCHOD, WIES_2, TORUN, TORUN_GL, TORUN_MIASTO]
    for typed in (
        "Toruń",
        "Torun",
        "toruń",
        "Thorn",
    ):  # także bez ogonków i po dawnej niemieckiej nazwie
        best = best_place(typed)
        assert (best["lat"], best["lon"]) == (TORUN["lat"], TORUN["lon"]), typed
    options = place_candidates("Toruń")
    assert [o["name"] for o in options] == [
        "Toruń",
        "Toruń Główny",
        "Toruń Miasto",
    ]  # wsie w ogóle odpadają
    assert all("Toruń" in o["name"] for o in options)


def test_torun_glowny_nadal_dziala(geocoder):
    asked, answer = geocoder
    answer[:] = [TORUN_GL, WIES_WSCHOD]
    assert best_place("Toruń Główny")["name"] == "Toruń Główny"


def test_podpowiedzi_dla_torunia_maja_prawdziwy_pierwszy_i_rozne_opisy(geocoder, monkeypatch):
    """Dwie wsie o tej samej nazwie w promieniu miasta: prawdziwy pierwszy, opisy się różnią."""
    asked, answer = geocoder
    wies_blisko = _place(
        "Toruń",
        53.10,
        18.70,
        category="village",
        areas=[{"name": "województwo kujawsko-pomorskie", "adminLevel": 4}],
    )
    wies_dalej = _place(
        "Toruń",
        53.20,
        18.50,
        category="village",
        areas=[{"name": "województwo kujawsko-pomorskie", "adminLevel": 4}],
    )
    prawdziwy = dict(TORUN, areas=[{"name": "województwo kujawsko-pomorskie", "adminLevel": 4}])
    answer[:] = [wies_dalej, wies_blisko, prawdziwy, TORUN_GL]
    labels = [label for label, _ in suggest_places("Toruń", "pl")]
    assert (
        labels[0].startswith("🏙️  Toruń (woj. kujawsko-pomorskie, 0 km)")
        and "Główny" not in labels[0]
    )
    assert len(set(labels)) == len(labels) == 4  # żadne dwa wpisy nie wyglądają tak samo
    town = [label for label in labels if label.startswith("🏙️")]
    assert [label.split("(")[1] for label in town] == [
        "woj. kujawsko-pomorskie, 0 km)",
        "woj. kujawsko-pomorskie, 12 km)",
        "woj. kujawsko-pomorskie, 22 km)",
    ]
    assert labels[-1] == "🚉  Toruń Główny"  # wpis bez duplikatu zostaje bez opisu


def test_pelny_przeplyw_krakow_glowny_do_torunia_bez_wyboru_z_listy(monkeypatch):
    from datetime import UTC, datetime

    from routing.model import Itinerary, Leg, LegMode, PricedLeg
    from routing.scoring import pick_recommendations

    krakow_gl = _place("Kraków Główny", 50.0675, 19.9475, kind="STOP", category=None)
    answers = {"Kraków Główny": [krakow_gl], "Toruń": [WIES_WSCHOD, WIES_2, TORUN, TORUN_GL]}
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [dict(s) for s in answers.get(text, [])],
    )
    seen = []

    def fake_search(request):
        seen.append(request)
        leg = Leg(
            LegMode.RAIL,
            "A",
            "B",
            datetime(2026, 10, 18, 6, tzinfo=UTC),
            datetime(2026, 10, 18, 9, tzinfo=UTC),
            carrier_name="PKP Intercity",
        )
        it = Itinerary(
            "Pociąg", [PricedLeg(leg, 50.0, "PLN", "oficjalna_taryfa", breakdown={})], 50.0, 180, 0
        )
        return search_service.SearchResult(
            request=request, built=[it], skipped=[], recommendations=pick_recommendations([it])
        )

    monkeypatch.setattr(search_service, "search", fake_search)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.session_state["origin_query"] = "Kraków Główny"
    at.session_state["dest_query"] = "Toruń"
    at.button[0].click().run()
    assert not at.exception, at.exception
    (request,) = seen
    assert request.destination_stop_id == f"{TORUN['lat']},{TORUN['lon']}"  # nie 51.09, 23.13
    assert request.destination_label == "Toruń"


# --- ta sama klasa błędu dla każdego miasta i każdej nazwy z pliku -------------------------------------


def _all_names():
    return [(c.key, n) for c in CITIES.values() for n in c.search_names()]


@pytest.mark.parametrize("key,name", _all_names())
def test_wies_o_tej_samej_nazwie_nie_wygrywa_z_miastem(geocoder, key, name):
    """Dla każdego miasta z pliku i każdej jego nazwy (6 języków, aliasy): geokoder zwraca najpierw wieś o
    nazwie miasta setki km dalej, potem właściwe miasto - wygrywa miasto."""
    city = CITIES[key]
    asked, answer = geocoder
    wies = _place(city.local, city.lat + 2.0, city.lon + 4.0, category="village")
    real = _place(city.local, city.lat + 0.02, city.lon + 0.02)
    answer[:] = [wies, real]
    best = best_place(name)
    assert best is not None and (best["lat"], best["lon"]) == (real["lat"], real["lon"]), (
        key,
        name,
    )
    assert [o["lat"] for o in place_candidates(name)] == [real["lat"]]


def test_zadne_miasto_z_pliku_nie_ma_wspolrzednych_poza_zakresem():
    for city in CITIES.values():
        assert city.lat is not None and city.lon is not None, city.key
    assert CITY_RADIUS_KM == 25.0


def test_gdy_w_promieniu_nic_nie_ma_nie_wybieramy_wsi(geocoder):
    asked, answer = geocoder
    answer[:] = [WIES_WSCHOD, WIES_2]
    assert place_candidates("Toruń") == [] and best_place("Toruń") is None


def test_tekst_ktory_nie_jest_miastem_z_pliku_nie_jest_filtrowany(geocoder):
    asked, answer = geocoder
    adres = _place("Rynek 1", 51.0, 23.0, kind="ADDRESS", category=None)
    wies = _place("Nowa Wieś", 51.0, 23.0, category="village")
    answer[:] = [adres, wies]
    # atrapa zwraca obu kandydatów na każde zapytanie; adres z numerem domu i nieznana nazwa zostają
    # mimo odległości od Torunia
    assert "Rynek 1" in [o["name"] for o in place_candidates("Rynek 1, Toruń")]
    assert "Nowa Wieś" in [o["name"] for o in place_candidates("Nowa Wieś")]


# --- opisy wpisów o tej samej nazwie -----------------------------------------------------------------------


def test_wpisy_o_tej_samej_nazwie_roznia_sie_regionem_krajem_lub_wspolrzednymi(
    geocoder, monkeypatch
):
    asked, answer = geocoder
    mazowieckie = [
        {"name": "Polska", "adminLevel": 2},
        {"name": "województwo mazowieckie", "adminLevel": 4},
    ]
    answer[:] = [
        _place("Nowa Wieś", 52.0, 21.0, category="village", areas=mazowieckie),
        _place("Nowa Wieś", 51.0, 23.0, category="village"),  # region z odwrotnego geokodowania
        _place(
            "Nowa Wieś", 50.0, 20.0, category="village", country="PL"
        ),  # reverse nie działa: kraj
        _place(
            "Nowa Wieś", 50.1, 20.1, category="village", country="PL"
        ),  # też kraj: dopisujemy współrzędne
    ]

    def reverse(lat, lon):
        if (lat, lon) == (51.0, 23.0):
            return [{"name": "województwo lubelskie", "adminLevel": 4}]
        raise motis_client.MotisError("brak")

    monkeypatch.setattr(motis_client, "reverse_geocode_areas", reverse)
    labels = [label for label, _ in suggest_places("Nowa Wieś", "pl")]
    assert len(set(labels)) == 4
    joined = "\n".join(labels)
    assert "(woj. mazowieckie)" in joined and "(woj. lubelskie)" in joined
    assert "(PL, 50.00, 20.00)" in joined and "(PL, 50.10, 20.10)" in joined


def test_wpis_bez_duplikatu_nie_dostaje_opisu_a_etykieta_w_podpisie_wyboru_go_zawiera(geocoder):
    asked, answer = geocoder
    answer[:] = [_place("Opole", 50.6751, 17.9213)]
    ((label, option),) = suggest_places("Opole", "en")
    assert label == "🏙️  Opole" and "detail" not in option
    option["detail"] = "woj. opolskie"
    assert place_label(option, lang="en") == "🏙️  Opole (woj. opolskie)"


# --- klient MOTIS: obszary i odwrotne geokodowanie -----------------------------------------------------------


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_geokoder_przekazuje_obszary_i_kraj_a_odwrotne_geokodowanie_jest_pamietane(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if url.endswith("/geocode"):
            return _Resp(
                [
                    {
                        "name": "Toruń",
                        "lat": 53.0,
                        "lon": 18.6,
                        "type": "PLACE",
                        "country": "PL",
                        "areas": [
                            {
                                "name": "województwo kujawsko-pomorskie",
                                "adminLevel": 4,
                                "matched": False,
                            },
                            {"name": "bez poziomu"},
                        ],
                    }
                ]
            )
        return _Resp(
            [
                {"name": "x", "areas": []},
                {"name": "y", "areas": [{"name": "Polska", "adminLevel": 2, "matched": False}]},
            ]
        )

    monkeypatch.setattr(motis_client.requests, "get", fake_get)
    (found,) = motis_client.geocode_suggestions("Toruń")
    assert found["country"] == "PL"
    assert found["areas"] == [{"name": "województwo kujawsko-pomorskie", "adminLevel": 4}]
    assert motis_client.reverse_geocode_areas(53.0, 18.6) == [{"name": "Polska", "adminLevel": 2}]
    assert motis_client.reverse_geocode_areas(53.0, 18.6)  # drugi raz z pamięci
    assert calls.count("http://localhost:8080/api/v1/reverse-geocode") == 1


# --- scripts/check_place_geocoding.py (bez sieci) -----------------------------------------------------------


def _check_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_place_geocoding", ROOT / "scripts" / "check_place_geocoding.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skrypt_kontrolny_oznacza_pierwszego_kandydata_dalej_niz_25_km():
    script = _check_script()
    torun = CITIES["torun"]
    geocode = lambda q: [WIES_WSCHOD, TORUN]  # geokoder: wieś pierwsza, jak w błędzie
    best = lambda q: TORUN  # aplikacja po poprawce: miasto
    row = script.check_name(torun, "de", geocode, best)
    assert row["query"] == "Toruń" and row["first_problem"] and not row["app_problem"]
    assert row["first_km"] > 100 and row["app_km"] < 1
    ok = script.check_name(torun, "pl", lambda q: [TORUN], best)
    assert not ok["first_problem"] and not ok["app_problem"]
    nic = script.check_name(torun, "pl", lambda q: [], lambda q: None)
    assert nic["first_problem"] and nic["app_problem"] and nic["first"] == "(brak wyniku)"

    def boom(q):
        raise motis_client.MotisError("brak MOTIS")

    assert script.check_name(torun, "pl", boom, best)["app_problem"]
    table = script.format_table([row, ok])
    assert "PROBLEM" in table.splitlines()[2] and "pierwszy kandydat" in table.splitlines()[0]
    assert len(table.splitlines()) == 4  # nagłówek, kreski, 2 wiersze
