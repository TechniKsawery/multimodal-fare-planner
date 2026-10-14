"""Styl interfejsu wg research/ui-styl.md (wersja 2): konfiguracja motywu, CSS, plakietki statusu,
karty wariantów, 5 grup opcji formularza i teksty w 6 językach. Tylko prezentacja - ceny i taryfy
nie są ruszane."""

import tomllib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ui_style
from i18n import LANGUAGES, TRANSLATIONS, t
from routing.model import TransferWarning
from tests.test_result_screen import _backend, _rail

ROOT = Path(__file__).resolve().parent.parent
PL = TRANSLATIONS["pl"]

NEW_KEYS = [
    "app.subtitle", "group.passenger", "group.passenger_hint", "group.rail", "group.rail_hint",
    "group.baggage", "group.baggage_hint", "group.city", "group.city_hint", "group.city_pl",
    "group.city_de", "group.free", "cards.safe", "cards.also", "cards.confirmed_why",
    "cards.estimate_why", "cards.fastest_why", "cards.safe_why",
]  # fmt: skip
# nazwy własne / skróty, które mogą brzmieć tak samo jak po polsku
SAME_AS_PL_OK = set()


# --- konfiguracja motywu -------------------------------------------------------------------------


def _config():
    return tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


def test_config_jasna_paleta_jest_podstawa_a_ciemna_nadpisaniem():
    theme = _config()["theme"]
    assert theme["base"] == "light"
    assert theme["primaryColor"] == "#2563EB"
    assert theme["backgroundColor"] == "#F8F9FA"
    assert theme["textColor"] == "#1E293B"
    dark = theme["dark"]
    assert dark["backgroundColor"] == "#18181B"
    assert dark["secondaryBackgroundColor"] == "#27272A"
    assert dark["textColor"] == "#FAFAFA"
    assert dark["primaryColor"] == "#3B82F6"


def test_config_nie_zmienia_zachowania_serwera():
    # headless/CORS/XSRF to decyzje wdrożeniowe, nie stylu: lokalne `streamlit run` ma dalej otwierać
    # przeglądarkę
    assert "server" not in _config()
    assert _config()["browser"]["gatherUsageStats"] is False


# --- CSS i plakietki -----------------------------------------------------------------------------


def test_css_ma_obie_palety_z_projektu_jako_light_dark():
    css = ui_style.style_css()
    for light, dark in [("#2563EB", "#3B82F6"), ("#166534", "#4ADE80"), ("#854D0E", "#FCD34D")]:
        assert f"light-dark({light}" in css and dark in css
    assert "light-dark(#DCFCE7, rgba(34,197,94,.16))" in css  # tło plakietki „oficjalna taryfa”


def test_css_przycisk_ma_50_px_a_na_telefonie_54_px_i_cele_dotyku_48_px():
    css = ui_style.style_css()
    assert "height:50px" in css and "border-radius:10px" in css
    mobile = css[css.index("@media (max-width:768px)") :]
    assert "height:54px" in mobile and "min-height:48px" in mobile


def test_css_bez_pustych_linii_i_wciec_ktore_zepsulyby_markdown():
    css = ui_style.style_css()
    assert "\n" not in css


def test_plakietka_to_tekst_i_kropka_a_tekst_jest_escapowany():
    html = ui_style.badge_html("OFICJALNA TARYFA", "official", "wyjaśnienie")
    assert 'class="mw-badge mw-badge-official"' in html and "OFICJALNA TARYFA" in html
    assert 'title="wyjaśnienie"' in html and "mw-dot" in html
    evil = ui_style.badge_html('<img src=x onerror="a">', "estimate", '"><script>')
    assert "<img" not in evil and "<script" not in evil and "&lt;img" in evil
    with pytest.raises(ValueError):
        ui_style.badge_html("x", "nieznany")


