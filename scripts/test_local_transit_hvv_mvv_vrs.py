"""Test weryfikacyjny (PR #49): czy MOTIS na porcie z MOTIS_BASE_URL faktycznie zwraca odcinek
lokalnego transportu w Hamburgu/Monachium/Kolonii, i czy routing/pricing.py poprawnie dopasowuje
go do kalkulatora HVV/MVV/kvb.py (zamiast fallbacku) — zarówno dla przejazdu normalnego, jak i
z Kindertarif / zniżką dla niepełnosprawnych.

Każdy leg jest wyceniany przez `routing.pricing.price_leg()` (dispatch po `leg.mode`), NIE przez
`price_bus_leg()` wprost — wcześniejsza wersja tego skryptu wołała `price_bus_leg()` dla każdego
legu niezależnie od trybu, co wyceniało też odcinki piesze (WALK) tak, jakby były autobusem/
S-Bahn, dając fałszywe "spacer kosztuje 1,75 EUR". Produkcyjna ścieżka (routing/variants.py::
_price_legs) zawsze używała poprawnego dispatchu — to był błąd tylko tego skryptu testowego, nie
routing/pricing.py.

Użycie (PowerShell, z katalogu repo głównego checkoutu):
    $env:MOTIS_BASE_URL = "http://localhost:8082"
    python scripts/test_local_transit_hvv_mvv_vrs.py

MOTIS_BASE_URL musi być ustawione PRZED importem routing.motis_client (czyta zmienną środowiskową
raz, przy imporcie modułu) — stąd ten skrypt, nie jednolinijkowe `python -c`.
"""

import sys
from datetime import date, timedelta

from fares.model import DiscountProfile
from routing import motis_client
from routing.pricing import price_leg

TEST_DATE = (date.today() + timedelta(days=1)).isoformat()
TIME = f"{TEST_DATE}T09:00:00+02:00"

CASES = [
    ("Hamburg (HVV)", "Hauptbahnhof, Hamburg", "Landungsbrücken, Hamburg", "hvv_dziecko"),
    ("Monachium (MVV)", "Marienplatz, München", "Hauptbahnhof, München", "mvv_dziecko"),
    ("Kolonia (VRS)", "Köln Hbf", "Köln Deutz", "vrs_koln_dziecko"),
]


def run_case(label: str, origin_text: str, dest_text: str, dziecko_field: str) -> None:
    print(f"=== {label} ===")
    try:
        lat1, lon1, name1 = motis_client.geocode(origin_text)
        lat2, lon2, name2 = motis_client.geocode(dest_text)
    except motis_client.MotisError as exc:
        print(f"  BŁĄD geokodowania: {exc}\n")
        return

    print(f"  {name1} -> {name2}")
    try:
        legs = motis_client.plan_leg(
            motis_client.coords_place(lat1, lon1), motis_client.coords_place(lat2, lon2), TIME
        )
    except motis_client.MotisError as exc:
        print(f"  BŁĄD planowania trasy: {exc}\n")
        return

    if not legs:
        print("  Brak odcinków w odpowiedzi MOTIS.\n")
        return

    for leg in legs:
        print(f"  Leg: {leg.carrier_name!r} ({leg.mode.value}) {leg.origin_name} -> {leg.destination_name}")
        for label_discount, discounts in [
            ("normalny", DiscountProfile()),
            (f"Kindertarif ({dziecko_field})", DiscountProfile(**{dziecko_field: True})),
            ("niepełnosprawność (Wertmarke)", DiscountProfile(schwerbehinderte_wertmarke_de=True)),
        ]:
            priced = price_leg(leg, discounts)
            print(
                f"    [{label_discount}] {priced.amount:.2f} {priced.currency} "
                f"({priced.price_type}) — {priced.notes[:80]}"
            )
    print()


def main() -> None:
    for label, origin, dest, dziecko_field in CASES:
        run_case(label, origin, dest, dziecko_field)


if __name__ == "__main__":
    sys.exit(main())
