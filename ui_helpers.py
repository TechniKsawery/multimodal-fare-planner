"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import streamlit as st

from fares.eligibility_info import eligibility_for, explain_ticket
from routing.model import OTHER_DAY_SECTION_TITLE


def render_bezplatne_info(it) -> None:
    """Wyjaśnia 0/ulgowe ceny i pokazuje, komu w miastach na trasie przysługuje bezpłatnie."""
    seen = {}
    for p in it.legs:
        powod = explain_ticket(p.breakdown)
        if powod:
            st.success(f"🎟️ {p.leg.origin_name} → {p.leg.destination_name}: {powod}")
        info = eligibility_for(p.carrier) if p.carrier else None
        if info:
            seen[info[0]] = info
    if seen:
        with st.expander("Kto jedzie bezpłatnie / ulgowo w miastach na trasie"):
            for miasto, bezplatne, ulgowe, zrodlo in seen.values():
                st.markdown(f"**{miasto}** ([źródło]({zrodlo}))")
                st.markdown("- Bezpłatnie: " + "; ".join(bezplatne))
                if ulgowe:
                    st.markdown("- Ulgowo (50%): " + "; ".join(ulgowe))
            st.caption("Zaznacz odpowiedni tytuł w formularzu, żeby cena go uwzględniła.")


def render_other_day_section(other_day, render_itinerary) -> None:
    """Sekcja "Najbliższe połączenia w innym dniu" (routing/model.py::OtherDayVariant): osobna od
    rekomendacji, z datą i wyraźną etykietą, że to NIE jest dzień zapytania. Nic nie rysuje dla
    pustej listy. `render_itinerary` to funkcja rysująca wariant (app.py::render_itinerary)."""
    if not other_day:
        return
    st.header(OTHER_DAY_SECTION_TITLE)
    st.warning(
        "W dniu zapytania nic nie jedzie. Poniżej połączenia z INNYCH dni — to NIE jest dzień "
        "zapytania i nie biorą udziału w rankingach „Najtańsza”/„Najszybsza”."
    )
    for variant in other_day:
        it = variant.itinerary
        with st.expander(
            f"{variant.date} — {it.variant_name}, {it.total_duration_min / 60:.1f} h, "
            f"{it.total_price_pln:.0f} PLN, przesiadek: {it.num_transfers}"
        ):
            st.error(variant.label)
            render_itinerary(it)
