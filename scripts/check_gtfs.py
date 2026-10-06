#!/usr/bin/env python3
"""Podstawowa walidacja feedów GTFS: czy zip jest cały, wymagane pliki, liczby wierszy,
zakres dat kalendarza i spójność kluczy (trips->routes, stop_times->stops/trips)."""

import csv
import io
import sys
import zipfile

REQUIRED = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]


def rows(z, name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"))


def check(path):
    ok = True
    print(f"\n### {path}")
    z = zipfile.ZipFile(path)
    bad = z.testzip()
    if bad:
        print(f"  BŁĄD: uszkodzony plik w archiwum: {bad}")
        return False
    names = set(z.namelist())
    for r in REQUIRED:
        if r not in names:
            print(f"  BŁĄD: brak {r}")
            ok = False
    if not ({"calendar.txt", "calendar_dates.txt"} & names):
        print("  BŁĄD: brak calendar.txt i calendar_dates.txt")
        ok = False
    if not ok:
        return False

    stops = {r["stop_id"] for r in rows(z, "stops.txt")}
    routes = {r["route_id"] for r in rows(z, "routes.txt")}
    trips, bad_route = set(), 0
    for r in rows(z, "trips.txt"):
        trips.add(r["trip_id"])
        bad_route += r["route_id"] not in routes
    n_st = bad_stop = bad_trip = 0
    for r in rows(z, "stop_times.txt"):
        n_st += 1
        bad_stop += r["stop_id"] not in stops
        bad_trip += r["trip_id"] not in trips

    dates = []
    if "calendar.txt" in names:
        for r in rows(z, "calendar.txt"):
            dates += [r["start_date"], r["end_date"]]
    if "calendar_dates.txt" in names:
        dates += [r["date"] for r in rows(z, "calendar_dates.txt")]

    agencies = [r.get("agency_name", "") for r in rows(z, "agency.txt")]
    print(
        f"  przewoźnicy: {len(agencies)} ({', '.join(agencies[:8])}{'…' if len(agencies) > 8 else ''})"
    )
    print(
        f"  przystanki: {len(stops)}, linie: {len(routes)}, kursy: {len(trips)}, stop_times: {n_st}"
    )
    print(f"  zakres dat: {min(dates) if dates else '?'} – {max(dates) if dates else '?'}")
    for label, n in [
        ("trips bez route", bad_route),
        ("stop_times bez stop", bad_stop),
        ("stop_times bez trip", bad_trip),
    ]:
        if n:
            print(f"  BŁĄD: {label}: {n}")
            ok = False
    print("  OK" if ok else "  NIEPOPRAWNY")
    return ok


if __name__ == "__main__":
    results = [check(p) for p in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
