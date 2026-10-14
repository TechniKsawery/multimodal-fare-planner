"""Sprawdza na PRAWDZIWYM geokoderze MOTIS, czy nazwy miast z places/aliases.json trafiają we właściwe miejsce.

    python scripts/check_place_geocoding.py [--url http://localhost:8080]

Wymaga działającego MOTIS (scripts/run_motis.ps1 server). Dla każdego miasta z pliku i każdego z 6 języków
(PL, EN, DE, ES, FR, NL) pyta geokoder o nazwę miasta w tym języku (tak, jak wyświetla ją interfejs) i
wypisuje tabelę:

- "pierwszy kandydat": pierwszy wynik surowej odpowiedzi geokodera i jego odległość w km od lat/lon miasta
  z pliku; PROBLEM, gdy jest dalej niż CITY_RADIUS_KM (25 km) albo geokoder nic nie zwrócił - to jest
  przyczyna błędu „Toruń” (wieś o tej samej nazwie na pierwszym miejscu);
- "aplikacja": co wybierze aplikacja po wpisaniu tej nazwy bez klikania podpowiedzi (best_place, z
  filtrem promienia) i jego odległość; PROBLEM, gdy nic albo coś dalej niż 25 km.

Kod wyjścia 1, gdy w kolumnie „aplikacja” jest choć jeden PROBLEM (surowy PROBLEM geokodera sam go nie
powoduje: aplikacja ma go właśnie naprawiać)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from places.aliases import CITY_RADIUS_KM, LANGUAGES, City, load_cities  # noqa: E402
from routing import motis_client  # noqa: E402


def _describe(candidate: dict | None, city: City) -> tuple[str, float | None]:
    if candidate is None:
        return "(brak wyniku)", None
    km = motis_client.haversine_km(city.lat, city.lon, candidate["lat"], candidate["lon"])
    return f"{candidate['name']} [{candidate.get('type', '?')}]", km


def check_name(city: City, lang: str, geocode, best) -> dict:
    """Wiersz tabeli dla jednej nazwy: pierwszy kandydat geokodera i wybór aplikacji (obie funkcje
    podawane z zewnątrz, żeby dało się je podmienić w testach)."""
    query = city.name(lang)
    row = {"city": city.key, "lang": lang, "query": query}
    try:
        first = next(iter(geocode(query)), None)
        chosen = best(query)
    except motis_client.MotisError as exc:
        return {**row, "first": f"BŁĄD: {exc}", "first_km": None, "first_problem": True,
                "app": "", "app_km": None, "app_problem": True}  # fmt: skip
    row["first"], row["first_km"] = _describe(first, city)
    row["app"], row["app_km"] = _describe(chosen, city)
    row["first_problem"] = row["first_km"] is None or row["first_km"] > CITY_RADIUS_KM
    row["app_problem"] = row["app_km"] is None or row["app_km"] > CITY_RADIUS_KM
    return row


def _km(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def format_table(rows: list[dict]) -> str:
    header = (
        "miasto",
        "jęz",
        "zapytanie",
        "pierwszy kandydat",
        "km",
        "status",
        "aplikacja",
        "km",
        "status",
    )
    body = [
        (
            r["city"], r["lang"], r["query"], r["first"], _km(r["first_km"]),
            "PROBLEM" if r["first_problem"] else "ok",
            r["app"], _km(r["app_km"]), "PROBLEM" if r["app_problem"] else "ok",
        )
        for r in rows
    ]  # fmt: skip
    widths = [max(len(str(line[i])) for line in [header, *body]) for i in range(len(header))]
    lines = [
        "  ".join(str(v).ljust(w) for v, w in zip(line, widths)).rstrip()
        for line in [header, *body]
    ]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=motis_client.MOTIS_BASE_URL, help="adres MOTIS")
    args = parser.parse_args(argv)
    motis_client.MOTIS_BASE_URL = args.url
    from ui_helpers import best_place  # importuje Streamlit, więc dopiero tutaj

    rows = [
        check_name(city, lang, lambda q: motis_client.geocode_suggestions(q, limit=1), best_place)
        for city in load_cities()
        for lang in LANGUAGES
    ]
    print(format_table(rows))
    raw = sum(r["first_problem"] for r in rows)
    app = sum(r["app_problem"] for r in rows)
    print(
        f"\nPROBLEM pierwszego kandydata geokodera: {raw}/{len(rows)}; PROBLEM w aplikacji: {app}/{len(rows)}"
    )
    return 1 if app else 0


if __name__ == "__main__":
    sys.exit(main())
