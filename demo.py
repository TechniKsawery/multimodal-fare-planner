"""Demo silnika optymalizacji trasy (Sesja 4): Lublin -> Gelsenkirchen.

Wymaga uruchomionego lokalnie MOTIS (scripts/run_motis.sh|ps1 server, patrz README.md).
Warianty z lotem wymagają tokena Travelpayouts w zmiennej środowiskowej TRAVELPAYOUTS_TOKEN
(patrz flights/README.md) — bez niego zostaną pominięte (SkippedVariant), ale reszta demo
i tak zadziała.

Użycie (adres -> adres, z dojściem pieszym; geocoding OSM z Sesji 4b):
    python demo.py
    python demo.py --from "Krakowskie Przedmieście 50, Lublin" --to "Bahnhofstraße, Gelsenkirchen" --date 2026-10-05
"""

import argparse

from attractions import (
    AttractionCategory,
    best_price_for_attraction,
    price_from_note,
    evaluate_city_cards,
    get_attractions,
    normalize_city,
    suggest_best_city_card,
)
from attractions import DiscountProfile as AttractionDiscountProfile
from routing.card_suggestions import suggest_bahncard_for_itinerary
from routing.demo_route import (
    FLIGHT_REGIONAL_HUBS,
    RAIL_FLIGHT_RAIL_HUBS,
    VIA_HUB_STOPS,
)
from fares.model import DiscountProfile
from routing.motis_client import MotisError
from routing.scoring import RECOMMENDATION_LABELS, pick_recommendations
from routing.variants import generate_variants, request_from_addresses

DEFAULT_FROM = "Krakowskie Przedmieście 50, Lublin"
DEFAULT_TO = "Bahnhofstraße, Gelsenkirchen"

# MOTIS ma wczytane rozkłady tylko na okno kilku tygodni od dnia importu danych (patrz
# scripts/run_motis.sh|ps1 import) — jeśli demo zwróci błąd "outside of loaded timetable
# window", zmień tę datę na jedną z aktualnego okna (błąd MOTIS podaje dokładny zakres).
DEMO_DATE = "2026-10-05"


def format_bahncard_suggestion(itinerary, age) -> str:
    suggestions = suggest_bahncard_for_itinerary(itinerary, age=age)
    if not suggestions:
        return ""
    best = suggestions[0]
    return f"  BahnCard: {best.opis}"


# Etykiety bez emoji: konsola Windows (cp1250) nie wyświetli emoji z attractions.CATEGORY_LABELS
CATEGORY_PLAIN = {
    AttractionCategory.SPORT: "sport",
    AttractionCategory.CULTURE: "turystyka i zabytki",
    AttractionCategory.ENTERTAINMENT: "rozrywka",
    AttractionCategory.GASTRONOMY: "gastronomia",
    AttractionCategory.NATURE: "natura",
}


def format_city_section(
    destination_label: str,
    profile: "AttractionDiscountProfile | None" = None,
    fallback_text: str = "",
) -> str:
    """Atrakcje i opłacalność kart miejskich dla miasta docelowego (nie wymaga MOTIS).

    Atrakcje wyróżnione (highlight) traktujemy jako zaplanowane; transport bez karty to
    szacunek (domyślnie 15 EUR / 25 PLN, jak w app.py). Ceny bez potwierdzenia są oznaczane.

    `profile`, jeśli podany (wiek/uczeń-student/senior), dla każdej atrakcji pokazuje
    najtańszą cenę, do jakiej dana osoba ma prawo z DOWOLNEGO potwierdzonego tytułu
    (nie tylko cenę dorosłego), razem z nazwą tego tytułu.
    """
    # Etykieta z geokodowania MOTIS dla konkretnego adresu (np. "Buerer Straße 8") często nie
    # zawiera miasta — wtedy używamy tekstu wpisanego przez użytkownika (--to), jak w app.py.
    city = normalize_city(destination_label) or normalize_city(fallback_text)
    if not city:
        return "Atrakcje i karty miejskie: nie rozpoznano miasta docelowego."
    attrs = get_attractions(city=city)
    if not attrs:
        return f"Atrakcje i karty miejskie: brak skatalogowanych atrakcji dla {city}."
    currency = attrs[0].currency
    transit_cost = 15.0 if currency == "EUR" else 25.0
    planned = [a for a in attrs if a.highlight]

    lines = [
        f"=== Atrakcje i karty miejskie: {city} ===",
        f"Katalog: {len(attrs)} miejsc, zaplanowane (wyróżnione) do kalkulacji: {len(planned)}",
    ]
    for a in attrs:
        price_val, label, source = best_price_for_attraction(a, profile)
        price = f"{price_val:.2f} {a.currency}" if price_val > 0 else "wstęp bezpłatny"
        if a.price_is_from:
            price = f"od {price}"
        if source is not None:
            price += f" ({label})"
            if not source.price_verified:
                price += ", cena niepotwierdzona"
        elif not a.price_verified:
            price += ", cena niepotwierdzona"
        if a.price_is_from:
            price += f" [{price_from_note(a)}]"
        lines.append(f"  - [{CATEGORY_PLAIN[a.category]}] {a.name}: {price}")

    best = suggest_best_city_card(
        city, planned, estimated_transit_cost=transit_cost, profile=profile
    )
    if best and best.is_recommended:
        lines.append(f"  Rekomendacja: {best.summary}")
    else:
        lines.append("  Rekomendacja: żadna karta miejska nie zwraca kosztu przy wyróżnionych atrakcjach.")
    for ev in evaluate_city_cards(
        city, planned, estimated_transit_cost=transit_cost, profile=profile
    ):
        verified = "" if ev.variant.price_verified else ", cena karty niepotwierdzona"
        lines.append(
            f"  - {ev.variant.name}: karta {ev.card_price:.2f} {ev.currency}, "
            f"bilans {ev.net_savings:+.2f} {ev.currency}{verified}"
        )
    lines.append(
        f"  Szacunek: transport bez karty przyjęty na {transit_cost:.2f} {currency} (stała w demo.py)."
    )
    return "\n".join(lines)


