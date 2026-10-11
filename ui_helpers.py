"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import streamlit as st

from fares.eligibility_info import eligibility_for, explain_ticket


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
