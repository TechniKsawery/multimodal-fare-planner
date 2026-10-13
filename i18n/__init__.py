"""Wersje językowe interfejsu Streamlit (PL domyślny, EN, DE, ES, FR, NL).

Teksty UI siedzą w słownikach `i18n/<kod>.py` (klucz -> tekst), a `t(klucz, **pola)` wybiera
język z `st.session_state["lang"]`. Polski jest językiem źródłowym i zapasowym: brakujący
klucz w innym języku spada na polski, brakujący w polskim zwraca sam klucz (test
tests/test_i18n.py pilnuje, żeby każdy język miał komplet kluczy i te same pola {…}).

To wyłącznie warstwa prezentacji — nie dotyka cen ani logiki taryf.
"""

from . import de, en, es, fr, nl, pl

DEFAULT_LANG = "pl"
LANGUAGES = {
    "pl": "Polski",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "nl": "Nederlands",
}
TRANSLATIONS = {"pl": pl.TEXTS, "en": en.TEXTS, "de": de.TEXTS, "es": es.TEXTS, "fr": fr.TEXTS, "nl": nl.TEXTS}


def current_lang() -> str:
    try:
        import streamlit as st

        lang = st.session_state.get("lang", DEFAULT_LANG)
    except Exception:  # poza kontekstem Streamlita (np. zwykły import w teście)
        lang = DEFAULT_LANG
    return lang if lang in TRANSLATIONS else DEFAULT_LANG


def t(key: str, lang: str | None = None, **fields) -> str:
    lang = lang or current_lang()
    text = TRANSLATIONS.get(lang, {}).get(key)
    if text is None:
        text = TRANSLATIONS[DEFAULT_LANG].get(key, key)
    return text.format(**fields) if fields else text


def label_or(prefix: str, key: str, fallback: str) -> str:
    """Tłumaczenie etykiety o kluczu `prefix.key`; gdy go nie ma w słowniku — `fallback`
    (np. surowa etykieta z modułu domenowego, która zostaje po polsku)."""
    full = f"{prefix}.{key}"
    if full in TRANSLATIONS[DEFAULT_LANG]:
        return t(full)
    return fallback
