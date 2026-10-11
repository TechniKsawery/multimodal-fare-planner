"""Kalibracja stawki fallbacku FlixBus (PLN/km) na prawdziwych cenach z API.

Uruchamiać LOKALNIE (API global.api.flixbus.com jest blokowane z chmury Claude):

    python scripts/calibrate_flixbus.py --out fares/data/flixbus_calibration.json

Dla listy tras PL-PL i PL-DE pobiera najtańszy przejazd (waluta PLN) na kilka dat w przyszłości,
liczy odległość w linii prostej (tak samo jak routing/motis_client.py — to jest distance_km, które
dostaje fares/flixbus.py) i zapisuje próbkę z datą pobrania. Statystyki: python scripts/calibrate_flixbus.py --summarize PLIK.
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fares import _flixbus_api  # noqa: E402
from routing.motis_client import haversine_km  # noqa: E402

CITIES = {
    "Lublin": (51.2465, 22.5684),
    "Warszawa": (52.2297, 21.0122),
    "Kraków": (50.0647, 19.9450),
    "Gdańsk": (54.3520, 18.6466),
    "Wrocław": (51.1079, 17.0385),
    "Poznań": (52.4064, 16.9252),
    "Szczecin": (53.4285, 14.5528),
    "Katowice": (50.2649, 19.0238),
    "Łódź": (51.7592, 19.4560),
    "Berlin": (52.5200, 13.4050),
    "Hamburg": (53.5511, 9.9937),
    "Dresden": (51.0504, 13.7373),
    "Köln": (50.9375, 6.9603),
    "München": (48.1351, 11.5820),
    "Gelsenkirchen": (51.5177, 7.0857),
    "Frankfurt": (50.1109, 8.6821),
}

ROUTES = [
    # PL-PL
    ("Warszawa", "Łódź"),
    ("Lublin", "Warszawa"),
    ("Katowice", "Kraków"),
    ("Wrocław", "Poznań"),
    ("Warszawa", "Kraków"),
    ("Warszawa", "Gdańsk"),
    ("Kraków", "Wrocław"),
    ("Lublin", "Wrocław"),
    ("Gdańsk", "Kraków"),
    ("Szczecin", "Kraków"),
    # PL-DE
    ("Poznań", "Berlin"),
    ("Wrocław", "Dresden"),
    ("Szczecin", "Berlin"),
    ("Wrocław", "Berlin"),
    ("Warszawa", "Berlin"),
    ("Lublin", "Berlin"),
    ("Kraków", "Berlin"),
    ("Gdańsk", "Hamburg"),
    ("Warszawa", "Hamburg"),
    ("Poznań", "Köln"),
    ("Lublin", "Gelsenkirchen"),
    ("Warszawa", "Köln"),
    ("Kraków", "München"),
    ("Wrocław", "Frankfurt"),
]

DATE_OFFSETS_DAYS = (14, 28, 49)


def sample(pause_s: float = 1.0) -> list[dict]:
    rows = []
    for origin, destination in ROUTES:
        km = round(haversine_km(*CITIES[origin], *CITIES[destination]), 1)
        for offset in DATE_OFFSETS_DAYS:
            travel_date = (date.today() + timedelta(days=offset)).isoformat()
            row = {
                "origin": origin,
                "destination": destination,
                "distance_km": km,
                "travel_date": travel_date,
                "fetched_on": date.today().isoformat(),
            }
            try:
                from_id = _flixbus_api.find_city_id(origin)
                to_id = _flixbus_api.find_city_id(destination)
                trip = _flixbus_api.fetch_cheapest_trip(from_id, to_id, travel_date, currency="PLN")
                row["price"] = float(trip["price"]["total"])
                row["currency"] = trip["price"].get("currency", "PLN")
                row["transfers"] = trip.get("transfer_count")
            except _flixbus_api.FlixbusApiError as exc:
                row["error"] = str(exc)[:300]
            print(row, flush=True)
            rows.append(row)
            time.sleep(pause_s)
    return rows


def summarize(path: str) -> None:
    rows = [
        r
        for r in json.loads(Path(path).read_text(encoding="utf-8"))["samples"]
        if r.get("currency") == "PLN" and r.get("price") and r["price"] > 0
    ]
    if not rows:
        print("brak poprawnych próbek w PLN")
        return
    # najtańsza cena na trasę (po datach) i mediana po datach — oba widoki
    per_km = sorted(r["price"] / r["distance_km"] for r in rows)
    n = len(per_km)
    print(f"próbek: {n}, tras: {len({(r['origin'], r['destination']) for r in rows})}")
    print(
        f"PLN/km  min {per_km[0]:.3f}  Q1 {per_km[n // 4]:.3f}  mediana {per_km[n // 2]:.3f}  "
        f"Q3 {per_km[3 * n // 4]:.3f}  max {per_km[-1]:.3f}"
    )
    # regresja price = a + b*km (OLS) — pokazuje, ile z ceny to stała opłata, a ile za km
    xs = [r["distance_km"] for r in rows]
    ys = [r["price"] for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    print(f"OLS: cena = {my - b * mx:.2f} + {b:.4f} * km")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--summarize")
    args = parser.parse_args()
    if args.summarize:
        summarize(args.summarize)
    elif args.out:
        Path(args.out).write_text(
            json.dumps(
                {
                    "_zrodlo": "https://global.api.flixbus.com/search/service/v4/search "
                    f"(nieoficjalne API), pobrane {date.today().isoformat()}, "
                    "scripts/calibrate_flixbus.py, najtanszy przejazd na trase/date.",
                    "waluta": "PLN",
                    "samples": sample(),
                },
                ensure_ascii=False,
                indent=1,
            ), encoding="utf-8"
        )
        summarize(args.out)
    else:
        parser.error("podaj --out albo --summarize")
