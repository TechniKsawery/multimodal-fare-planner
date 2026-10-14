"""Nazwy miast w 6 językach (places/aliases.json): kompletność danych, wyszukiwanie po dowolnej nazwie,
wyświetlanie w języku interfejsu z nazwą lokalną, skrypt weryfikujący względem Wikidata (bez sieci).
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from places.aliases import (
    DATA_PATH,
    LANGUAGES,
    City,
    find_city,
    fold,
    load_cities,
    local_query,
    localize_name,
    place_text,
)
from routing import motis_client, search_service
from ui_helpers import best_place, correct_place_text, place_label

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
CITIES = {c.key: c for c in load_cities()}
LOCAL_LANG = {"PL": "pl", "DE": "de", "AT": "de", "NL": "nl"}  # CZ: czeski nie jest językiem UI

# Miasta z fares/ i attractions/ (klucze jak w attractions.json i test_city_completeness) oraz główne
# miasta PL i DE wskazane w zadaniu: każde musi mieć wpis z aliasami.
REQUIRED = {
    "lublin", "warszawa", "krakow", "poznan", "wroclaw", "berlin", "hamburg", "munchen", "koln",
    "gelsenkirchen", "dusseldorf", "gdansk", "szczecin", "lodz", "katowice", "dresden", "leipzig",
    "frankfurt_am_main", "stuttgart", "nurnberg", "gorlitz", "zgorzelec",
}  # fmt: skip


def _attraction_cities() -> set[str]:
    data = json.loads((ROOT / "attractions/data/attractions.json").read_text(encoding="utf-8"))
    return {a["city"] for a in data["atrakcje"]}


# --- dane: kompletność i uczciwość ---------------------------------------------------------------------


def test_kazde_miasto_ma_wpis_dla_kazdego_jezyka_albo_jawne_puste_pole():
    assert tuple(DATA["jezyki"]) == LANGUAGES == ("pl", "en", "de", "es", "fr", "nl")
    for key, entry in DATA["miasta"].items():
        assert set(entry["wyswietlana"]) == set(
            LANGUAGES
        ), key  # brak klucza = luka; "" = jawnie pusto
        assert all(isinstance(v, str) for v in entry["wyswietlana"].values()), key
        assert entry["local"].strip() and entry["kraj"] in {"PL", "DE", "AT", "CZ", "NL"}, key


def test_miasta_z_zadania_fares_i_attractions_maja_aliasy():
    assert set(CITIES) >= REQUIRED, sorted(REQUIRED - set(CITIES))
    assert _attraction_cities() <= set(CITIES), sorted(_attraction_cities() - set(CITIES))


def test_nazwa_w_jezyku_kraju_miasta_to_nazwa_lokalna():
    for key, city in CITIES.items():
        lang = LOCAL_LANG.get(city.country)
        if lang and city.display[lang]:
            assert city.display[lang] == city.local, key


def test_zadna_nazwa_nie_nalezy_do_dwoch_miast():
    seen: dict[str, str] = {}
    for key, city in CITIES.items():
        for name in city.search_names():
            folded = fold(name)
            assert seen.setdefault(folded, key) == key, f"{name!r}: {seen[folded]} i {key}"


def test_zrodlo_data_i_status_weryfikacji_sa_zapisane_jawnie():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", DATA["_data_aktualizacji"])
    assert "wikidata" in DATA["_zrodlo"].lower() and "wikipedi" in DATA["_zrodlo"].lower()
    assert DATA["_UWAGA_weryfikacja"].strip()
    for key, entry in DATA["miasta"].items():
        assert isinstance(entry["zweryfikowano"], bool), key
        if entry["zweryfikowano"]:  # potwierdzone musi wskazywać obiekt w Wikidata
            assert re.fullmatch(r"Q\d+", entry["wikidata"] or ""), key


def test_przyklady_z_zadania():
    cases = {
        "krakow": ["Kraków", "Krakau", "Cracovia", "Cracovie", "Cracow", "krakow"],
        "koln": ["Köln", "Cologne", "Colonia", "Cologne", "Keulen", "Kolonia", "Koeln", "koln"],
        "munchen": ["München", "Munich", "Múnich", "Munich", "Monachium", "Muenchen", "munchen"],
    }
    for key, names in cases.items():
        for name in names:
            assert find_city(name) is CITIES[key], (key, name)


# --- szukanie po aliasie ---------------------------------------------------------------------------------


def _all_search_names():
    return [(c.key, n) for c in CITIES.values() for n in c.search_names()]


def _city_only_geocoder(monkeypatch, asked):
    """Geokoder, który zna miasta tylko po nazwie lokalnej (jak realny: bez nazw alternatywnych)."""
    places = {
        fold(c.local): {
            "lat": c.lat + 0.02,
            "lon": c.lon + 0.02,
            "name": c.local,
            "type": "PLACE",
            "category": "city",
        }
        for c in CITIES.values()
    }

    def geocode(text, limit=5):
        asked.append(text)
        hit = places.get(fold(text))
        return [dict(hit)] if hit else []

    monkeypatch.setattr(motis_client, "geocode_suggestions", geocode)


@pytest.mark.parametrize("key,name", _all_search_names())
def test_wpisanie_dowolnej_nazwy_znajduje_to_samo_miasto(monkeypatch, key, name):
    asked: list[str] = []
    _city_only_geocoder(monkeypatch, asked)
    found = best_place(name)
    assert found is not None and found["name"] == CITIES[key].local, (key, name, asked)
    assert CITIES[key].local in asked  # geokoder dostał nazwę lokalną


def test_literowka_w_obcej_nazwie_tez_dziala(monkeypatch):
    asked: list[str] = []
    _city_only_geocoder(monkeypatch, asked)
    assert best_place("Monachuim")["name"] == "München"
    assert best_place("cracovie")["name"] == "Kraków"


def test_nazwa_miasta_w_adresie_i_na_poczatku_nazwy_dworca(monkeypatch):
    assert local_query("Hauptbahnhof, Cologne") == "Hauptbahnhof, Köln"
    assert local_query("Krakau Hbf") == "Kraków Hbf"
    assert local_query("Frankfurt (Oder)") == "Frankfurt (Oder)"  # to nie Frankfurt nad Menem
    assert local_query("Berliner Strasse 5, Cologne") == "Berliner Strasse 5, Köln"
    assert (
        correct_place_text("Krakowskie Przedmieście 50, Lublin")
        == "Krakowskie Przedmieście 50, Lublin"
    )
    assert local_query("Lublin") == "Lublin"


# --- wyświetlanie ----------------------------------------------------------------------------------------


def test_nazwa_w_jezyku_interfejsu_i_lokalna_obok():
    assert {lang: localize_name("Köln", lang) for lang in LANGUAGES} == {
        "pl": ("Kolonia", "Köln"),
        "en": ("Cologne", "Köln"),
        "de": ("Köln", None),
        "es": ("Colonia", "Köln"),
        "fr": ("Cologne", "Köln"),
        "nl": ("Keulen", "Köln"),
    }
    assert localize_name("München", "en") == ("Munich", "München")
    assert localize_name("München", "nl") == ("München", None)  # nl używa tej samej nazwy
    assert localize_name("Kraków", "pl") == ("Kraków", None)
    assert localize_name("Kraków", "es") == ("Cracovia", "Kraków")


def test_dworzec_z_nazwa_miasta_na_poczatku_i_adres_z_miastem():
    assert localize_name("Köln Hbf", "en") == ("Cologne Hbf", "Köln Hbf")
    assert localize_name("Kraków Główny", "de") == ("Krakau Główny", "Kraków Główny")
    assert localize_name("Hauptstraße, Köln", "nl") == ("Hauptstraße, Keulen", "Hauptstraße, Köln")
    # adres z numerem domu i nazwy bez miasta zostają bez zmian
    assert localize_name("Krakowskie Przedmieście 50, Lublin", "en")[1] is None
    assert localize_name("Miejsce (Krakowskie Przedmieście 50, Lublin)", "en")[1] is None
    assert localize_name("Gelsenkirchen Hbf", "en") == ("Gelsenkirchen Hbf", None)


def test_obca_nazwa_z_geokodera_nie_zamienia_innego_miejsca():
    # polskie "Praga" to dzielnica Warszawy, a nie Praha: podmieniamy tylko nazwy lokalne
    assert localize_name("Praga", "en") == ("Praga", None)
    assert localize_name("Praha hl.n.", "en") == ("Prague hl.n.", "Praha hl.n.")


def test_etykieta_podpowiedzi_i_zdanie_z_nazwami():
    option = {"lat": 50.9, "lon": 6.9, "name": "Köln", "type": "PLACE", "category": "city"}
    assert place_label(option, lang="en") == "🏙️  Cologne · Köln"
    assert place_label(option, lang="de") == "🏙️  Köln"
    station = {"lat": 50.9, "lon": 6.9, "name": "Köln Hbf", "type": "STOP"}
    assert place_label(station, lang="pl") == "🚉  Kolonia Hbf · Köln Hbf"
    assert place_text("Köln", "en") == "Cologne (Köln)"
    assert place_text("Berlin", "pl") == "Berlin"


def test_city_zwraca_nazwe_lokalna_gdy_brak_odrebnej():
    city = City("x", "Xtown", "PL", {"pl": "", "en": "Xtown City"}, (), False)
    assert (
        city.name("en") == "Xtown City"
        and city.name("pl") == "Xtown"
        and city.name(None) == "Xtown"
    )
    assert city.name("de") == "Xtown"


def _backend(monkeypatch):
    from datetime import UTC, datetime

    from routing.model import Itinerary, Leg, LegMode, PricedLeg
    from routing.scoring import pick_recommendations

    def fake_search(request):
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

    places = {
        "koln": {"lat": 50.94, "lon": 6.96, "name": "Köln", "type": "PLACE", "category": "city"},
        "munchen": {
            "lat": 48.14,
            "lon": 11.58,
            "name": "München",
            "type": "PLACE",
            "category": "city",
        },
    }
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [dict(places[fold(text)])] if fold(text) in places else [],
    )
    monkeypatch.setattr(search_service, "search", fake_search)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_naglowek_wyniku_pokazuje_miasta_w_jezyku_interfejsu_i_lokalne_obok(monkeypatch, lang):
    import i18n

    monkeypatch.setattr(
        i18n, "current_lang", lambda: lang
    )  # AppTest woła format_func poza skryptem
    _backend(monkeypatch)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.session_state["origin_query"] = "Cologne"  # dowolny język wpisu
    at.session_state["dest_query"] = "Monachium"
    at.button[0].click().run()
    assert not at.exception, at.exception
    request = at.session_state["search_result"]["request"]
    assert (request.origin_label, request.destination_label) == ("Köln", "München")
    header = next(m.value for m in at.markdown if "Köln" in m.value or "München" in m.value)
    for city in ("Köln", "München"):
        shown = localize_name(city, lang)[0]
        assert shown in header, (lang, shown, header)
        if shown != city:
            assert f"({city})" in header  # nazwa lokalna zostaje obok


# --- skrypt weryfikujący względem Wikidata (bez sieci) --------------------------------------------------


def _script():
    spec = importlib.util.spec_from_file_location(
        "build_place_aliases", ROOT / "scripts" / "build_place_aliases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPARQL_ANSWER = {
    "results": {
        "bindings": [
            {
                "c": {"value": "http://www.wikidata.org/entity/Q365"},
                "coord": {"value": "Point(6.957 50.938)"},
                "sl": {"value": "230"},
                "pl": {"value": "Kolonia"},
                "en": {"value": "Cologne"},
                "de": {"value": "Köln"},
                "es": {"value": "Colonia"},
                "nl": {"value": "Keulen"},
            }
        ]
    }
}


def _cand(qid, lat=None, lon=None, sitelinks=0, **labels):
    return {"qid": qid, "lat": lat, "lon": lon, "sitelinks": sitelinks, **labels}


WARSZAWA = {"local": "Warszawa", "lat": 52.23, "lon": 21.01}


def test_skrypt_buduje_zapytania_i_parsuje_odpowiedz():
    script = _script()
    query = script.build_query("Köln", "DE")
    assert '"Köln"@de' in query and "wd:Q183" in query and "wd:Q486972" in query
    assert all(f"?l_{lang}" in query for lang in LANGUAGES)
    assert "wdt:P625" in query and "wikibase:sitelinks" in query
    assert script.build_query('A"B', "PL").count('"A\\"B"@pl') == 1
    by_qid = script.build_query_by_qid("Q64")
    assert "VALUES ?c { wd:Q64 }" in by_qid and "wdt:P17" not in by_qid
    with pytest.raises(ValueError):
        script.build_query_by_qid("Q64 } DROP")
    (row,) = script.parse_bindings(SPARQL_ANSWER)
    assert row["qid"] == "Q365" and row["sitelinks"] == 230
    assert (row["lat"], row["lon"]) == (50.938, 6.957)  # WKT to (długość szerokość)
    assert row["pl"] == "Kolonia" and "fr" not in row
    assert script.parse_bindings({}) == []
    assert script.parse_bindings({"results": {"bindings": [{"c": {"value": "x/Q1"}}]}}) == [
        {"qid": "Q1", "lat": None, "lon": None, "sitelinks": 0}
    ]


def test_wybor_obiektu_jedyny_odleglosc_sitelinki_albo_reczny_wybor():
    choose = _script().choose
    assert choose(WARSZAWA, []) == (None, "brak", [])
    miasto = _cand("Q270", 52.23, 21.0, 250)
    assert choose(WARSZAWA, [miasto])[:2] == (miasto, "jedyny")
    # kilka trafień, ale tylko jedno blisko miasta z pliku
    daleko = _cand("Q1", 54.0, 18.0, 400)
    assert choose(WARSZAWA, [daleko, miasto])[:2] == (miasto, "odległość")
    # dwa blisko: wygrywa wyraźna przewaga sitelinków (>= 20 i >= 3x)
    wies = _cand("Q2", 52.2, 21.1, 12)
    assert choose(WARSZAWA, [wies, miasto])[:2] == (miasto, "sitelinki")
    # brak wyraźnej przewagi: nie zgadujemy, zwracamy kandydatów (najlepiej powiązani pierwsi)
    bliski = _cand("Q3", 52.25, 21.0, 200)
    chosen, how, options = choose(WARSZAWA, [wies, bliski, miasto])
    assert (chosen, how) == (None, "niejednoznaczne")
    assert [c["qid"] for c in options] == ["Q270", "Q3", "Q2"]
    # za mało sitelinków mimo przewagi: też ręcznie
    assert (
        choose(WARSZAWA, [_cand("Q4", 52.2, 21.0, 9), _cand("Q5", 52.2, 21.0, 2)])[1]
        == "niejednoznaczne"
    )
    # nikt nie jest blisko: oceniamy wszystkich, ale tylko wg sitelinków
    assert (
        choose(WARSZAWA, [_cand("Q6", 10.0, 10.0, 100), _cand("Q7", 11.0, 10.0, 5)])[:2][1]
        == "sitelinki"
    )
    # kandydaci bez współrzędnych nie przechodzą filtra odległości
    assert choose(WARSZAWA, [_cand("Q8"), miasto])[:2] == (miasto, "odległość")


def test_opis_kandydata_do_recznego_wyboru():
    script = _script()
    text = script.describe(WARSZAWA, _cand("Q270", 52.23, 21.0, 250, en="Warsaw"))
    assert text.startswith("Q270: Warsaw, 52.230,21.000") and "sitelinków: 250" in text
    assert "bez współrzędnych" in script.describe(WARSZAWA, _cand("Q9"))


def test_skrypt_wykrywa_rozbieznosci_i_braki():
    script = _script()
    labels = script.parse_bindings(SPARQL_ANSWER)[0]
    city = DATA["miasta"]["koln"]
    assert script.compare(city, labels) == {"mismatch": {}, "missing": {}}  # fr: brak etykiety
    wrong = json.loads(json.dumps(city))
    wrong["wyswietlana"]["en"] = "Colon"
    wrong["wyswietlana"]["nl"] = ""
    diff = script.compare(wrong, labels)
    assert diff["mismatch"] == {"en": ("Colon", "Cologne")}
    assert diff["missing"] == {"nl": "Keulen"}
    # etykieta równa nazwie lokalnej (po złożeniu) nie jest brakiem
    assert script.compare({"local": "Düsseldorf", "wyswietlana": {}}, {"de": "Dusseldorf"}) == {
        "mismatch": {},
        "missing": {},
    }


def test_wyniki_z_raportu_uzytkownika_sa_w_pliku():
    """Rozbieżności i braki z uruchomienia --check na Wikidata (2026-10-14) są poprawione."""
    miasta = DATA["miasta"]
    for key in ("katowice", "bydgoszcz", "czestochowa", "gorzow_wielkopolski"):
        entry = miasta[key]
        assert entry["wyswietlana"]["de"] == entry["local"]  # nazwa z Wikidata
    assert miasta["katowice"]["aliasy_wyszukiwania"] == ["Kattowitz"]
    assert miasta["bydgoszcz"]["aliasy_wyszukiwania"] == ["Bromberg"]
    assert miasta["czestochowa"]["aliasy_wyszukiwania"] == ["Tschenstochau"]
    assert miasta["gorzow_wielkopolski"]["aliasy_wyszukiwania"] == ["Landsberg an der Warthe"]
    assert miasta["frankfurt_am_main"]["wyswietlana"]["en"] == "Frankfurt"
    assert miasta["duisburg"]["wyswietlana"]["es"] == "Duisburgo"
    assert miasta["duisburg"]["wyswietlana"]["fr"] == "Duisbourg"


def test_dawne_nazwy_szukaja_ale_nie_sa_wyswietlane():
    for old, key in (
        ("Kattowitz", "katowice"),
        ("Bromberg", "bydgoszcz"),
        ("Tschenstochau", "czestochowa"),
        ("Landsberg an der Warthe", "gorzow_wielkopolski"),
        ("Thorn", "torun"),
        ("Oppeln", "opole"),
        ("Allenstein", "olsztyn"),
    ):
        city = CITIES[key]
        assert find_city(old) is city and local_query(old) == city.local
        for lang in LANGUAGES:
            assert old not in city.display.values() and city.name(lang) != old
    assert localize_name("Katowice", "de") == ("Katowice", None)
    for name in ("Toruń", "Opole", "Olsztyn"):
        assert localize_name(name, "de") == (name, None)


def test_kazde_miasto_ma_pola_wyswietlana_aliasy_i_wspolrzedne():
    for key, entry in DATA["miasta"].items():
        assert (
            isinstance(entry["aliasy_wyszukiwania"], list)
            and "tez" not in entry
            and "nazwy" not in entry
        ), key
        assert -90 < entry["lat"] < 90 and -180 < entry["lon"] < 180, key
        for alias in entry["aliasy_wyszukiwania"]:  # alias nie powtarza nazwy wyświetlanej
            assert alias not in entry["wyswietlana"].values(), (key, alias)


def test_frankfurt_nad_menem_nie_zjada_frankfurtu_nad_odra():
    assert local_query("Frankfurt") == "Frankfurt am Main"
    assert local_query("Frankfurt (Oder)") == "Frankfurt (Oder)"
    assert local_query("Frankfurt Oder Hbf") == "Frankfurt Oder Hbf"
    assert local_query("Frankfurt nad Menem Hbf") == "Frankfurt am Main Hbf"
    assert localize_name("Frankfurt (Oder)", "en")[1] is None


# --- sieć: ponowienia, 429, pamięć podręczna (z podmienionym requests) -------------------------------------


class _Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _script().requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._body


def _network(monkeypatch, tmp_path, answers):
    """Podmienia requests.get (kolejne odpowiedzi albo wyjątki), time.sleep (zapisuje przerwy) i cache."""
    script = _script()
    calls, sleeps = [], []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(script.requests, "get", fake_get)
    monkeypatch.setattr(script.time, "sleep", sleeps.append)
    monkeypatch.setattr(script, "CACHE_PATH", tmp_path / "cache.json")
    return script, calls, sleeps


def test_429_z_retry_after_czeka_tyle_ile_kazal_serwer(monkeypatch, tmp_path):
    script, calls, sleeps = _network(
        monkeypatch, tmp_path, [_Resp(429, headers={"Retry-After": "7"}), _Resp(200, SPARQL_ANSWER)]
    )
    assert script._sparql("Q")[0]["qid"] == "Q365"
    assert len(calls) == 2 and sleeps == [7.0, script.PAUSE_S]
    assert calls[0]["timeout"] == 90 == script.TIMEOUT_S


def test_retry_z_rosnaca_przerwa_po_timeoucie_i_5xx(monkeypatch, tmp_path):
    script = _script()
    boom = script.requests.ReadTimeout("read timed out")
    s, calls, sleeps = _network(
        monkeypatch, tmp_path, [boom, _Resp(429), _Resp(503), boom, _Resp(200, SPARQL_ANSWER)]
    )
    assert s._sparql("Q")[0]["qid"] == "Q365"
    assert len(calls) == 5  # pierwsza próba + 4 ponowienia
    assert sleeps == [5.0, 10.0, 20.0, 40.0, s.PAUSE_S]  # bez Retry-After: rosnąco


def test_po_czterech_ponowieniach_blad_idzie_wyzej_i_nie_trafia_do_cache(monkeypatch, tmp_path):
    script, calls, sleeps = _network(monkeypatch, tmp_path, [_Resp(429)])
    with pytest.raises(script.requests.HTTPError):
        script._sparql("Q")
    assert len(calls) == 5 and len(sleeps) == 4
    assert not script.CACHE_PATH.exists()


def test_inny_blad_http_nie_jest_ponawiany_a_zly_retry_after_wraca_do_rosnacej_przerwy(
    monkeypatch, tmp_path
):
    script, calls, sleeps = _network(monkeypatch, tmp_path, [_Resp(400)])
    with pytest.raises(script.requests.HTTPError):
        script._sparql("Q")
    assert len(calls) == 1 and sleeps == []
    assert script._retry_delay(_Resp(429, headers={"Retry-After": "Wed, 21 Oct"}), 1) == 10.0
    assert (
        script._retry_delay(_Resp(429, headers={"Retry-After": "9999"}), 0)
        == script.RETRY_AFTER_MAX_S
    )


def test_user_agent_opisuje_projekt_bez_danych_osob(monkeypatch, tmp_path):
    script, calls, _ = _network(monkeypatch, tmp_path, [_Resp(200, SPARQL_ANSWER)])
    script._sparql("Q")
    agent = calls[0]["headers"]["User-Agent"]
    assert "multimodal-fare-planner" in agent and "contact" in agent
    assert (
        "@" not in agent and "github.com" not in agent
    )  # ani e-maila, ani nicku z adresu repozytorium


def test_wznawianie_zapisane_zapytania_nie_ida_ponownie_do_sieci(monkeypatch, tmp_path):
    script, calls, sleeps = _network(monkeypatch, tmp_path, [_Resp(200, SPARQL_ANSWER)])
    first = script._sparql("Q1")
    assert script._sparql("Q1") == first and len(calls) == 1  # z pamięci, bez przerwy
    assert sleeps == [script.PAUSE_S]
    script._sparql("Q2")  # inne zapytanie idzie do sieci
    assert len(calls) == 2
    # nowe „uruchomienie” czyta ten sam plik: pyta tylko o brakujące
    assert set(json.loads(script.CACHE_PATH.read_text(encoding="utf-8"))) == {"Q1", "Q2"}
    script._sparql("Q1"), script._sparql("Q2")
    assert len(calls) == 2
    script.CACHE_PATH.write_text("nie json", encoding="utf-8")  # uszkodzony plik = pusta pamięć
    script._sparql("Q1")
    assert len(calls) == 3


def test_wszystkie_naglowki_i_adres_zadania_to_czyste_ascii(monkeypatch, tmp_path):
    """Regresja: UnicodeEncodeError (latin-1) w http.client.putheader przez polskie znaki w User-Agent.
    Sprawdzamy nagłówki każdego rodzaju zapytania (po nazwie z polskimi znakami i po QID) oraz gotowe
    żądanie, jakie zbuduje requests (nagłówki i adres z zakodowanymi parametrami)."""
    script, calls, _ = _network(monkeypatch, tmp_path, [_Resp(200, SPARQL_ANSWER)])
    script._sparql(script.build_query("Łódź", "PL"))
    script._sparql(script.build_query("Düsseldorf", "DE"))
    script._sparql(script.build_query_by_qid("Q1799"))
    assert len(calls) == 3
    for call in calls:
        assert call["headers"]["User-Agent"] == script.USER_AGENT
        for name, value in call["headers"].items():
            name.encode("ascii"), value.encode("ascii")
            assert all(ch.isprintable() for ch in value), (name, value)
        prepared = script.requests.Request(
            "GET", call["url"], params=call["params"], headers=call["headers"]
        ).prepare()
        prepared.url.encode("ascii")
        for name, value in prepared.headers.items():
            name.encode("ascii"), str(value).encode("ascii")
    assert "@" not in script.USER_AGENT and "github.com" not in script.USER_AGENT
