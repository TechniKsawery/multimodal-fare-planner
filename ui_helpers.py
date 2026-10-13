"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import json

import streamlit as st
import streamlit.components.v1 as components

from fares.eligibility_info import eligibility_for, explain_ticket
from i18n import t


def html_lang_script(lang: str) -> str:
    """Mały skrypt ustawiający <html lang> strony nadrzędnej (Streamlit domyślnie deklaruje "en")."""
    return (
        "<script>"
        f"window.parent.document.documentElement.lang = {json.dumps(lang)};"
        "</script>"
    )


def set_html_lang(lang: str) -> None:
    """Ustawia lang elementu <html> zgodnie z językiem UI, żeby Chrome nie proponował tłumaczenia.

    Skrypt jest renderowany w każdym przebiegu, więc zmiana języka działa bez przeładowania strony.
    """
    components.html(html_lang_script(lang), height=0)


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
        with st.expander(t("free_info.title")):
            for miasto, bezplatne, ulgowe, zrodlo in seen.values():
                st.markdown(f"**{miasto}** ([{t('free_info.source')}]({zrodlo}))")
                st.markdown(t("free_info.free", items="; ".join(bezplatne)))
                if ulgowe:
                    st.markdown(t("free_info.reduced", items="; ".join(ulgowe)))
            st.caption(t("free_info.caption"))


def render_other_day_section(other_day, render_itinerary) -> None:
    """Sekcja "Najbliższe połączenia w innym dniu" (routing/model.py::OtherDayVariant): osobna od
    rekomendacji, z datą i wyraźną etykietą, że to NIE jest dzień zapytania. Nic nie rysuje dla
    pustej listy. `render_itinerary` to funkcja rysująca wariant (app.py::render_itinerary)."""
    if not other_day:
        return
    st.header(t("other_day.title"))
    st.warning(t("other_day.warning"))
    for variant in other_day:
        it = variant.itinerary
        with st.expander(
            t(
                "other_day.expander",
                date=variant.date,
                name=it.variant_name,
                hours=f"{it.total_duration_min / 60:.1f}",
                price=f"{it.total_price_pln:.0f}",
                transfers=it.num_transfers,
            )
        ):
            st.error(variant.label)
            render_itinerary(it)
