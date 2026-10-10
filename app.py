"""Frontend Streamlit (Sesja 5): ten sam pipeline co demo.py, w przeglądarce.

Uruchomienie:  pip install streamlit  &&  streamlit run app.py
Wymaga działającego MOTIS (localhost:8080), patrz README.md.
"""

import datetime as dt
import json

import streamlit as st

from attractions import (
    CATEGORY_LABELS,
    AttractionCategory,
    evaluate_city_cards,
    get_attractions,
    get_city_cards,
    normalize_city,
    suggest_best_city_card,
)
from demo import DEFAULT_FROM, DEFAULT_TO, DEMO_DATE
from fares.model import DiscountProfile
from routing import motis_client
from routing.card_suggestions import db_distance_km, suggest_bahncard_for_itinerary
from routing.motis_client import MotisError
from routing.scoring import RECOMMENDATION_LABELS, SAFE_CATEGORY_KEYS, TOP_CATEGORY_KEYS
from routing.search_service import search
from routing.variants import RouteRequest

with open("fares/data/pkp_intercity.json", encoding="utf-8") as fh:
    PKP_ULGI = list(json.load(fh)["ulgi_procent"])

st.set_page_config(page_title="Multimodalna wyszukiwarka", layout="wide")
st.title("Multimodalna wyszukiwarka tras")

# Czysto kosmetyczne rozróżnienie w UI (nie wpływa na progi z routing/transfers.py ani na
# scoring/kategoryzację "bezpieczna"): przesiadka, której brakuje do progu bezpieczeństwa
# tylko odrobinę, dostaje łagodniejszą adnotację "prawie bezpieczna" zamiast zwykłego
# ostrzeżenia o ryzykownej przesiadce.
NEAR_MISS_MARGIN_MINUTES = 10


def _is_near_miss(warning) -> bool:
    if warning.infeasible:
        return False
    shortfall = warning.minimum_required_minutes - warning.gap_minutes
    return 0 < shortfall <= NEAR_MISS_MARGIN_MINUTES


def _is_near_miss_itinerary(it) -> bool:
    """True, gdy wariant jest ryzykowny WYŁĄCZNIE przez przesiadki tuż poniżej progu — nie przez
    próg oblany z dużym zapasem."""
    risky = [w for w in it.transfer_warnings if not w.infeasible]
    return bool(risky) and all(_is_near_miss(w) for w in risky)


