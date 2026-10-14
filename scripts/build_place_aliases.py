"""Sprawdza (i uzupełnia) places/aliases.json względem Wikidata.

    python scripts/build_place_aliases.py --check   # tylko raport, plik bez zmian
    python scripts/build_place_aliases.py --write   # dopisuje QID, brakujące nazwy i oznacza miasta

Dla każdego miasta skrypt wybiera JEDEN obiekt Wikidata i porównuje jego etykiety w językach
pl/en/de/es/fr/nl z polem "wyswietlana" w pliku. Wybór obiektu:
1. jeśli w pliku jest "wikidata": "Q…" (ręczny wybór albo wynik wcześniejszego --write), pytamy wprost
   o ten obiekt;
2. inaczej szukamy obiektów, które mają etykietę równą nazwie lokalnej, są osadą (instance of podklasa
   human settlement) w odpowiednim kraju;
3. gdy trafień jest kilka, zostają te w promieniu RADIUS_KM od "lat"/"lon" miasta z pliku;
4. gdy nadal kilka: wygrywa obiekt z wyraźną przewagą sitelinków (wiki-linków; co najmniej
   SITELINK_MIN i SITELINK_RATIO razy więcej niż drugi), a raport mówi, że tak rozstrzygnięto;
5. inaczej NIE zgadujemy: skrypt wypisuje kandydatów (QID, współrzędne, odległość, sitelinki) do
   ręcznego wyboru. Wpisz wybrany QID w polu "wikidata" miasta i uruchom skrypt ponownie.

Porównanie z plikiem:
- zgodne -> miasto dostaje "zweryfikowano": true, "wikidata": "Q…" i datę w "_data_aktualizacji";
- nazwa wyświetlana w pliku inna niż etykieta Wikidata -> raport, miasto zostaje niezweryfikowane
  (nic nie nadpisujemy, decyduje człowiek);
- etykieta Wikidata, której plik nie ma (a różni się od nazwy lokalnej) -> raport, a z --write jest
  dopisywana do "wyswietlana" (źródło: Wikidata).
"aliasy_wyszukiwania" (dawne i potoczne nazwy: Kattowitz, Bromberg, Cracow) służą tylko do szukania i nie
są porównywane z Wikidata.

Skrypt wymaga dostępu do query.wikidata.org. Funkcje wyboru, parsowania i porównania pokrywa
tests/test_place_aliases.py na przykładowych odpowiedziach."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from places.aliases import DATA_PATH, LANGUAGES, fold  # noqa: E402
from routing.motis_client import haversine_km  # noqa: E402

SPARQL_URL = "https://query.wikidata.org/sparql"
# Nagłówki HTTP muszą być czysto ASCII (http.client koduje je jako latin-1): bez polskich znaków,
# myślników typograficznych i cudzysłowów; test pilnuje każdego wysyłanego nagłówka.
USER_AGENT = (
    "multimodal-fare-planner-place-aliases/1.0 "
    "(open source project: Poland-Germany journey search; contact via issues in the project repository)"
)
TIMEOUT_S = 90
PAUSE_S = 1.5  # przerwa po każdym zapytaniu do sieci
RETRIES = 4  # ponowień po pierwszej próbie
BACKOFF_S = 5.0  # przerwa przed 1. ponowieniem, potem x2 (5, 10, 20, 40 s)
RETRY_AFTER_MAX_S = 120.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
# wyniki pobranych już zapytań (poza repo): kolejne uruchomienie pyta tylko o brakujące; usuń plik, by pobrać od nowa
CACHE_PATH = Path(tempfile.gettempdir()) / "multimodalna_place_aliases_cache.json"
# kraj (kod z pliku) -> (QID kraju w Wikidata, język etykiety lokalnej)
COUNTRIES = {
    "PL": ("Q36", "pl"),
    "DE": ("Q183", "de"),
    "AT": ("Q40", "de"),
    "CZ": ("Q213", "cs"),
    "NL": ("Q55", "nl"),
}
HUMAN_SETTLEMENT = "Q486972"
RADIUS_KM = 25.0
SITELINK_MIN = 20
SITELINK_RATIO = 3.0
MAX_CANDIDATES_SHOWN = 8

_SELECT = (
    "SELECT ?c (SAMPLE(?coord) AS ?coord) (SAMPLE(?sl) AS ?sl) "
    + " ".join(f"(SAMPLE(?l_{lang}) AS ?{lang})" for lang in LANGUAGES)
    + " WHERE {\n"
)
_OPTIONALS = "\n".join(
    f'  OPTIONAL {{ ?c rdfs:label ?l_{lang} . FILTER(LANG(?l_{lang}) = "{lang}") }}'
    for lang in LANGUAGES
)
_TAIL = (
    "\n  OPTIONAL { ?c wdt:P625 ?coord }\n  OPTIONAL { ?c wikibase:sitelinks ?sl }\n"
    f"{_OPTIONALS}\n}} GROUP BY ?c"
)


def build_query(local: str, country: str) -> str:
    """Zapytanie SPARQL: osada o etykiecie `local` w języku kraju, w tym kraju, ze współrzędnymi,
    liczbą sitelinków i etykietami 6 języków."""
    country_qid, label_lang = COUNTRIES[country]
    escaped = local.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'{_SELECT}  ?c rdfs:label "{escaped}"@{label_lang} ;\n'
        f"     wdt:P17 wd:{country_qid} ;\n"
        f"     wdt:P31/wdt:P279* wd:{HUMAN_SETTLEMENT} ." + _TAIL
    )


def build_query_by_qid(qid: str) -> str:
    """To samo dla obiektu wskazanego wprost (ręczny wybór albo QID zapisany wcześniej)."""
    if not re.fullmatch(r"Q\d+", qid):
        raise ValueError(f"to nie jest QID: {qid!r}")
    return f"{_SELECT}  VALUES ?c {{ wd:{qid} }}" + _TAIL


_POINT = re.compile(r"Point\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")


def parse_bindings(response: dict) -> list[dict]:
    """Odpowiedź SPARQL -> lista {"qid", "lat", "lon", "sitelinks", "pl": "…", …}. Brak etykiety w języku
    = brak klucza; brak współrzędnych = lat/lon None."""
    out = []
    for row in response.get("results", {}).get("bindings", []):
        entry = {
            "qid": row["c"]["value"].rsplit("/", 1)[-1],
            "lat": None,
            "lon": None,
            "sitelinks": 0,
        }
        match = _POINT.match(row.get("coord", {}).get("value", ""))
        if match:  # WKT: Point(długość szerokość)
            entry["lon"], entry["lat"] = float(match.group(1)), float(match.group(2))
        if "sl" in row:
            entry["sitelinks"] = int(float(row["sl"]["value"]))
        for lang in LANGUAGES:
            if lang in row:
                entry[lang] = row[lang]["value"]
        out.append(entry)
    return out


def distance_km(city: dict, candidate: dict) -> float | None:
    if None in (city.get("lat"), city.get("lon"), candidate.get("lat"), candidate.get("lon")):
        return None
    return haversine_km(city["lat"], city["lon"], candidate["lat"], candidate["lon"])


def choose(city: dict, candidates: list[dict]) -> tuple[dict | None, str, list[dict]]:
    """Wybiera obiekt Wikidata dla miasta: (wybrany albo None, jak rozstrzygnięto, kandydaci do
    ręcznego wyboru). Powód: "jedyny", "odległość", "sitelinki" albo "niejednoznaczne"/"brak"."""
    if not candidates:
        return None, "brak", []
    if len(candidates) == 1:
        return candidates[0], "jedyny", []
    near = [c for c in candidates if (d := distance_km(city, c)) is not None and d <= RADIUS_KM]
    if len(near) == 1:
        return near[0], "odległość", []
    pool = near or candidates
    ranked = sorted(pool, key=lambda c: c["sitelinks"], reverse=True)
    top, second = ranked[0], ranked[1]
    if top["sitelinks"] >= SITELINK_MIN and top["sitelinks"] >= SITELINK_RATIO * max(
        second["sitelinks"], 1
    ):
        return top, "sitelinki", []
    return None, "niejednoznaczne", ranked


def describe(city: dict, candidate: dict) -> str:
    d = distance_km(city, candidate)
    where = (
        "bez współrzędnych"
        if d is None
        else f"{candidate['lat']:.3f},{candidate['lon']:.3f} ({d:.0f} km od miasta z pliku)"
    )
    label = candidate.get("en") or candidate.get("pl") or candidate.get("de") or "?"
    return f"{candidate['qid']}: {label}, {where}, sitelinków: {candidate['sitelinks']}"


def compare(city: dict, labels: dict) -> dict:
    """Porównanie "wyswietlana" z etykietami Wikidata: {"mismatch": {lang: (plik, wikidata)}, "missing":
    {lang: wikidata}}. Nazwa pusta w pliku przy etykiecie równej nazwie lokalnej (po złożeniu) nie jest
    brakiem: UI i tak użyje nazwy lokalnej."""
    mismatch, missing = {}, {}
    for lang in LANGUAGES:
        ours, theirs = city["wyswietlana"].get(lang, ""), labels.get(lang, "")
        if ours and theirs and ours != theirs:
            mismatch[lang] = (ours, theirs)
        elif not ours and theirs and fold(theirs) != fold(city["local"]):
            missing[lang] = theirs
    return {"mismatch": mismatch, "missing": missing}


def _retry_delay(response, attempt: int) -> float:
    """Przerwa przed ponowieniem: nagłówek Retry-After (sekundy), jeśli jest, inaczej rosnąca."""
    header = response.headers.get("Retry-After") if response is not None else None
    try:
        if header is not None:
            return min(max(float(header), 0.0), RETRY_AFTER_MAX_S)
    except ValueError:
        pass
    return BACKOFF_S * 2**attempt


def _get(query: str):
    """GET do SPARQL z ponowieniami (timeout, błąd połączenia, 429 i 5xx); błąd po ostatniej próbie idzie wyżej."""
    for attempt in range(RETRIES + 1):
        response = None
        try:
            response = requests.get(
                SPARQL_URL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=TIMEOUT_S,
            )
            if response.status_code not in RETRY_STATUSES:
                response.raise_for_status()
                return response
            error: Exception = requests.HTTPError(f"HTTP {response.status_code}", response=response)
        except (requests.Timeout, requests.ConnectionError) as exc:
            error = exc
        if attempt == RETRIES:
            raise error
        delay = _retry_delay(response, attempt)
        print(f"  {error}; ponowienie {attempt + 1}/{RETRIES} za {delay:.0f} s", file=sys.stderr)
        time.sleep(delay)
    raise AssertionError("nieosiągalne")


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sparql(query: str) -> list[dict]:
    """Wynik zapytania z pamięci podręcznej albo z sieci (po pobraniu zapisany i z przerwą PAUSE_S)."""
    cache = _load_cache()
    if query in cache:
        return cache[query]
    result = parse_bindings(_get(query).json())
    cache[query] = result
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_S)
    return result


def fetch(city: dict) -> list[dict]:
    if city.get("wikidata"):
        return _sparql(build_query_by_qid(city["wikidata"]))
    return _sparql(build_query(city["local"], city["kraj"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="tylko raport")
    mode.add_argument("--write", action="store_true", help="zapisz QID, brakujące nazwy i status")
    args = parser.parse_args(argv)

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(
        f"pamięć podręczna zapytań: {CACHE_PATH} (usuń plik, by pobrać wszystko od nowa)",
        file=sys.stderr,
    )
    manual: list[str] = []
    mismatches = 0
    for key, city in data["miasta"].items():
        found = fetch(city)
        chosen, how, options = choose(city, found)
        if chosen is None:
            manual.append(key)
            print(
                f"{key}: {how} ({len(found)} trafień), potrzebny ręczny wybór: wpisz QID w polu "
                f'"wikidata" miasta i uruchom ponownie'
            )
            for cand in options[:MAX_CANDIDATES_SHOWN]:
                print(f"    {describe(city, cand)}")
            continue
        if how in ("odległość", "sitelinki"):
            print(
                f"{key}: {len(found)} trafień, rozstrzygnięto regułą „{how}”: {describe(city, chosen)}"
            )
        diff = compare(city, chosen)
        for lang, (ours, theirs) in diff["mismatch"].items():
            print(f"{key}: {lang}: plik „{ours}” != Wikidata „{theirs}”")
        for lang, theirs in diff["missing"].items():
            print(f"{key}: {lang}: brak w pliku, Wikidata ma „{theirs}”")
        mismatches += len(diff["mismatch"])
        if args.write:
            city["wikidata"] = chosen["qid"]
            for lang, theirs in diff["missing"].items():
                city["wyswietlana"][lang] = theirs
            city["zweryfikowano"] = not diff["mismatch"]
    if args.write:
        data["_data_aktualizacji"] = date.today().isoformat()
        data["_UWAGA_weryfikacja"] = (
            f"Sprawdzone skryptem scripts/build_place_aliases.py wg Wikidata ({data['_data_aktualizacji']}). "
            "Miasta z zweryfikowano:false mają rozbieżności albo czekają na ręczny wybór obiektu (raport skryptu)."
        )
        DATA_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"zapisano {DATA_PATH}")
    print(f"do ręcznej decyzji: {len(manual)} {manual}; rozbieżności nazw: {mismatches}")
    return 1 if manual or mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
