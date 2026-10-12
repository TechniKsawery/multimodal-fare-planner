"""Ręczna kontrola bagażu podręcznego (bez UI): python scripts/check_cabin_baggage.py

Część A (offline): dla FR/W6/EW/U2/LO/LH stan, flagi, kwoty i etykieta z UI.
Część B (offline): cena odcinka lotu z bagażem podręcznym i bez niego musi być identyczna.
Część C (na żywo, tylko gdy jest TRAVELPAYOUTS_TOKEN): prawdziwe ceny dla 3 tras, to samo porównanie.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from flights import cabin_baggage as cb  # noqa: E402
from flights.model import PriceEstimate, PriceType  # noqa: E402
from routing import pricing  # noqa: E402
from routing.model import Leg, LegMode  # noqa: E402

CODES = ["FR", "W6", "EW", "U2", "LO", "LH"]


def part_a():
    print("=== A. Pola bagażu podręcznego ===")
    for code in CODES:
        info = cb.get_cabin_baggage(code)
        d = info.to_dict()
        print(f"\n[{code}] {info.airline_name}: stan={d['stan']}  price_verified={d['price_verified']}  oplaty_potwierdzone={d['oplaty_potwierdzone']}")
        print(f"  waluty dopłat: {sorted({f.currency for f in info.fees}) or '-'}  (ma być max 1)")
        for f in info.fees:
            print(f"  dopłata: {f.format()}")
        print(f"  UI: {cb.format_breakdown(d)[:300]}")


def _leg(origin, dest, date):
    now = datetime(2026, 11, 15, 6)
    return Leg(mode=LegMode.FLIGHT, origin_name=origin, destination_name=dest, depart=now, arrive=now,
               carrier_name="", distance_km=1000.0, requires_walk=False,
               extra={"origin_iata": origin, "destination_iata": dest, "depart_date": date,
                      "checked_baggage": False})


def _with_and_without(leg):
    with_cb = pricing.price_flight_leg(leg)
    real = pricing.get_cabin_baggage
    pricing.get_cabin_baggage = lambda code: cb._unknown(code, "wyłączone na potrzeby porównania")
    try:
        without_cb = pricing.price_flight_leg(leg)
    finally:
        pricing.get_cabin_baggage = real
    return with_cb, without_cb


def part_b():
    print("\n=== B. Cena przed/po (symulowany bilet 200 PLN) ===")
    ok = True
    for code in CODES:
        def fake(segment, code=code):
            return PriceEstimate("WAW", "DTM", 200.0, "PLN", PriceType.ESTIMATE,
                                 {"cena_biletu": 200.0, "linia": code, "bagaz": 0.0}, "test")
        pricing.flights_estimate_price = fake
        a, b = _with_and_without(_leg("WAW", "DTM", "2026-11-15"))
        same = a.amount == b.amount
        ok &= same
        print(f"  {code}: z bagażem={a.amount}  bez={b.amount}  stan={a.breakdown['bagaz_podreczny']['stan']}  {'OK' if same else 'RÓŻNICA!'}")
    return ok


def part_c():
    print("\n=== C. Na żywo (Travelpayouts) ===")
    if not os.getenv("TRAVELPAYOUTS_TOKEN"):
        print("  brak TRAVELPAYOUTS_TOKEN w środowisku, pomijam (ma być w .env w katalogu worktree).")
        return True
    from flights import estimate_price
    pricing.flights_estimate_price = estimate_price
    ok = True
    for o, d in [("WAW", "DUS"), ("KRK", "BER"), ("WRO", "MUC")]:
        try:
            a, b = _with_and_without(_leg(o, d, "2026-11-15"))
        except Exception as e:  # brak biletu itp.
            print(f"  {o}->{d}: błąd/brak oferty: {e}")
            continue
        same = a.amount == b.amount
        ok &= same
        bc = a.breakdown["bagaz_podreczny"]
        print(f"  {o}->{d}: linia={a.breakdown.get('linia')} cena={a.amount} (bez bagażu podręcznego {b.amount}) stan={bc['stan']} oplaty_potwierdzone={bc['oplaty_potwierdzone']} {'OK' if same else 'RÓŻNICA!'}")
    return ok


if __name__ == "__main__":
    part_a()
    ok = part_b() & part_c()
    print("\nWYNIK:", "OK, ceny bez zmian" if ok else "UWAGA: cena zależy od bagażu podręcznego!")