def render_itinerary(it, wiek=None, posiadana_bahncard=None) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Czas podróży", f"{it.total_duration_min / 60:.1f} h")
    c2.metric("Cena łączna", f"{it.total_price_pln:.2f} PLN")
    c3.metric("Przesiadki", it.num_transfers)
    rows = []
    for p in it.legs:
        leg = p.leg
        if leg.mode.value == "pieszo":
            m = leg.extra.get("walk_distance_m")
            price = f"{m:.0f} m" if m else ""
        else:
            price = f"{p.amount:.2f} {p.currency} ({p.price_type})"
        rozbicie = ""
        zrodlo_bagazu = ""
        if leg.mode.value == "lot" and "cena_biletu" in p.breakdown:
            rozbicie = (
                f"bilet {p.breakdown['cena_biletu']:.2f} "
                f"+ bagaż {p.breakdown.get('bagaz', 0):.2f} {p.currency}"
            )
            zrodlo_bagazu = p.breakdown.get("bagaz_zrodlo", "")
        rows.append(
            {
                "Środek": leg.mode.value,
                "Połączenie": (
                    leg.extra.get("route_short_name") or ""
                    if leg.mode.value in ("kolej", "autobus")
                    else ""
                ),
                "Trasa": f"{leg.origin_name} → {leg.destination_name}",
                "Godziny": f"{leg.depart:%H:%M}–{leg.arrive:%H:%M} ({leg.duration_min:.0f} min)",
                "Przewoźnik": leg.carrier_name or "",
                "Cena / dystans": price,
                "Rozbicie ceny lotu": rozbicie,
                "Cennik bagażu": zrodlo_bagazu,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    if it.is_risky:
        for w in it.transfer_warnings:
            if w.infeasible:
                continue
            if _is_near_miss(w):
                stacja = it.legs[w.after_leg_index].leg.destination_name
                shortfall = w.minimum_required_minutes - w.gap_minutes
                st.info(
                    f"🟡 Prawie bezpieczna przesiadka w {stacja} — brakuje {shortfall:.0f} min "
                    f"do progu bezpieczeństwa ({w.gap_minutes:.0f} z wymaganych "
                    f"{w.minimum_required_minutes:.0f} min)."
                )
            else:
                st.warning(f"Ryzykowna przesiadka: {w.reason}")
    else:
        st.success("Przesiadki: bezpieczne (wg przyjętych minimów)")

    if db_distance_km(it) <= 0:
        st.caption(
            "💳 Ten wariant nie zawiera odcinka DB (kolej niemiecka) — BahnCard nie ma tu zastosowania."
        )
    else:
        suggestions = suggest_bahncard_for_itinerary(
            it, age=wiek, existing_bahncard=posiadana_bahncard
        )
        if suggestions:
            best = suggestions[0]
            if best.rekomendowana:
                st.info(f"💳 {best.opis}")
            else:
                st.caption(f"💳 {best.opis}")
        elif posiadana_bahncard:
            st.caption(
                f"💳 Masz już BahnCard {posiadana_bahncard} — cena w tabeli wyżej już ją uwzględnia; "
                f"żadna inna karta nie da tu lepszego rabatu."
            )


def render_attractions_and_city_cards(destination_label: str, fallback_text: str = "") -> None:
    # destination_label pochodzi z podpowiedzi geocodingu MOTIS i dla konkretnego adresu
    # (np. "Buerer Straße 8") często NIE zawiera nazwy miasta, więc normalize_city się nie
    # trafia — spada wtedy na fallback_text, czyli surowy tekst wpisany w pole "Dokąd (adres)"
    # (zwykle z miastem, np. "Buerer Straße 8, Gelsenkirchen").
    norm_city = normalize_city(destination_label) or normalize_city(fallback_text)
    if not norm_city:
        return

    city_names = {
        "gelsenkirchen": "Gelsenkirchen & Zagłębie Ruhry",
        "berlin": "Berlin",
        "krakow": "Kraków",
        "lublin": "Lublin",
        "warszawa": "Warszawa",
    }
    display_city = city_names.get(norm_city, norm_city.capitalize())

    st.markdown("---")
    st.header(f"🏛️ Miejsca warte odwiedzenia i zniżki: {display_city}")
    st.caption(
        "Wybierz interesujące Cię kategorie miejsc (np. stadiony sportowe, zabytki) "
        "i sprawdź, czy dedykowana Karta Miejska (City Card) pozwoli Ci zaoszczędzić na wstępach i komunikacji."
    )

    all_city_attrs = get_attractions(city=norm_city)
    if not all_city_attrs:
        st.info(f"Brak skatalogowanych atrakcji dla: {display_city}.")
        return

    # Filtrowanie kategorii
    cat_options = ["Wszystkie"] + [cat.value for cat in AttractionCategory]
    cat_labels = {"Wszystkie": "Wszystkie kategorie"}
    cat_labels.update({cat.value: CATEGORY_LABELS[cat] for cat in AttractionCategory})

    selected_cat = st.selectbox(
        "Filtruj wg kategorii",
        options=cat_options,
        format_func=lambda c: cat_labels.get(c, c),
        key="attr_cat_filter",
    )

    filtered_attrs = (
        all_city_attrs
        if selected_cat == "Wszystkie"
        else [a for a in all_city_attrs if a.category.value == selected_cat]
    )

    # Wybór planowanych atrakcji do kalkulatora karty
    attr_names = [a.name for a in all_city_attrs]
    default_selected = [a.name for a in all_city_attrs if a.highlight]

    st.subheader("Zaplanuj wizytę")
    chosen_names = st.multiselect(
        "Zaznacz miejsca, które planujesz odwiedzić (posłużą do kalkulacji opłacalności karty):",
        options=attr_names,
        default=default_selected,
        key="chosen_attractions",
    )
    chosen_objects = [a for a in all_city_attrs if a.name in chosen_names]

    # Kalkulator City Card
    cards = get_city_cards(norm_city)
    if cards:
        st.subheader("💳 Analiza opłacalności Karty Miejskiej")
        default_transit_cost = 15.0 if all_city_attrs[0].currency == "EUR" else 25.0
        transit_cost = st.number_input(
            f"Szacowany wydatek na komunikację miejską bez karty ({all_city_attrs[0].currency})",
            min_value=0.0,
            value=default_transit_cost,
            step=5.0,
            key="transit_est_cost",
            help="Jeśli karta miejska zawiera nielimitowany transport, ten koszt odpada i staje się Twoją oszczędnością.",
        )

        best_eval = suggest_best_city_card(
            norm_city, chosen_objects, estimated_transit_cost=transit_cost
        )
        if best_eval and best_eval.is_recommended:
            st.success(f"🎉 **Rekomendacja:** {best_eval.summary}")
        elif chosen_objects:
            st.info(
                f"ℹ️ Przy obecnie wybranych {len(chosen_objects)} atrakcjach zakup karty miejskiej nie jest jeszcze optymalny. "
                "Poniżej znajdziesz porównanie wszystkich dostępnych wariantów."
            )

        evals = evaluate_city_cards(norm_city, chosen_objects, estimated_transit_cost=transit_cost)
        if evals:
            card_rows = []
            for ev in evals:
                card_rows.append(
                    {
                        "Karta / Wariant": ev.variant.name,
                        "Cena karty": f"{ev.card_price:.2f} {ev.currency}"
                        + ("" if ev.variant.price_verified else " (niepotwierdzona)"),
                        "Ważność": f"{ev.variant.duration_hours}h",
                        "Darmowy transport": "Tak" if ev.variant.includes_public_transit else "Nie",
                        "Koszt bez karty": f"{ev.total_cost_without_card:.2f} {ev.currency}",
                        "Koszt z kartą": f"{ev.total_cost_with_card:.2f} {ev.currency}",
                        "Bilans": (
                            f"+{ev.net_savings:.2f} {ev.currency} (zysk)"
                            if ev.net_savings > 0
                            else f"{ev.net_savings:.2f} {ev.currency}"
                        ),
                        "Rekomendowana": "✅ Tak" if ev.is_recommended else "❌ Nie",
                    }
                )
            st.dataframe(card_rows, width="stretch", hide_index=True)

    # Prezentacja listy atrakcji w wybranej kategorii
    st.subheader(f"Miejsca w kategorii: {cat_labels.get(selected_cat, selected_cat)}")
    cols = st.columns(2)
    for idx, attr in enumerate(filtered_attrs):
        col = cols[idx % 2]
        with col:
            price_text = (
                f"{attr.normal_price:.2f} {attr.currency}"
                if attr.normal_price > 0
                else "Wstęp bezpłatny"
            )
            if not attr.price_verified:
                price_text += " (cena niepotwierdzona)"
            discount_note = (
                f" • zniżka z kartą: do {attr.default_card_discount_percent:.0f}%"
                if attr.default_card_discount_percent > 0
                else ""
            )
            with st.container(border=True):
                st.markdown(f"**{attr.name}**")
                st.caption(
                    f"{CATEGORY_LABELS.get(attr.category, attr.category.value)} • {price_text}{discount_note}"
                )
                st.write(attr.description)
                if attr.address:
                    st.caption(f"📍 {attr.address}")
                if attr.official_url:
                    st.markdown(f"[Strona oficjalna]({attr.official_url})")


def address_picker(label: str, default_text: str, state_key: str):
    """Pole adresu + podpowiedzi z geocodingu MOTIS do wyboru (zamiast wpisywania z palca
    na ślepo — literówka w mieście/ulicy dotąd potrafiła po cichu trafić w zły punkt)."""
    query = st.text_input(label, value=default_text, key=f"{state_key}_query")
    if len(query.strip()) < 3:
        st.caption("Wpisz co najmniej 3 znaki, żeby zobaczyć podpowiedzi.")
        return None
    try:
        suggestions = motis_client.geocode_suggestions(query)
    except MotisError as exc:
        st.caption(f"Podpowiedzi niedostępne: {exc}")
        return None
    if not suggestions:
        st.caption("Brak dopasowań — sprawdź pisownię albo dodaj nazwę miasta.")
        return None
    idx = st.selectbox(
        f"Wybierz dokładny adres ({label.lower()})",
        options=list(range(len(suggestions))),
        format_func=lambda i: suggestions[i]["name"],
        key=f"{state_key}_choice",
    )
    return suggestions[idx]


wiek = st.number_input(
    "Wiek pasażera",
    min_value=0,
    max_value=120,
    value=30,
    step=1,
    help="Używany tylko do PODPOWIEDZI zniżek zależnych od wieku (VRR Kindertarif 6-14 lat, "
    "ZTM Lublin ulgowy). Checkboxy niżej możesz zawsze nadpisać ręcznie — np. dorosły "
    "uczeń/student ma bilet ulgowy niezależnie od wieku, a wiek sam z siebie nie daje "
    "pełnego obrazu uprawnień.",
)

st.subheader("Skąd i dokąd")
c_origin, c_dest = st.columns(2)
with c_origin:
    origin_resolved = address_picker("Skąd (adres)", DEFAULT_FROM, "origin")
with c_dest:
    dest_resolved = address_picker("Dokąd (adres)", DEFAULT_TO, "dest")

with st.form("search"):
    date = st.date_input("Data", dt.date.fromisoformat(DEMO_DATE))
    c1, c2 = st.columns(2)
    pkp = c1.selectbox("Ulga PKP", PKP_ULGI)
    bc = c2.selectbox("BahnCard", ["brak", "25", "50", "100"])
    c3, c4 = st.columns(2)
    ztm_ulgowy = c3.checkbox(
        "Bilet ulgowy ZTM Lublin",
        value=wiek < 18,
        help="Podpowiedź wg wieku (<18 lat) — zaznacz też ręcznie, jeśli masz ulgę z innego "
        "tytułu (uczeń, student, senior, niepełnosprawność), niezależnie od wieku.",
    )
    vrr_dziecko = c4.checkbox(
        "Taryfa dziecięca VRR (Kindertarif)",
        value=6 <= wiek <= 14,
        help="Oficjalna zniżka VRR: 50% dla dzieci 6-14 lat, ściśle wg wieku.",
    )
    st.caption("Bilety ulgowe w innych miastach (50% — zaznacz, jeśli dotyczy)")
    u1, u2, u3, u4, u5 = st.columns(5)
    ztm_warszawa_ulgowy = u1.checkbox("Warszawa", value=wiek < 18)
    mpk_krakow_ulgowy = u2.checkbox("Kraków", value=wiek < 18)
    ztm_poznan_ulgowy = u3.checkbox("Poznań", value=wiek < 18)
    mpk_wroclaw_ulgowy = u4.checkbox("Wrocław", value=wiek < 18)
    bvg_berlin_ulgowy = u5.checkbox("Berlin", value=wiek < 18)
    st.caption(
        "Przejazdy bezpłatne (100%, inna kategoria niż ulgowy — ma priorytet nad checkboxem "
        "ulgowy tego miasta wyżej, jeśli zaznaczone)"
    )
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    ztm_warszawa_bezplatny = b1.checkbox(
        "Warszawa: uczeń/senior 70+/niepełnosprawność znaczna",
        value=wiek >= 70,
        help="Karta Ucznia (tylko szkoła podstawowa, NIE ponadpodstawowa); osoby 70+ (bez wymogu"
        " zamieszkania); niepełnosprawność ZNACZNA 26+ (UWAGA: 'umiarkowana' to tylko ulgowy"
        " 50%, nie ta kategoria).",
    )
    mpk_krakow_bezplatny = b2.checkbox(
        "Kraków: uczeń/senior 70+/niepełnosprawność znaczna",
        value=wiek >= 70,
        help="Uczniowie podstawówek z Krakowa/Metropolii (NIE ponadpodstawowe); osoby 70+ (bez"
        " wymogu zamieszkania); niepełnosprawność ZNACZNA, lub UMIARKOWANA tylko przy symbolach"
        " 04-O/05-R/10-N/01-U (inaczej to tylko ulgowy 50%).",
    )
    mpk_wroclaw_bezplatny = b3.checkbox(
        "Wrocław: uczeń/dziecko/senior",
        value=wiek <= 7 or wiek <= 21 or wiek >= 65,
        help="Jedna kategoria 100% w naszych danych obejmuje kilka tytułów potwierdzonych na"
        " wroclaw.pl: uczniowie szkół podstawowych/ponadpodstawowych do 21 lat, dzieci do 7 lat"
        " i seniorzy 65+ (bez wymogu zamieszkania we Wrocławiu). Inne potwierdzone tytuły z tej"
        " samej kategorii (niepełnosprawność, rodziny wielodzietne itd.) zaznacz też tutaj,"
        " niezależnie od wieku.",
    )
    ztm_lublin_bezplatny = b4.checkbox(
        "Lublin: uczeń podstawówki",
        help="Uczniowie szkół podstawowych (gmina Lublin) — NIE potwierdzone dla"
        " ponadpodstawowych (licea), tam zostaje ulgowy 50%.",
    )
    ztm_poznan_bezplatny = b5.checkbox(
        "Poznań: senior 70+/niepełnosprawność znaczna",
        value=wiek >= 70,
        help="W Poznaniu NIE ma bezpłatnego dla zwykłych uczniów (tylko ulgowy 50%), ale JEST dla"
        " osób 70+ (bez wymogu zamieszkania) i niepełnosprawności znacznej/I grupy — bez dolnej"
        " granicy wieku 26 lat, inaczej niż w Warszawie/Krakowie.",
    )
    bvg_berlin_schwerbehindert = b6.checkbox(
        "Berlin: Schwerbehindertenausweis + Wertmarke",
        help="Bezpłatne w Berlinie TYLKO z legitymacją niepełnosprawności (Merkzeichen G/aG/H/Bl)"
        " ORAZ osobno wykupioną Wertmarke (ok. 104 EUR/rok) — samo orzeczenie (nawet GdB 50) nie"
        " wystarcza. Nie zaznaczaj bez obu dokumentów naraz. Brak w Berlinie ulgi wiekowej dla"
        " seniorów (65+ to płatny abonament VBB-Abo 65plus, nie modelowany tutaj).",
    )
    submitted = st.form_submit_button("Szukaj")

if submitted:
    if origin_resolved is None or dest_resolved is None:
        st.error("Wybierz dokładny adres z podpowiedzi (skąd i dokąd) przed wyszukiwaniem.")
        st.stop()
    profile = DiscountProfile(
        pkp_ulga_kod=pkp,
        bahncard=None if bc == "brak" else bc,
        ztm_lublin_ulgowy=ztm_ulgowy,
        ztm_lublin_bezplatny=ztm_lublin_bezplatny,
        ztm_warszawa_ulgowy=ztm_warszawa_ulgowy,
        ztm_warszawa_bezplatny=ztm_warszawa_bezplatny,
        mpk_krakow_ulgowy=mpk_krakow_ulgowy,
        mpk_krakow_bezplatny=mpk_krakow_bezplatny,
        ztm_poznan_ulgowy=ztm_poznan_ulgowy,
        ztm_poznan_bezplatny=ztm_poznan_bezplatny,
        mpk_wroclaw_ulgowy=mpk_wroclaw_ulgowy,
        mpk_wroclaw_bezplatny=mpk_wroclaw_bezplatny,
        bvg_berlin_ulgowy=bvg_berlin_ulgowy,
        bvg_berlin_schwerbehindert=bvg_berlin_schwerbehindert,
        vrr_dziecko=vrr_dziecko,
        age=wiek,
    )
    try:
        with st.spinner("Szukam połączeń..."):
            request = RouteRequest(
                origin_stop_id=motis_client.coords_place(
                    origin_resolved["lat"], origin_resolved["lon"]
                ),
                destination_stop_id=motis_client.coords_place(
                    dest_resolved["lat"], dest_resolved["lon"]
                ),
                origin_label=origin_resolved["name"],
                destination_label=dest_resolved["name"],
                date=date.isoformat(),
                discounts=profile,
            )
            # search() (routing/search_service.py, współdzielone z API w api/) nie przekazuje
            # alternative_destination_stops — patrz komentarz tam / w demo.py (podmieniłoby
            # rzeczywisty adres docelowy na sztywny dworzec, ucinając ostatni odcinek do adresu).
            search_result = search(request)
            built, skipped, recs = (
                search_result.built,
                search_result.skipped,
                search_result.recommendations,
            )
    except MotisError as exc:
        st.error(f"Błąd MOTIS / geokodowania: {exc}")
        st.stop()
    except Exception as exc:  # np. MOTIS nieuruchomiony
        st.error(f"Nie udało się wyszukać (czy MOTIS działa na localhost:8080?): {exc}")
        st.stop()

    # Wynik ląduje w session_state, a nie w zwykłej zmiennej lokalnej: widgety POZA formularzem
    # (np. checkbox "Pokaż więcej") wywołują kolejny rerun Streamlita, w którym `submitted` jest
    # znów False — bez zapamiętania wyniku cały ten blok by się nie wykonał i wyszukiwanie
    # "znikało by" przy każdej takiej interakcji.
    st.session_state["search_result"] = {
        "request": request,
        "date": date,
        "built": built,
        "skipped": skipped,
        "recs": recs,
    }

result = st.session_state.get("search_result")
if result is not None:
    request, date, built, skipped, recs = (
        result["request"],
        result["date"],
        result["built"],
        result["skipped"],
        result["recs"],
    )

    st.caption(
        f"{request.origin_label} → {request.destination_label}, {date}. "
        f"Zbudowano {len(built)} wariant(y), pominięto {len(skipped)}."
    )
    if skipped:
        with st.expander("Pominięte warianty"):
            for s in skipped:
                st.write(f"**{s.variant_name}**: {s.reason}")
    if not built:
        st.error("Brak działającego wariantu — sprawdź, czy MOTIS jest uruchomiony.")
        st.stop()
    header_col, toggle_col = st.columns([3, 1])
    with header_col:
        st.header("Rekomendacje")
    more_keys = [key for key in RECOMMENDATION_LABELS if key not in TOP_CATEGORY_KEYS]
    with toggle_col:
        pokaz_wiecej = st.checkbox(f"Pokaż więcej ({len(more_keys)})", value=False)

    # Ten sam wariant potrafi wygrać w kilku kategoriach naraz (np. "Najszybsza" i "Najlepszy
    # kompromis" mogą wskazać dokładnie tę samą trasę, jeśli akurat jest jednocześnie
    # najszybsza i relatywnie tania) — to poprawne działanie scoringu, nie duplikat/błąd, ale
    # bez podpowiedzi wygląda na demo jak awaria. Pierwsza kategoria w kolejności
    # RECOMMENDATION_LABELS, która "zdobyła" dany wariant, staje się jego "właścicielem";
    # każda kolejna kategoria wskazująca na ten sam wariant dostaje hint z jej nazwą.
    first_owner_key = {}
    for key, itinerary in recs.items():
        first_owner_key.setdefault(id(itinerary), key)

    def render_recommendation_tab(key: str) -> None:
        owner_key = first_owner_key[id(recs[key])]
        if owner_key != key:
            st.caption(
                f"Ta sama trasa co „{RECOMMENDATION_LABELS[owner_key]}” — to nie duplikat, po prostu ten wariant wygrywa na obu osiach naraz."
            )
        if key in SAFE_CATEGORY_KEYS and recs[key].is_safe_fallback:
            st.info(
                "Żaden wariant nie był w pełni bezpieczny — to najmniej ryzykowny z dostępnych."
            )
        st.subheader(recs[key].variant_name)
        render_itinerary(recs[key], wiek, bc if bc != "brak" else None)

    visible_keys = list(RECOMMENDATION_LABELS) if pokaz_wiecej else list(TOP_CATEGORY_KEYS)
    tabs = st.tabs([RECOMMENDATION_LABELS[key] for key in visible_keys])
    for tab, key in zip(tabs, visible_keys):
        with tab:
            render_recommendation_tab(key)

    st.header("Wszystkie warianty")
    for it in built:
        if it.is_risky and _is_near_miss_itinerary(it):
            risk_suffix = "  🟡 prawie bezpieczna"
        elif it.is_risky:
            risk_suffix = "  ⚠️"
        else:
            risk_suffix = ""
        with st.expander(
            f"{it.variant_name} — {it.total_duration_min / 60:.1f} h, "
            f"{it.total_price_pln:.0f} PLN, przesiadek: {it.num_transfers}" + risk_suffix
        ):
            render_itinerary(it, wiek, bc if bc != "brak" else None)

    render_attractions_and_city_cards(
        request.destination_label, fallback_text=st.session_state.get("dest_query", "")
    )