def test_kazdy_rodzaj_plakietki_ma_reguly_css():
    css = ui_style.style_css()
    for kind in ui_style.BADGE_KINDS:
        assert f".mw-badge-{kind}" in css
        for part in ("text", "bg", "border", "dot"):
            assert f"--mw-{kind}-{part}:" in css


# --- ekran ---------------------------------------------------------------------------------------


def _risky(it):
    it.transfer_warnings = [
        TransferWarning(after_leg_index=0, gap_minutes=5, minimum_required_minutes=10, reason="x")
    ]
    return it


def _app(monkeypatch, built, lang="pl"):
    _backend(monkeypatch, built)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception, at.exception
    return at


def _search(at):
    at.button[0].click().run()
    assert not at.exception, at.exception
    return at


def _markdown(at):
    """Teksty markdown i podpisy (st.caption) ekranu jako jeden napis."""
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def test_aplikacja_wstrzykuje_css_tytul_zostaje_a_podtytul_jest(monkeypatch):
    at = _app(monkeypatch, [_rail("A", 50.0)])
    assert at.title[0].value == "Multimodalna wyszukiwarka tras"
    assert t("app.subtitle") in [c.value for c in at.caption]
    assert "<style>" in _markdown(at) and ".mw-badge" in _markdown(at)


def test_przycisk_szukaj_jest_pierwszy_i_ma_ikone(monkeypatch):
    at = _app(monkeypatch, [_rail("A", 50.0)])
    submit = at.button[0]
    assert submit.label == t("form.submit")
    assert submit.proto.icon == ":material/search:" and submit.proto.type == "primary"


GROUP_KEYS = ("group-passenger", "group-rail", "group-baggage", "group-city")


def test_opcje_sa_w_piecioch_grupach_i_zadna_nie_zniknela(monkeypatch):
    at = _app(monkeypatch, [_rail("A", 50.0)])
    labels = [e.label for e in at.expander]
    assert t("form.more") in labels and t("group.free") in labels
    text = _markdown(at)
    for key in ("group.passenger", "group.rail", "group.baggage", "group.city"):
        assert t(key) in text, key
    # wszystkie pola formularza wciąż są (etykiety i wartości domyślne bez zmian)
    boxes = {c.label: c.value for c in at.checkbox}
    expected_off = [
        "student.label", "senior.label", "form.ztm_lublin", "city.warszawa", "city.krakow",
        "city.poznan", "city.wroclaw", "city.berlin", "form.vrr", "form.hamburg", "form.munich",
        "form.cologne", "free.warszawa", "free.krakow", "free.poznan", "free.wroclaw",
        "free.lublin", "free.berlin", "free.de_wertmarke",
    ]  # fmt: skip
    for key in expected_off:
        assert boxes[t(key)] is False, key
    assert boxes[t("form.baggage")] is True
    assert {s.label for s in at.selectbox} >= {
        t("citizen.label"), t("idcountry.label"), t("form.pkp"), t("form.bahncard")
    }
    assert at.number_input(key="w_wiek").value == 30


def test_domyslne_wartosci_checkboxow_zaleza_od_wieku_jak_dotad(monkeypatch):
    at = _app(monkeypatch, [_rail("A", 50.0)])
    at.number_input(key="w_wiek").set_value(10)
    at.button[0].click().run()  # domyślne wartości przestawiają się przy wysłaniu formularza
    assert not at.exception, at.exception
    boxes = {c.label: c.value for c in at.checkbox}
    assert boxes[t("form.ztm_lublin")] is True and boxes[t("form.vrr")] is True
    assert boxes[t("free.lublin")] is True and boxes[t("free.warszawa")] is False
    assert t("form.guardian") in boxes  # dziecko 6-14 lat: pytanie o opiekuna


