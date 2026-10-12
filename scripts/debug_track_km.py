#!/usr/bin/env python3
"""Diagnostyka: skąd bierze się cena odcinka kolejowego i które pasmo taryfy ją ustaliło.

Dla pary miast i daty pyta MOTIS (albo czyta zapisaną odpowiedź przez --fixture) i dla KAŻDEGO
odcinka transitu każdego itinerary wypisuje: przewoźnika/linię, km w linii prostej, km po torach
z obu metod osobno (legGeometry, intermediateStops), które km poszły do wyceny i skąd (legGeometry
/ stops / fallback = linia prosta), pasmo, cenę, typ ceny i - dla taryfy POLREGIO/KD/KŚ - pasmo i
cenę, jakie dałaby sama linia prosta (żeby było widać, ile zmienia km po torach).

Użycie (z katalogu głównego repo, MOTIS na http://localhost:8080 albo MOTIS_BASE_URL):
    python scripts/debug_track_km.py "Wrocław" "Kłodzko"
    python scripts/debug_track_km.py "Wrocław" "Kłodzko" --date 2026-10-17 --time 06:00
    python scripts/debug_track_km.py --fixture tests/fixtures/motis_kd_wroclaw_klodzko.json

PowerShell, jedna linia (bez pliku):
    python -c "import sys; sys.argv=['x','Wrocław','Kłodzko']; exec(open('scripts/debug_track_km.py',encoding='utf-8').read())"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path.cwd()
sys.path.insert(0, str(ROOT))

from fares import polregio  # noqa: E402
from fares.model import Carrier, DiscountProfile  # noqa: E402
from routing import motis_client, pricing  # noqa: E402
from routing.model import LegMode  # noqa: E402
from routing.variants import LOCAL_TIMEZONE  # noqa: E402

LABEL_SHORT = {
    motis_client.TRACK_KM_GEOMETRY: "legGeometry",
    motis_client.TRACK_KM_STOPS: "stops",
}


def _km(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def _candidates(raw: dict) -> tuple[float | None, float | None]:
    """(km z legGeometry, km z intermediateStops) - obie metody osobno, None gdy niedostępna."""
    out = []
    for path in (motis_client._geometry_path(raw), motis_client._stops_path(raw)):
        out.append(motis_client._path_km(path) if path else None)
    return out[0], out[1]


def _straight_line_band(km: float) -> tuple[int, float] | None:
    try:
        band = polregio._band(polregio._TABLE, km)
    except ValueError:
        return None
    return band["do_km"], band["cena"]


def describe_itinerary(itinerary: dict, discounts: DiscountProfile) -> list[str]:
    legs = motis_client.itinerary_to_legs(itinerary)
    transit_raw = [r for r in itinerary["legs"] if r["mode"] != "WALK"]
    transit = [leg for leg in legs if leg.mode is not LegMode.WALK]
    lines = []
    for raw, leg in zip(transit_raw, transit, strict=True):
        if leg.mode is LegMode.FLIGHT:
            continue
        geom_km, stops_km = _candidates(raw)
        used = leg.extra.get("distance_along_track_km")
        source = leg.extra.get("distance_along_track_source")
        priced = pricing.price_leg(leg, discounts)
        b = priced.breakdown
        carrier = priced.carrier.value if priced.carrier else "brak modułu (fallback km)"
        lines.append(
            f"  {leg.depart:%H:%M}-{leg.arrive:%H:%M} {leg.carrier_name or '?'} "
            f"[{raw.get('routeShortName') or '-'}] mode={raw['mode']}  "
            f"{leg.origin_name} -> {leg.destination_name}"
        )
        lines.append(
            f"      km linia prosta: {_km(leg.distance_km)} | intermediateStops w odp.: "
            f"{len(raw.get('intermediateStops') or [])} | legGeometry w odp.: "
            f"{'tak' if (raw.get('legGeometry') or {}).get('points') else 'nie'}"
        )
        lines.append(
            f"      km po torach: legGeometry={_km(geom_km)} stops={_km(stops_km)} -> do wyceny: "
            f"{_km(used)} (źródło: {LABEL_SHORT.get(source, source) if used else 'fallback: linia prosta'})"
        )
        pasmo = b.get("pasmo_do_km")
        lines.append(
            f"      taryfa: {carrier} | pasmo: {'do ' + str(pasmo) + ' km' if pasmo else '-'} | "
            f"cena: {priced.amount:.2f} {priced.currency} | typ: {priced.price_type} | "
            f"potwierdzona: {'tak' if priced.price_verified else 'NIE'} | "
            f"odległość taryfowa: {b.get('odleglosc_taryfowa', '-')}"
        )
        if priced.carrier is Carrier.POLREGIO_PODSTAWOWA and leg.distance_km is not None:
            line = _straight_line_band(leg.distance_km)
            if line and line[0] != pasmo:
                lines.append(
                    f"      z samej linii prostej ({leg.distance_km:.1f} km) byłoby pasmo do "
                    f"{line[0]} km = {line[1]:.2f} zł"
                )
            elif line:
                lines.append("      linia prosta dałaby to samo pasmo")
        if priced.carrier is None or not priced.price_verified:
            lines.append(f"      uwaga: {priced.notes[:200]}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("origin", nargs="?", help="miasto/stacja początkowa")
    ap.add_argument("destination", nargs="?", help="miasto/stacja końcowa")
    ap.add_argument("--date", default="2026-10-17", help="YYYY-MM-DD (domyślnie 2026-10-17)")
    ap.add_argument("--time", default="06:00", help="HH:MM, czas odjazdu (domyślnie 06:00)")
    ap.add_argument("--fixture", help="zapisana odpowiedź MOTIS (JSON) zamiast zapytania na żywo")
    ap.add_argument("--ulga", default="brak", help="kod ulgi PKP (domyślnie brak = cena normalna)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    discounts = DiscountProfile(pkp_ulga_kod=args.ulga)
    if args.fixture:
        data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        itineraries = data.get("itineraries") or [data]
        print(f"Fixture: {args.fixture} (odpowiedź zapisana, nie z żywego MOTIS)")
    else:
        if not (args.origin and args.destination):
            ap.error("podaj miasto początkowe i końcowe albo --fixture")
        try:
            lat1, lon1, name1 = motis_client.geocode(args.origin)
            lat2, lon2, name2 = motis_client.geocode(args.destination)
        except motis_client.MotisError as exc:
            print(f"BŁĄD MOTIS: {exc}", file=sys.stderr)
            return 2
        local = datetime.fromisoformat(f"{args.date}T{args.time}").replace(tzinfo=LOCAL_TIMEZONE)
        when = local.isoformat()
        print(f"MOTIS {motis_client.MOTIS_BASE_URL}: {name1} -> {name2}, odjazd od {when}")
        try:
            payload = motis_client.plan(
                motis_client.coords_place(lat1, lon1),
                motis_client.coords_place(lat2, lon2),
                when,
                max_transfers=5,
                num_itineraries=motis_client.MAIN_QUERY_ITINERARIES,
            )
        except motis_client.MotisError as exc:
            print(f"BŁĄD MOTIS: {exc}", file=sys.stderr)
            return 2
        itineraries = motis_client._all_itineraries(payload)

    for i, itinerary in enumerate(itineraries, 1):
        print(
            f"\nItinerary {i}: {itinerary.get('duration', 0) // 60} min, "
            f"przesiadki: {itinerary.get('transfers', '?')}"
        )
        body = describe_itinerary(itinerary, discounts)
        print("\n".join(body) if body else "  (brak odcinków transitu)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
