"""Wersje językowe interfejsu Streamlit (PL domyślny, EN, DE, ES, FR, NL).

Teksty UI siedzą w słownikach `i18n/<kod>.py` (klucz -> tekst), a `t(klucz, **pola)` wybiera
język z `st.session_state["lang"]`. Polski jest językiem źródłowym i zapasowym: brakujący
klucz w innym języku spada na polski, brakujący w polskim zwraca sam klucz (test
tests/test_i18n.py pilnuje, żeby każdy język miał komplet kluczy i te same pola {…}).

To wyłącznie warstwa prezentacji — nie dotyka cen ani logiki taryf.

Teksty tworzone w kodzie domenowym (nazwy wariantów, powody pominięcia, komunikaty przesiadek,
ostrzeżenia) są obiektami `Msg`: to podklasa `str` z polskim tekstem (więc API, demo.py i testy
widzą zwykły polski napis), która dodatkowo pamięta klucz i parametry. UI wywołuje `tm(wartość)`,
żeby wyrenderować ją w wybranym języku; zwykły `str` przechodzi bez zmian.
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


class Joined:
    """Lista elementów (Msg albo str) renderowana jako jeden tekst z separatorem — parametr Msg."""

    def __init__(self, items, sep: str = ", "):
        self.items = list(items)
        self.sep = sep


def _render_param(value, lang: str):
    if isinstance(value, Joined):
        return value.sep.join(str(_render_param(v, lang)) for v in value.items)
    if isinstance(value, Msg):
        return value.render(lang)
    return value


class Msg(str):
    """Tekst z kluczem i18n: `str` z polskim brzmieniem + `key`/`params` do renderu w innym języku."""

    key: str
    params: dict

    def __new__(cls, key: str, **params):
        obj = super().__new__(cls, t(key, lang=DEFAULT_LANG, **_params_for(params, DEFAULT_LANG)))
        obj.key = key
        obj.params = params
        return obj

    def __reduce__(self):  # kopiowanie/pickle (np. session_state, dataclasses.replace)
        return (_rebuild_msg, (self.key, self.params))

    def render(self, lang: str | None = None) -> str:
        return t(self.key, lang=lang, **_params_for(self.params, lang or current_lang()))


def _params_for(params: dict, lang: str) -> dict:
    return {name: _render_param(value, lang) for name, value in params.items()}


def _rebuild_msg(key: str, params: dict) -> Msg:
    return Msg(key, **params)


def tm(value, lang: str | None = None) -> str:
    """Tekst w wybranym języku: `Msg` jest renderowany z kluczy, zwykły `str` zostaje bez zmian
    (np. tekst z zewnętrznego API albo surowy komunikat bez tłumaczenia)."""
    return value.render(lang) if isinstance(value, Msg) else str(value)


def exc_text(exc: BaseException):
    """Powód z wyjątku: `Msg`, gdy wyjątek niósł `Msg` (str(exc) gubi podklasę), inaczej `str`."""
    if exc.args and isinstance(exc.args[0], Msg):
        return exc.args[0]
    return str(exc)


def transport_mode_name(motis_mode: str) -> Msg | str:
    """Nazwa rodzaju transportu z surowego trybu MOTIS (np. "REGIONAL_RAIL" -> "kolej regionalna");
    nieznany tryb dostaje czytelny napis zamiast surowego klucza."""
    key = f"tmode.{motis_mode.lower()}"
    if key in TRANSLATIONS[DEFAULT_LANG]:
        return Msg(key)
    return motis_mode.replace("_", " ").lower()