def test_dodatkowe_karty_najszybsza_i_bezpieczna_przesiadka(monkeypatch):
    built = [
        _rail("Potwierdzony", 80.0, minutes=300),
        _rail("Szacunkowy", 40.0, confirmed=False, minutes=420, transfers=1),
        _rail("Szybki", 120.0, minutes=180),
        _risky(_rail("Ryzykowny", 60.0, minutes=240, transfers=1)),
    ]
    at = _search(_app(monkeypatch, built))
    keys = {b.key for b in at.button}
    assert {"show_confirmed", "show_estimate", "show_fastest"} <= keys
    text = _markdown(at)
    assert t("rec.najszybsza") in text and t("cards.fastest_why") in text
    # najtańsza bezpieczna to ta sama trasa co polecana: bez osobnej karty, jest dopisek „także”
    assert "show_safe" not in keys
    assert t("cards.also", labels=t("cards.safe")) in [c.value for c in at.caption]


def test_bezpieczna_przesiadka_ma_karte_gdy_to_inny_wariant(monkeypatch):
    built = [
        _risky(_rail("Tani ryzykowny", 30.0, minutes=200, transfers=1)),
        _rail("Szybki bezpieczny", 70.0, minutes=210),  # remis kompromisu: wygrywa pierwszy
        _rail("Wolny bezpieczny", 60.0, minutes=900),  # najtańsza bezpieczna
    ]
    at = _search(_app(monkeypatch, built))
    text = _markdown(at)
    assert {"show_safe"} <= {b.key for b in at.button}
    assert t("cards.safe") in text and t("cards.safe_why") in text


def test_bez_bezpiecznego_wariantu_nie_ma_karty_bezpiecznej_przesiadki(monkeypatch):
    built = [_risky(_rail("A", 30.0, transfers=1)), _risky(_rail("B", 50.0, minutes=200, transfers=1))]
    at = _search(_app(monkeypatch, built))
    assert "show_safe" not in {b.key for b in at.button}


def test_karta_szacunku_ma_jedna_plakietke_szacunku_a_potwierdzona_oficjalna(monkeypatch):
    at = _search(_app(monkeypatch, [_rail("Potwierdzony", 80.0), _rail("Szacunkowy", 40.0, confirmed=False)]))
    text = _markdown(at)
    assert text.count("mw-badge-estimate") >= 1 and "mw-badge-official" in text
    # „potwierdzona” wynika z is_price_confirmed (nie z innych pól): karta potwierdzona to ta o cenie 80
    assert t("cards.confirmed_why") in text and t("cards.estimate_why") in text


# --- zakazane sformułowania i teksty w 6 językach ---------------------------------------------------

FORBIDDEN = ("gwarancj", "garantowan", "superpromo", "super promo", "guarantee", "garantie", "garant")


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_w_tekstach_nie_ma_obietnic_ceny_ani_superpromo(lang):
    for key, text in TRANSLATIONS[lang].items():
        assert not any(w in text.lower() for w in FORBIDDEN), f"{lang}/{key}: {text}"


@pytest.mark.parametrize("lang", [lang for lang in LANGUAGES if lang != "pl"])
def test_nowe_teksty_stylu_sa_przetlumaczone(lang):
    same = [k for k in NEW_KEYS if TRANSLATIONS[lang][k] == PL[k] and k not in SAME_AS_PL_OK]
    assert same == [], f"{lang}: skopiowane z polskiego {same}"


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_ekran_w_jezyku_ma_grupy_i_dodatkowe_karty(monkeypatch, lang):
    import i18n

    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    built = [_rail("Potwierdzony", 80.0, minutes=300), _rail("Szybki", 120.0, minutes=180)]
    at = _search(_app(monkeypatch, built, lang))
    text = _markdown(at)
    for key in ("group.passenger", "group.rail", "group.baggage", "group.city", "cards.fastest_why"):
        assert t(key, lang=lang) in text, (lang, key)
    assert t("group.free", lang=lang) in [e.label for e in at.expander]
    assert t("app.subtitle", lang=lang) in [c.value for c in at.caption]
