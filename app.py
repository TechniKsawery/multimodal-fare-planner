"""Frontend Streamlit (Sesja 5): ten sam pipeline co demo.py, w przeglądarce.

Uruchomienie:  pip install streamlit  &&  streamlit run app.py
Wymaga działającego MOTIS (localhost:8080), patrz README.md.
"""
import datetime as dt
import json

import streamlit as st

from demo import DEFAULT_FROM, DEFAULT_TO, DEMO_DATE
from fares.model import DiscountProfile
from routing import motis_client
from routing.demo_route import (
    FLIGHT_REGIONAL_HUBS,
    RAIL_FLIGHT_RAIL_HUBS,
    VIA_HUB_STOPS,
)
from routing.card_suggestions import db_distance_km, suggest_bahncard_for_itinerary
from routing.motis_client import MotisError
from routing.scoring import RECOMMENDATION_LABELS, SAFE_CATEGORY_KEYS, TOP_CATEGORY_KEYS, pick_recommendations
from routing.variants import RouteRequest, generate_variants

with open("fares/data/pkp_intercity.json", encoding="utf-8") as fh:
    PKP_ULGI = list(json.load(fh)["ulgi_procent"])

st.set_page_config(page_title="Multimodalna wyszukiwarka", layout="wide")
st.title("Multimodalna wyszukiwarka tras")


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
        rows.append({
            "Środek": leg.mode.value,
            "Trasa": f"{leg.origin_name} → {leg.destination_name}",
            "Godziny": f"{leg.depart:%H:%M}–{leg.arrive:%H:%M} ({leg.duration_min:.0f} min)",
            "Przewoźnik": leg.carrier_name or "",
            "Cena / dystans": price,
            "Rozbicie ceny lotu": rozbicie,
            "Cennik bagażu": zrodlo_bagazu,
        })
    st.dataframe(rows, width="stretch", hide_index=True)
    if it.is_risky:
        for w in it.transfer_warnings:
            st.warning(f"Ryzykowna przesiadka: {w.reason}")
    else:
        st.success("Przesiadki: bezpieczne (wg przyjętych minimów)")

    if db_distance_km(it) <= 0:
        st.caption("💳 Ten wariant nie zawiera odcinka DB (kolej niemiecka) — BahnCard nie ma tu zastosowania.")
    else:
        suggestions = suggest_bahncard_for_itinerary(it, age=wiek, existing_bahncard=posiadana_bahncard)
        if suggestions:
            best = suggestions[0]
            if best.rekomendowana:
                st.info(f"💳 {best.opis}")
            else:
                st.caption(f"💳 {best.opis}")
        elif posiadana_bahncard:
            st.caption(f"💳 Masz już BahnCard {posiadana_bahncard} — cena w tabeli wyżej już ją uwzględnia; "
                       f"żadna inna karta nie da tu lepszego rabatu.")


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
    "Wiek pasażera", min_value=0, max_value=120, value=30, step=1,
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
        "Bilet ulgowy ZTM Lublin", value=wiek < 18,
        help="Podpowiedź wg wieku (<18 lat) — zaznacz też ręcznie, jeśli masz ulgę z innego "
             "tytułu (uczeń, student, senior, niepełnosprawność), niezależnie od wieku.",
    )
    vrr_dziecko = c4.checkbox(
        "Taryfa dziecięca VRR (Kindertarif)", value=6 <= wiek <= 14,
        help="Oficjalna zniżka VRR: 50% dla dzieci 6-14 lat, ściśle wg wieku.",
    )
    submitted = st.form_submit_button("Szukaj")

if submitted:
    if origin_resolved is None or dest_resolved is None:
        st.error("Wybierz dokładny adres z podpowiedzi (skąd i dokąd) przed wyszukiwaniem.")
        st.stop()
    profile = DiscountProfile(
        pkp_ulga_kod=pkp, bahncard=None if bc == "brak" else bc,
        ztm_lublin_ulgowy=ztm_ulgowy, vrr_dziecko=vrr_dziecko,
    )
    try:
        with st.spinner("Szukam połączeń..."):
            request = RouteRequest(
                origin_stop_id=motis_client.coords_place(origin_resolved["lat"], origin_resolved["lon"]),
                destination_stop_id=motis_client.coords_place(dest_resolved["lat"], dest_resolved["lon"]),
                origin_label=origin_resolved["name"],
                destination_label=dest_resolved["name"],
                date=date.isoformat(),
                discounts=profile,
            )
            # UWAGA: alternative_destination_stops celowo NIE jest tu przekazywane — patrz
            # komentarz w demo.py / routing/demo_route.py (podmieniłoby rzeczywisty adres
            # docelowy na sztywny dworzec, ucinając ostatni odcinek do adresu).
            built, skipped = generate_variants(
                request,
                rail_flight_rail_hubs=RAIL_FLIGHT_RAIL_HUBS,
                flight_regional_hubs=FLIGHT_REGIONAL_HUBS,
                via_hub_stops=VIA_HUB_STOPS,
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
        "request": request, "date": date, "built": built, "skipped": skipped,
    }

result = st.session_state.get("search_result")
if result is not None:
    request, date, built, skipped = result["request"], result["date"], result["built"], result["skipped"]

    st.caption(f"{request.origin_label} → {request.destination_label}, {date}. "
               f"Zbudowano {len(built)} wariant(y), pominięto {len(skipped)}.")
    if skipped:
        with st.expander("Pominięte warianty"):
            for s in skipped:
                st.write(f"**{s.variant_name}**: {s.reason}")
    if not built:
        st.error("Brak działającego wariantu — sprawdź, czy MOTIS jest uruchomiony.")
        st.stop()

    recs = pick_recommendations(built)
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
            st.caption(f"Ta sama trasa co „{RECOMMENDATION_LABELS[owner_key]}” — to nie duplikat, po prostu ten wariant wygrywa na obu osiach naraz.")
        if key in SAFE_CATEGORY_KEYS and recs[key].is_safe_fallback:
            st.info("Żaden wariant nie był w pełni bezpieczny — to najmniej ryzykowny z dostępnych.")
        st.subheader(recs[key].variant_name)
        render_itinerary(recs[key], wiek, bc if bc != "brak" else None)

    visible_keys = list(RECOMMENDATION_LABELS) if pokaz_wiecej else list(TOP_CATEGORY_KEYS)
    tabs = st.tabs([RECOMMENDATION_LABELS[key] for key in visible_keys])
    for tab, key in zip(tabs, visible_keys):
        with tab:
            render_recommendation_tab(key)

    st.header("Wszystkie warianty")
    for it in built:
        with st.expander(f"{it.variant_name} — {it.total_duration_min / 60:.1f} h, "
                         f"{it.total_price_pln:.0f} PLN, przesiadek: {it.num_transfers}"
                         + ("  ⚠️" if it.is_risky else "")):
            render_itinerary(it, wiek, bc if bc != "brak" else None)
