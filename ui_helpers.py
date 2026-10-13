"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import json

import streamlit as st

from fares.eligibility_info import eligibility_for, explain_ticket
from i18n import t, tm


def html_lang_script(lang: str) -> str:
    """Skrypt dla strony nadrzędnej: ustawia <html lang> (Streamlit domyślnie deklaruje "en") oraz
    translate="no" na <html> i <body> i <meta name="google" content="notranslate"> w <head>.

    Idempotentny - jest wykonywany w każdym przebiegu aplikacji.
    """
    return (
        "<script>"
        "(function(){"
        "var d=window.parent.document,h=d.documentElement;"
        f"h.lang={json.dumps(lang)};"
        "h.setAttribute('translate','no');"
        "if(d.body){d.body.setAttribute('translate','no');}"
        "if(!d.head.querySelector('meta[name=\"google\"][content=\"notranslate\"]')){"
        "var m=d.createElement('meta');m.name='google';m.content='notranslate';d.head.appendChild(m);"
        "}"
        "})();"
        "</script>"
    )


def set_html_lang(lang: str) -> None:
    """Ustawia lang/translate="no"/meta notranslate dokumentu nadrzędnego, żeby Chrome nie proponował
    tłumaczenia.

    Skrypt jest renderowany w każdym przebiegu, więc zmiana języka działa bez przeładowania strony.
    Dzieje się to dopiero po starcie frontendu Streamlita - zob. opis ograniczeń w README/PR.
    """
    st.iframe(html_lang_script(lang), height=1)


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


def variant_price_text(it, digits: int = 0) -> str:
    """Cena wariantu do nagłówków: pełna ("120 PLN" / "od 100 do 140 PLN"), "cena częściowa: od X"
    (część odcinków bez ceny — suma znanych to dolne ograniczenie) albo "brak ceny". Nigdy "0 PLN"
    dla kwoty, której nie znamy (Itinerary.price_status)."""
    status = it.price_status
    if status == "brak":
        return t("price.variant_none")
    lo = f"{it.total_price_pln:.{digits}f}"
    if it.total_price_pln_high is not None:
        hi = f"{it.total_price_pln_high:.{digits}f}"
        key = "price.variant_range" if status == "pelna" else "price.variant_partial_range"
        return t(key, lo=lo, hi=hi)
    key = "price.variant_single" if status == "pelna" else "price.variant_partial"
    return t(key, price=lo)


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
                name=tm(it.variant_name),
                hours=f"{it.total_duration_min / 60:.1f}",
                price=variant_price_text(it),
                transfers=it.num_transfers,
            )
        ):
            st.error(tm(variant.label))
            render_itinerary(it)
