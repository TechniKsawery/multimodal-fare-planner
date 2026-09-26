"""Demo silnika optymalizacji trasy (Sesja 4): Lublin -> Gelsenkirchen.

Wymaga uruchomionego lokalnie MOTIS (scripts/run_motis.sh|ps1 server, patrz README.md).
Warianty z lotem wymagają tokena Travelpayouts w zmiennej środowiskowej TRAVELPAYOUTS_TOKEN
(patrz flights/README.md) — bez niego zostaną pominięte (SkippedVariant), ale reszta demo
i tak zadziała.

Użycie:
    python demo.py
"""
from routing.demo_route import (
    FLIGHT_REGIONAL_HUBS,
    RAIL_FLIGHT_RAIL_HUBS,
    lublin_gelsenkirchen_request,
)
from routing.scoring import RECOMMENDATION_LABELS, pick_recommendations
from routing.variants import generate_variants

# MOTIS ma wczytane rozkłady tylko na okno kilku tygodni od dnia importu danych (patrz
# scripts/run_motis.sh|ps1 import) — jeśli demo zwróci błąd "outside of loaded timetable
# window", zmień tę datę na jedną z aktualnego okna (błąd MOTIS podaje dokładny zakres).
DEMO_DATE = "2026-10-05"


def format_itinerary(itinerary) -> str:
    lines = [
        f"  Czas podróży: {itinerary.total_duration_min / 60:.1f} h "
        f"({int(itinerary.total_duration_min)} min), przesiadek: {itinerary.num_transfers}",
        f"  Cena łączna: {itinerary.total_price_pln:.2f} PLN "
        f"(cena/godz.: {itinerary.price_per_hour:.1f} PLN/h)",
    ]
    for priced in itinerary.legs:
        leg = priced.leg
        lines.append(
            f"    - {leg.mode.value}: {leg.origin_name} -> {leg.destination_name} "
            f"({leg.depart.strftime('%H:%M')}-{leg.arrive.strftime('%H:%M')}, "
            f"{leg.carrier_name or '?'}): {priced.amount:.2f} {priced.currency} ({priced.price_type})"
        )
    if itinerary.is_risky:
        lines.append("  RYZYKOWNY:")
        for warning in itinerary.transfer_warnings:
            lines.append(f"    ! {warning.reason}")
    else:
        lines.append("  Przesiadki: bezpieczne (wg przyjętych minimów, patrz routing/README.md)")
    return "\n".join(lines)


def main() -> None:
    print(f"Multimodalna wyszukiwarka — Lublin -> Gelsenkirchen, {DEMO_DATE}\n")

    request = lublin_gelsenkirchen_request(DEMO_DATE)
    built, skipped = generate_variants(
        request,
        rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
        flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
    )

    print(f"Zbudowano {len(built)} wariant(y), pominięto {len(skipped)}.\n")
    for skip in skipped:
        print(f"  [pominięty] {skip.variant_name}: {skip.reason}")
    if skipped:
        print()

    if not built:
        print("Brak żadnego działającego wariantu — sprawdź, czy MOTIS jest uruchomiony.")
        return

    recommendations = pick_recommendations(built)

    print("=== 4 rekomendacje ===\n")
    already_shown = set()
    for key, label in RECOMMENDATION_LABELS.items():
        itinerary = recommendations[key]
        print(f"[{label}] {itinerary.variant_name}")
        print(format_itinerary(itinerary))
        if id(itinerary) in already_shown:
            print("  (ten sam wariant wygrywa też w innej kategorii powyżej)")
        already_shown.add(id(itinerary))
        print()

    print("=== Wszystkie wygenerowane warianty ===\n")
    for itinerary in built:
        print(f"- {itinerary.variant_name}")
        print(format_itinerary(itinerary))
        print()


if __name__ == "__main__":
    main()
