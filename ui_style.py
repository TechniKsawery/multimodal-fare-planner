"""Styl interfejsu wg research/ui-styl.md (wersja 2): tokeny kolorów, plakietki statusu, duży przycisk
„Szukaj połączeń”, karty wariantów, grupy formularza i układ mobilny.

Tylko prezentacja - nic tu nie dotyka cen ani taryf. Kolory tła, tekstu i akcentu daje motyw
Streamlita z .streamlit/config.toml (jasny domyślnie, ciemny do wyboru w menu aplikacji). CSS
dokłada to, czego motyw nie umie: plakietki, karty, przycisk i odstępy.

Paleta jasna i ciemna siedzą w tych samych regułach jako `light-dark(jasna, ciemna)`. Streamlit
ustawia `color-scheme` na kontenerze .stApp zgodnie z aktualnym motywem (także po przełączeniu
w menu, bez przeładowania strony), więc CSS nie zależy od Pythona ani od ustawień systemu."""

from html import escape

import streamlit as st

# Klasa plakietki wg rodzaju statusu ceny (klucze jak w ui_helpers._STATUS_KEY).
BADGE_KINDS = ("official", "estimate", "no_price")

_TOKENS = {
    "--mw-card": "light-dark(#FFFFFF, #27272A)",
    "--mw-subtle": "light-dark(#F1F5F9, #3F3F46)",
    "--mw-border": "light-dark(#E2E8F0, #3F3F46)",
    "--mw-primary": "light-dark(#2563EB, #3B82F6)",
    "--mw-primary-hover": "light-dark(#1D4ED8, #2563EB)",
    "--mw-primary-active": "light-dark(#1E40AF, #1D4ED8)",
    "--mw-primary-glow": "light-dark(rgba(37,99,235,.28), rgba(59,130,246,.35))",
    "--mw-primary-tint": "light-dark(rgba(37,99,235,.04), rgba(59,130,246,.10))",
    "--mw-muted": "light-dark(#64748B, #A1A1AA)",
    "--mw-official-text": "light-dark(#166534, #4ADE80)",
    "--mw-official-bg": "light-dark(#DCFCE7, rgba(34,197,94,.16))",
    "--mw-official-border": "light-dark(#86EFAC, rgba(74,222,128,.35))",
    "--mw-official-dot": "light-dark(#16A34A, #4ADE80)",
    "--mw-estimate-text": "light-dark(#854D0E, #FCD34D)",
    "--mw-estimate-bg": "light-dark(#FEF3C7, rgba(245,158,11,.18))",
    "--mw-estimate-border": "light-dark(#FCD34D, rgba(251,191,36,.35))",
    "--mw-estimate-dot": "light-dark(#D97706, #FCD34D)",
    "--mw-no_price-text": "light-dark(#475569, #D4D4D8)",
    "--mw-no_price-bg": "light-dark(#F1F5F9, rgba(161,161,170,.14))",
    "--mw-no_price-border": "light-dark(#CBD5E1, rgba(161,161,170,.30))",
    "--mw-no_price-dot": "light-dark(#64748B, #A1A1AA)",
}