def format_itinerary(itinerary, age=None) -> str:
    lines = [
        f"  Czas podróży: {itinerary.total_duration_min / 60:.1f} h "
        f"({int(itinerary.total_duration_min)} min), przesiadek: {itinerary.num_transfers}",
        "  Cena łączna: "
        + (
            f"od {itinerary.total_price_pln:.2f} do {itinerary.total_price_pln_high:.2f} PLN "
            "(szacunek, górna granica wg cennika PKP) "
            if itinerary.total_price_pln_high is not None
            else f"{itinerary.total_price_pln:.2f} PLN "
        )
        + f"(ocena wartości: {itinerary.value_score:.0f} PLN, niżej = lepiej)",
    ]
    for priced in itinerary.legs:
        leg = priced.leg
        if leg.mode.value == "pieszo":
            meters = leg.extra.get("walk_distance_m")
            dist = f", {meters:.0f} m" if meters else ""
            lines.append(
                f"    - pieszo: {leg.origin_name} -> {leg.destination_name} "
                f"({leg.depart.strftime('%H:%M')}-{leg.arrive.strftime('%H:%M')}, {leg.duration_min:.0f} min{dist})"
            )
            continue
        line = (
            f"    - {leg.mode.value}: {leg.origin_name} -> {leg.destination_name} "
            f"({leg.depart.strftime('%H:%M')}-{leg.arrive.strftime('%H:%M')}, "
            f"{leg.carrier_name or '?'}): {priced.amount:.2f} {priced.currency} ({priced.price_type})"
        )
        if leg.mode.value == "lot" and "cena_biletu" in priced.breakdown:
            line += (
                f" [bilet {priced.breakdown['cena_biletu']:.2f} "
                f"+ bagaż {priced.breakdown.get('bagaz', 0):.2f} {priced.currency}]"
            )
            zrodlo_bagazu = priced.breakdown.get("bagaz_zrodlo")
            if zrodlo_bagazu:
                line += f"\n      bagaż wg cennika: {zrodlo_bagazu}"
        zakres = priced.breakdown.get("zakres_cen")
        if zakres:
            line += (
                f"\n      szacunek: od {zakres['od']:.2f} ({zakres['od_zrodlo']}) "
                f"do {zakres['do']:.2f} ({zakres['do_zrodlo']}) {zakres['waluta']}; "
                f"przedział SPI {zakres['spi_od']:.2f}-{zakres['spi_do']:.2f} (cennik PKP od {zakres['data_cennika']})"
            )
        alt = priced.breakdown.get("alternatywna_oferta")
        if alt:
            zrodlo = "DB Super Sparpreis Europa" if alt["zrodlo"] == "db" else "PKP Oferta Polska-Niemcy"
            line += f"\n      alternatywa: {alt['cena']:.2f} {alt['waluta']} ({zrodlo})"
        lines.append(line)
    if itinerary.is_risky:
        lines.append("  RYZYKOWNY:")
        for warning in itinerary.transfer_warnings:
            lines.append(f"    ! {warning.reason}")
    else:
        lines.append("  Przesiadki: bezpieczne (wg przyjętych minimów, patrz routing/README.md)")
    bahncard_line = format_bahncard_suggestion(itinerary, age)
    if bahncard_line:
        lines.append(bahncard_line)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wyszukiwarka tras adres -> adres")
    parser.add_argument(
        "--from", dest="origin", default=DEFAULT_FROM, help="adres startowy (z miastem)"
    )
    parser.add_argument(
        "--to", dest="destination", default=DEFAULT_TO, help="adres docelowy (z miastem)"
    )
    parser.add_argument("--date", default=DEMO_DATE, help="dzień wyjazdu YYYY-MM-DD")
    parser.add_argument(
        "--time",
        dest="departure_time",
        default="06:00",
        help="najwcześniejsza godzina wyjazdu HH:MM (czas lokalny startu, domyślnie 06:00)",
    )
    parser.add_argument(
        "--age",
        type=int,
        default=None,
        help="wiek pasażera — wpływa na podpowiedź BahnCard (My/Jugend BahnCard 6-26 lat) ORAZ "
        "na cenę biletu międzynarodowego PL-DE (dziecko do 5 lat gratis, 6-14 lat zależnie od "
        "--child-with-guardian, taryfa 'Super Sparpreis Europa Young' 15-26 lat)",
    )
    parser.add_argument(
        "--child-with-guardian",
        action="store_true",
        help="dziecko 6-14 lat (--age) podróżuje w towarzystwie osoby od 15 lat — na bilecie DB "
        "PL-DE jedzie wtedy bezpłatnie (bahn.de); bez tej flagi liczone jako samodzielne (-50%% "
        "tylko na niemiecki odcinek). Nie dotyczy oferty PKP (jej ulga dziecięca jest taka sama "
        "niezależnie od opiekuna).",
    )
    parser.add_argument(
        "--student",
        action="store_true",
        help="posiadacz ważnej legitymacji ucznia/studenta — wpływa na cenę atrakcji z potwierdzoną zniżką uczniowską/studencką",
    )
    parser.add_argument(
        "--senior",
        action="store_true",
        help="zniżka seniora — wpływa na cenę atrakcji z potwierdzoną zniżką senioralną",
    )
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="pokaż w sekcji 'wszystkie warianty' także absurdalnie wolne (domyślnie ukryte)",
    )
    args = parser.parse_args()
    attraction_profile = AttractionDiscountProfile(
        age=args.age, is_student=args.student, is_senior=args.senior
    )

    try:
        request = request_from_addresses(
            args.origin,
            args.destination,
            args.date,
            departure_time=args.departure_time if args.departure_time.count(":") == 2
            else f"{args.departure_time}:00",
            discounts=DiscountProfile(age=args.age, child_with_guardian=args.child_with_guardian),
        )
    except MotisError as exc:
        print(f"Nie udało się zgeokodować adresów: {exc}")
        return

    print(
        f"Multimodalna wyszukiwarka — {request.origin_label} -> {request.destination_label}, {args.date}\n"
    )

    print(
        format_city_section(
            request.destination_label, attraction_profile, fallback_text=args.destination
        )
    )
    print()

    # UWAGA: alternative_destination_stops (np. Essen Hbf z routing/demo_route.py) celowo NIE
    # jest tu przekazywane — dla wyszukiwania adres->adres podmieniłoby rzeczywisty adres
    # docelowy na sztywny dworzec, ucinając ostatni odcinek (pieszo/autobus/tramwaj) do adresu.
    built, skipped = generate_variants(
        request,
        rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
        flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
        via_hub_stops=VIA_HUB_STOPS,
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

    n = len(RECOMMENDATION_LABELS)
    forma = "rekomendacja" if n == 1 else "rekomendacje" if 2 <= n <= 4 else "rekomendacji"
    print(f"=== {n} {forma} ===\n")
    already_shown = set()
    for key, label in RECOMMENDATION_LABELS.items():
        itinerary = recommendations[key]
        print(f"[{label}] {itinerary.variant_name}")
        print(format_itinerary(itinerary, args.age))
        if id(itinerary) in already_shown:
            print("  (ten sam wariant wygrywa też w innej kategorii powyżej)")
        already_shown.add(id(itinerary))
        print()

    print("=== Wszystkie wygenerowane warianty ===\n")
    fastest = min(it.total_duration_min for it in built)
    hidden = []
    for itinerary in built:
        # Absurdalnie wolne warianty (>3x najszybszego i >6 h dłużej) tylko zaśmiecają wydruk.
        too_slow = (
            itinerary.total_duration_min > 3 * fastest
            and itinerary.total_duration_min - fastest > 360
        )
        if too_slow and not args.all_variants:
            hidden.append(itinerary)
            continue
        print(f"- {itinerary.variant_name}")
        print(format_itinerary(itinerary, args.age))
        print()
    if hidden:
        print(
            f"Ukryto {len(hidden)} wariant(y) absurdalnie dłuższe od najszybszego "
            "(użyj --all-variants, aby pokazać wszystkie)."
        )


if __name__ == "__main__":
    main()