# Reguły bez pustych linii i wcięć: Markdown Streamlita traktuje wcięty blok jako kod, a pustą linię
# jako koniec bloku HTML.
_RULES = (
    # układ strony
    ".block-container{max-width:1140px;padding-top:1.5rem;padding-bottom:3rem;}",
    "h1{font-size:26px !important;font-weight:700 !important;line-height:1.2 !important;}",
    "h3{font-size:15px !important;font-weight:600 !important;line-height:1.35 !important;}",
    # karty wariantów i grupy formularza (kontenery z kluczem card-* / group-*)
    '[class*="st-key-card-"],[class*="st-key-group-"]{background:var(--mw-card);'
    "border:1px solid var(--mw-border) !important;border-radius:12px !important;"
    "padding:.25rem .5rem;box-shadow:0 1px 3px rgba(0,0,0,.05);"
    "gap:.4rem;transition:border-color .15s ease-in-out,box-shadow .15s ease-in-out;}",
    '[class*="st-key-card-"]:hover{border-color:var(--mw-primary) !important;'
    "box-shadow:0 4px 12px rgba(0,0,0,.08);}",
    '[class*="st-key-card-selected-"]{border:2px solid var(--mw-primary) !important;'
    "background:var(--mw-primary-tint);box-shadow:0 4px 14px var(--mw-primary-glow);}",
    ".mw-card-title{font-size:13px;font-weight:700;letter-spacing:.02em;text-transform:uppercase;"
    "color:var(--mw-muted);}",
    ".mw-price-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:2px 0 4px;}",
    ".mw-price{font-size:22px;font-weight:800;line-height:1.15;}",
    ".mw-group-title{font-size:15px;font-weight:600;line-height:1.35;margin:0;}",
    # plakietki statusu ceny: tekst + kropka, nie sam kolor
    ".mw-badge{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:6px;"
    "border:1px solid;font-size:11px;font-weight:700;line-height:1.2;letter-spacing:.02em;"
    "text-transform:uppercase;white-space:nowrap;}",
    ".mw-dot{width:6px;height:6px;border-radius:50%;display:inline-block;}",
    ".mw-badge-selected{color:var(--mw-primary);background:var(--mw-primary-tint);"
    "border-color:var(--mw-primary);}",
    *(
        f".mw-badge-{k}{{color:var(--mw-{k}-text);background:var(--mw-{k}-bg);"
        f"border-color:var(--mw-{k}-border);}}.mw-badge-{k} .mw-dot{{background:var(--mw-{k}-dot);}}"
        for k in BADGE_KINDS
    ),
    # duży przycisk „Szukaj połączeń”
    '[data-testid="stFormSubmitButton"] button{width:100%;height:50px;border:none;border-radius:10px;'
    "font-size:16px;font-weight:600;color:#FFFFFF;background-color:var(--mw-primary);"
    "box-shadow:0 2px 6px var(--mw-primary-glow);margin-top:.75rem;"
    "transition:all .15s ease-in-out;}",
    '[data-testid="stFormSubmitButton"] button:hover{background-color:var(--mw-primary-hover);'
    "color:#FFFFFF;transform:translateY(-1px);box-shadow:0 4px 12px var(--mw-primary-glow);}",
    '[data-testid="stFormSubmitButton"] button:active{background-color:var(--mw-primary-active);'
    "transform:translateY(1px);box-shadow:0 1px 3px var(--mw-primary-glow);}",
    '[data-testid="stFormSubmitButton"] button p{font-size:16px;font-weight:600;}',
    # pola formularza
    '[data-baseweb="input"],[data-baseweb="select"] > div{border-radius:8px !important;}',
    '[data-baseweb="input"]:focus-within,[data-baseweb="select"]:focus-within > div{'
    "border-color:var(--mw-primary) !important;box-shadow:0 0 0 3px var(--mw-primary-glow);}",
    # telefon: jeden słupek, większe cele dotyku
    "@media (max-width:768px){"
    ".block-container{padding-left:.75rem;padding-right:.75rem;}"
    '[data-testid="stFormSubmitButton"] button{height:54px;}'
    '.stButton button,[data-baseweb="input"] input,[data-baseweb="select"] > div{min-height:48px;}'
    '[class*="st-key-card-"]{margin-bottom:.25rem;}}',
)


def style_css() -> str:
    tokens = "".join(f"{name}:{value};" for name, value in _TOKENS.items())
    return f".stApp{{{tokens}}}" + "".join(_RULES)


def inject_style() -> None:
    """Wstrzykuje CSS do strony (w każdym przebiegu, bo st.markdown nie zapamiętuje elementów)."""
    st.markdown(f"<style>{style_css()}</style>", unsafe_allow_html=True)


def badge_html(label: str, kind: str, title: str | None = None) -> str:
    """Plakietka statusu ceny (kropka + napis wielkimi literami). `kind`: official / estimate /
    no_price, `title` to podpowiedź po najechaniu. Tekst jest zawsze escapowany."""
    if kind not in BADGE_KINDS:
        raise ValueError(f"nieznany rodzaj plakietki: {kind}")
    tip = f' title="{escape(title, quote=True)}"' if title else ""
    return f'<span class="mw-badge mw-badge-{kind}"{tip}><span class="mw-dot"></span>{escape(label)}</span>'


def selected_badge_html(label: str) -> str:
    return f'<span class="mw-badge mw-badge-selected">{escape(label)}</span>'
