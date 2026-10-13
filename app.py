"""Frontend Streamlit (Sesja 5): ten sam pipeline co demo.py, w przeglądarce.

Uruchomienie:  pip install streamlit  &&  streamlit run app.py
Wymaga działającego MOTIS (localhost:8080), patrz README.md.
"""

import datetime as dt
import json
import re
from pathlib import Path

import streamlit as st

from attractions import (
    CATEGORY_LABELS,
    AttractionCategory,
    best_price_for_attraction,
    price_from_note,
    evaluate_city_cards,
    get_attractions,
    get_city_cards,
    normalize_city,
    suggest_best_city_card,
)
from attractions import DiscountProfile as AttractionDiscountProfile
from attractions import HeldDocument
from demo import DEFAULT_FROM, DEFAULT_TO, DEMO_DATE
from ui_helpers import (
    render_bezplatne_info,
    render_other_day_section,
    set_html_lang,
    variant_price_text,
)
from fares.foreigner_eligibility import warnings_for as foreigner_warnings_for
from flights.cabin_baggage import format_breakdown as format_cabin_breakdown
from fares.model import DiscountProfile
from i18n import DEFAULT_LANG, LANGUAGES, label_or, t
from routing import motis_client
from routing.card_suggestions import db_distance_km, suggest_bahncard_for_itinerary
from routing.motis_client import MotisError
from routing.scoring import (
    RECOMMENDATION_LABELS,
    SAFE_CATEGORY_KEYS,
    TOP_CATEGORY_KEYS,
    price_ranking_note,
)
from routing.search_service import search
from routing.variants import RouteRequest

with open("fares/data/pkp_intercity.json", encoding="utf-8") as fh:
    PKP_ULGI = list(json.load(fh)["ulgi_procent"])

# set_page_config musi być pierwszym poleceniem st.*, więc tytuł karty czyta język z poprzedniego
# przebiegu (po zmianie języka Streamlit robi rerun, w którym st.session_state["lang"] już jest).
st.set_page_config(
    page_title=t("app.page_title", lang=st.session_state.get("lang", DEFAULT_LANG)),
    layout="wide",
)
st.radio(
    "Język / Language",
    options=list(LANGUAGES),
    format_func=LANGUAGES.get,
    key="lang",
    horizontal=True,
    label_visibility="collapsed",
)
set_html_lang(st.session_state["lang"])
st.title(t("app.title"))

# Czysto kosmetyczne rozróżnienie w UI (nie wpływa na progi z routing/transfers.py ani na
# scoring/kategoryzację "bezpieczna"): przesiadka, której brakuje do progu bezpieczeństwa
# tylko odrobinę, dostaje łagodniejszą adnotację "prawie bezpieczna" zamiast zwykłego
# ostrzeżenia o ryzykownej przesiadce.
NEAR_MISS_MARGIN_MINUTES = 10

# Lokalne profile użytkowników (zaznaczone atrakcje per miasto), żeby kilka osób mogło
# współdzielić to samo demo i każda wracała do swoich wyborów pod własną nazwą profilu.
# Katalog data/ jest w .gitignore — to dane runtime, nie repo.
PROFILES_DIR = Path("data/profiles")


def _profile_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "profil"


def _profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{_profile_slug(name)}.json"


def _load_profile(name: str) -> dict:
    path = _profile_path(name)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_profile_selection(name: str, city: str, attraction_names: list[str]) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    data = _load_profile(name)
    data[city] = attraction_names
    _profile_path(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _unverified_label(p) -> str:
    """Tłumaczona wersja PricedLeg.unverified_label (routing/model.py) — te same warunki, sam
    tekst z i18n; sama wycena nie jest tu ruszana."""
    if p.price_verified:
        return ""
    if p.breakdown.get("cena_nieznana"):
        return t("price.unknown_leg")
    if p.breakdown.get("wartosc_zastepcza"):
        return t("price.unverified_fallback")
    return t("price.unverified")


def rec_label(key: str) -> str:
    return label_or("rec", key, RECOMMENDATION_LABELS[key])


def render_itinerary(it, wiek=None, posiadana_bahncard=None) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric(t("metric.time"), f"{it.total_duration_min / 60:.1f} h")
    status = it.price_status
    if status == "brak":
        c2.metric(t("metric.price"), t("metric.price_none"))
    elif status == "czesciowa":
        c2.metric(
            t("metric.price"),
            t("metric.price_partial", price=f"{it.total_price_pln:.2f}"),
            help=t("price.unknown_total"),
        )
    elif it.total_price_pln_high is not None:
        c2.metric(
            t("metric.price"),
            t("metric.price_from", price=f"{it.total_price_pln:.2f}"),
            help=t("metric.price_high_help", price=f"{it.total_price_pln_high:.2f}"),
        )
    else:
        c2.metric(t("metric.price"), t("metric.price_exact", price=f"{it.total_price_pln:.2f}"))
    c3.metric(t("metric.transfers"), it.num_transfers)
    if status != "pelna":
        st.caption(t("price.unknown_total"))
    elif not it.price_verified:
        st.caption(t("price.unverified_total"))
    rows = []
    for p in it.legs:
        leg = p.leg
        if leg.mode.value == "pieszo":
            m = leg.extra.get("walk_distance_m")
            price = f"{m:.0f} m" if m else ""
        else:
            price = (
                f"{p.amount:.2f} {p.currency} ({p.price_type})"
                if p.price_known
                else t("price.leg_none")
            )
            if p.unverified_label:
                price += f" — {_unverified_label(p)}"
        rozbicie = ""
        zrodlo_bagazu = ""
        bagaz_podreczny = ""
        if leg.mode.value == "lot" and "bagaz_podreczny" in p.breakdown:
            bagaz_podreczny = format_cabin_breakdown(p.breakdown["bagaz_podreczny"])
        if leg.mode.value == "lot" and "cena_biletu" in p.breakdown:
            rozbicie = t(
                "leg.flight_breakdown",
                ticket=f"{p.breakdown['cena_biletu']:.2f}",
                bag=f"{p.breakdown.get('bagaz', 0):.2f}",
                cur=p.currency,
            )
            zrodlo_bagazu = p.breakdown.get("bagaz_zrodlo", "")
        zakres = p.breakdown.get("zakres_cen")
        if zakres:
            price += t(
                "price.range",
                lo=f"{zakres['od']:.2f}",
                lo_src=zakres["od_zrodlo"],
                hi=f"{zakres['do']:.2f}",
                hi_src=zakres["do_zrodlo"],
                cur=zakres["waluta"],
            )
        alt = p.breakdown.get("alternatywna_oferta")
        alternatywa = ""
        if alt:
            zrodlo_oferty = t("alt.db") if alt["zrodlo"] == "db" else t("alt.pkp")
            alternatywa = f"{alt['cena']:.2f} {alt['waluta']} ({zrodlo_oferty})"
        rows.append(
            {
                t("col.mode"): label_or("mode", leg.mode.value, leg.mode.value),
                t("col.line"): (
                    leg.extra.get("route_short_name") or ""
                    if leg.mode.value in ("kolej", "autobus")
                    else ""
                ),
                t("col.route"): f"{leg.origin_name} → {leg.destination_name}",
                t("col.hours"): f"{leg.depart:%H:%M}–{leg.arrive:%H:%M} ({leg.duration_min:.0f} min)",
                t("col.carrier"): leg.carrier_name or "",
                t("col.price"): price,
                t("col.flight_breakdown"): rozbicie,
                t("col.baggage_tariff"): zrodlo_bagazu,
                t("col.cabin_baggage"): bagaz_podreczny,
                t("col.alt_offer"): alternatywa,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    render_bezplatne_info(it)
    if it.is_risky:
        for w in it.transfer_warnings:
            if w.infeasible:
                continue
            if _is_near_miss(w):
                stacja = it.legs[w.after_leg_index].leg.destination_name
                shortfall = w.minimum_required_minutes - w.gap_minutes
                st.info(
                    t(
                        "transfer.near_miss",
                        station=stacja,
                        shortfall=f"{shortfall:.0f}",
                        gap=f"{w.gap_minutes:.0f}",
                        required=f"{w.minimum_required_minutes:.0f}",
                    )
                )
            else:
                st.warning(t("transfer.risky", reason=w.reason))
    else:
        st.success(t("transfer.safe"))

    if db_distance_km(it) <= 0:
        st.caption(t("bc.no_db"))
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
            st.caption(t("bc.already", card=posiadana_bahncard))


def render_attractions_and_city_cards(
    destination_label: str,
    fallback_text: str = "",
    attraction_profile: "AttractionDiscountProfile | None" = None,
) -> None:
    # destination_label pochodzi z podpowiedzi geocodingu MOTIS i dla konkretnego adresu
    # (np. "Buerer Straße 8") często NIE zawiera nazwy miasta, więc normalize_city się nie
    # trafia — spada wtedy na fallback_text, czyli surowy tekst wpisany w pole "Dokąd (adres)"
    # (zwykle z miastem, np. "Buerer Straße 8, Gelsenkirchen").
    norm_city = normalize_city(destination_label) or normalize_city(fallback_text)
    if not norm_city:
        return

    known_cities = ("gelsenkirchen", "berlin", "krakow", "lublin", "warszawa")
    display_city = t(f"city.{norm_city}") if norm_city in known_cities else norm_city.capitalize()

    st.markdown("---")
    st.header(t("attr.header", city=display_city))
    st.caption(t("attr.intro"))

    all_city_attrs = get_attractions(city=norm_city)
    if not all_city_attrs:
        st.info(t("attr.none", city=display_city))
        return

    # Filtrowanie kategorii
    cat_options = ["Wszystkie"] + [cat.value for cat in AttractionCategory]
    cat_labels = {"Wszystkie": t("attr.all_categories")}
    cat_labels.update(
        {cat.value: label_or("cat", cat.value, CATEGORY_LABELS[cat]) for cat in AttractionCategory}
    )

    selected_cat = st.selectbox(
        t("attr.filter"),
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

    st.subheader(t("attr.plan"))
    st.caption(t("attr.profile_hint"))
    profile_col, save_col, load_col = st.columns([3, 1, 1])
    with profile_col:
        profile_name = st.text_input(
            t("profile.label"),
            key="profile_name",
            placeholder=t("profile.placeholder"),
        )
    with save_col:
        st.markdown("<div style='height: 1.6em'></div>", unsafe_allow_html=True)
        if st.button(
            t("profile.save"),
            key="save_profile_btn",
            disabled=not profile_name.strip(),
            help=t("profile.save_help"),
        ):
            _save_profile_selection(
                profile_name, norm_city, st.session_state.get("chosen_attractions", default_selected)
            )
            st.success(t("profile.saved", city=display_city, name=profile_name.strip()))
    with load_col:
        st.markdown("<div style='height: 1.6em'></div>", unsafe_allow_html=True)
        if st.button(
            t("profile.load"),
            key="load_profile_btn",
            disabled=not profile_name.strip(),
            help=t("profile.load_help"),
        ):
            saved = _load_profile(profile_name).get(norm_city, [])
            st.session_state["chosen_attractions"] = [n for n in saved if n in attr_names]
            if saved:
                st.success(t("profile.loaded", city=display_city, name=profile_name.strip()))
            else:
                st.info(t("profile.empty", city=display_city, name=profile_name.strip()))

    chosen_names = st.multiselect(
        t("attr.choose"),
        options=attr_names,
        default=default_selected,
        key="chosen_attractions",
    )
    chosen_objects = [a for a in all_city_attrs if a.name in chosen_names]

    # Kalkulator City Card
    cards = get_city_cards(norm_city)
    if cards:
        st.subheader(t("card.header"))
        default_transit_cost = 15.0 if all_city_attrs[0].currency == "EUR" else 25.0
        transit_cost = st.number_input(
            t("card.transit_cost", cur=all_city_attrs[0].currency),
            min_value=0.0,
            value=default_transit_cost,
            step=5.0,
            key="transit_est_cost",
            help=t("card.transit_help"),
        )

        best_eval = suggest_best_city_card(
            norm_city,
            chosen_objects,
            estimated_transit_cost=transit_cost,
            profile=attraction_profile,
        )
        if best_eval and best_eval.is_recommended:
            st.success(t("card.recommendation", summary=best_eval.summary))
        elif chosen_objects:
            st.info(t("card.not_optimal", n=len(chosen_objects)))

        evals = evaluate_city_cards(
            norm_city,
            chosen_objects,
            estimated_transit_cost=transit_cost,
            profile=attraction_profile,
        )
        if evals:
            card_rows = []
            for ev in evals:
                card_rows.append(
                    {
                        t("card.col.name"): ev.variant.name,
                        t("card.col.price"): f"{ev.card_price:.2f} {ev.currency}"
                        + ("" if ev.variant.price_verified else t("card.unverified")),
                        t("card.col.valid"): f"{ev.variant.duration_hours}h",
                        t("card.col.transit"): t("yes") if ev.variant.includes_public_transit else t("no"),
                        t("card.col.without"): f"{ev.total_cost_without_card:.2f} {ev.currency}",
                        t("card.col.with"): f"{ev.total_cost_with_card:.2f} {ev.currency}",
                        t("card.col.balance"): (
                            t("card.gain", amount=f"{ev.net_savings:.2f}", cur=ev.currency)
                            if ev.net_savings > 0
                            else f"{ev.net_savings:.2f} {ev.currency}"
                        ),
                        t("card.col.recommended"): t("card.rec_yes") if ev.is_recommended else t("card.rec_no"),
                    }
                )
            st.dataframe(card_rows, width="stretch", hide_index=True)

    # Prezentacja listy atrakcji w wybranej kategorii
    st.subheader(t("attr.in_category", category=cat_labels.get(selected_cat, selected_cat)))
    cols = st.columns(2)
    for idx, attr in enumerate(filtered_attrs):
        col = cols[idx % 2]
        with col:
            price_val, price_label, price_source = best_price_for_attraction(
                attr, attraction_profile
            )
            price_text = (
                f"{price_val:.2f} {attr.currency}" if price_val > 0 else t("attr.free")
            )
            if attr.price_is_from:
                price_text = t("attr.from_prefix", text=price_text)
            if price_source is not None:
                price_text += f" ({price_label})"
                if not price_source.price_verified:
                    price_text += t("price.unverified_suffix")
            elif not attr.price_verified:
                price_text += t("price.unverified_suffix")
            if attr.price_is_from:
                price_text += f" — {price_from_note(attr)}"
            discount_note = (
                t("attr.card_discount", pct=f"{attr.default_card_discount_percent:.0f}")
                if attr.default_card_discount_percent > 0
                else ""
            )
            with st.container(border=True):
                st.markdown(f"**{attr.name}**")
                st.caption(
                    f"{label_or('cat', attr.category.value, CATEGORY_LABELS.get(attr.category, attr.category.value))}"
                    f" • {price_text}{discount_note}"
                )
                st.write(attr.description)
                if attr.address:
                    st.caption(f"📍 {attr.address}")
                if attr.official_url:
                    st.markdown(f"[{t('attr.official')}]({attr.official_url})")


def address_picker(label: str, default_text: str, state_key: str):
    """Pole adresu + podpowiedzi z geocodingu MOTIS do wyboru (zamiast wpisywania z palca
    na ślepo — literówka w mieście/ulicy dotąd potrafiła po cichu trafić w zły punkt)."""
    query = st.text_input(label, value=default_text, key=f"{state_key}_query")
    if len(query.strip()) < 3:
        st.caption(t("addr.min_chars"))
        return None
    try:
        suggestions = motis_client.geocode_suggestions(query)
    except MotisError as exc:
        st.caption(t("addr.unavailable", exc=exc))
        return None
    if not suggestions:
        st.caption(t("addr.no_match"))
        return None
    idx = st.selectbox(
        t("addr.pick", label=label.lower()),
        options=list(range(len(suggestions))),
        format_func=lambda i: suggestions[i]["name"],
        key=f"{state_key}_choice",
    )
    return suggestions[idx]


wiek = st.number_input(
    t("age.label"),
    min_value=0,
    max_value=120,
    value=30,
    step=1,
    help=t("age.help"),
    key="w_wiek",
)
obywatelstwo = st.selectbox(
    t("citizen.label"),
    [None, "PL", "UE", "poza_UE"],
    format_func=lambda o: t("citizen.none") if o is None else t(f"citizen.{o}"),
    help=t("citizen.help"),
    key="w_obywatelstwo",
)
c_attr_profile1, c_attr_profile2 = st.columns(2)
uczen_student = c_attr_profile1.checkbox(
    t("student.label"),
    help=t("student.help"),
    key="w_uczen_student",
)
senior_attrakcje = c_attr_profile2.checkbox(
    t("senior.label"),
    help=t("senior.help"),
    key="w_senior",
)
_kraj_legitymacji = st.selectbox(
    t("idcountry.label"),
    ["none", "PL", "DE", "other"],
    format_func=lambda k: t(f"idcountry.{k}"),
    help=t("idcountry.help"),
    key="w_kraj_legitymacji",
)
_kod_kraju = {"PL": "PL", "DE": "DE"}.get(_kraj_legitymacji)
attraction_profile = AttractionDiscountProfile(
    age=wiek,
    is_student=uczen_student,
    is_senior=senior_attrakcje,
    documents=(
        [HeldDocument("legitymacja_studencka", _kod_kraju)] if _kod_kraju else []
    ),
)

st.subheader(t("section.route"))
c_origin, c_dest = st.columns(2)
with c_origin:
    origin_resolved = address_picker(t("addr.origin"), DEFAULT_FROM, "origin")
with c_dest:
    dest_resolved = address_picker(t("addr.dest"), DEFAULT_TO, "dest")

# Widgety z domyślną wartością zależną od wieku (value=wiek < 18 itd.) są celowo BEZ key=: zmiana
# wieku ma je nadal przestawiać na nową podpowiedź, jak dotąd. Ceną jest to, że ręczne
# nadpisanie takiego checkboxa przepada przy zmianie języka (zmienia się jego etykieta).
with st.form("search"):
    date = st.date_input(
        t("form.date"),
        dt.date.today() + dt.timedelta(days=5),
        help=t("form.date_help"),
        key="w_date",
    )
    godzina = st.time_input(
        t("form.time"),
        dt.time(6, 0),
        step=dt.timedelta(minutes=15),
        help=t("form.time_help"),
        key="w_time",
    )
    bagaz_rejestrowany = st.checkbox(
        t("form.baggage"),
        value=True,
        help=t("form.baggage_help"),
        key="w_bagaz",
    )
    c1, c2 = st.columns(2)
    pkp = c1.selectbox(
        t("form.pkp"), PKP_ULGI, format_func=lambda k: label_or("pkp", k, k), key="w_pkp"
    )
    bc = c2.selectbox(
        t("form.bahncard"),
        ["brak", "25", "50", "100"],
        format_func=lambda k: t(f"bc.{k}"),
        key="w_bc",
    )
    c3, c4 = st.columns(2)
    ztm_ulgowy = c3.checkbox(
        t("form.ztm_lublin"),
        value=wiek < 18,
        help=t("form.ztm_lublin_help"),
    )
    vrr_dziecko = c4.checkbox(
        t("form.vrr"),
        value=6 <= wiek <= 14,
        help=t("form.vrr_help"),
    )
    child_with_guardian = False
    if 6 <= wiek <= 14:
        child_with_guardian = st.checkbox(
            t("form.guardian"),
            value=False,
            help=t("form.guardian_help"),
        )
    st.caption(t("form.kinder_other"))
    k1, k2, k3 = st.columns(3)
    hvv_dziecko = k1.checkbox(t("form.hamburg"), value=6 <= wiek <= 14)
    mvv_dziecko = k2.checkbox(t("form.munich"), value=6 <= wiek <= 14)
    vrs_koln_dziecko = k3.checkbox(t("form.cologne"), value=6 <= wiek <= 14)
    st.caption(t("form.reduced_other"))
    u1, u2, u3, u4, u5 = st.columns(5)
    ztm_warszawa_ulgowy = u1.checkbox(t("city.warszawa"), value=wiek < 18)
    mpk_krakow_ulgowy = u2.checkbox(t("city.krakow"), value=wiek < 18)
    ztm_poznan_ulgowy = u3.checkbox(t("city.poznan"), value=wiek < 18)
    mpk_wroclaw_ulgowy = u4.checkbox(t("city.wroclaw"), value=wiek < 18)
    bvg_berlin_ulgowy = u5.checkbox(t("city.berlin"), value=wiek < 18)
    st.caption(t("form.free_caption"))
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    ztm_warszawa_bezplatny = b1.checkbox(
        t("free.warszawa"),
        value=wiek >= 70,
        help=t("free.warszawa_help"),
    )
    mpk_krakow_bezplatny = b2.checkbox(
        t("free.krakow"),
        value=wiek >= 70,
        help=t("free.krakow_help"),
    )
    mpk_wroclaw_bezplatny = b3.checkbox(
        t("free.wroclaw"),
        value=wiek <= 7 or wiek <= 21 or wiek >= 65,
        help=t("free.wroclaw_help"),
    )
    ztm_lublin_bezplatny = b4.checkbox(
        t("free.lublin"),
        value=wiek >= 65 or wiek <= 14,
        help=t("free.lublin_help"),
    )
    ztm_poznan_bezplatny = b5.checkbox(
        t("free.poznan"),
        value=wiek >= 70,
        help=t("free.poznan_help"),
    )
    bvg_berlin_schwerbehindert = b6.checkbox(
        t("free.berlin"),
        help=t("free.berlin_help"),
    )
    schwerbehinderte_wertmarke_de = st.checkbox(
        t("free.de_wertmarke"),
        help=t("free.de_wertmarke_help"),
    )
    submitted = st.form_submit_button(t("form.submit"))

if submitted:
    if origin_resolved is None or dest_resolved is None:
        st.error(t("err.pick_address"))
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
        hvv_dziecko=hvv_dziecko,
        mvv_dziecko=mvv_dziecko,
        vrs_koln_dziecko=vrs_koln_dziecko,
        schwerbehinderte_wertmarke_de=schwerbehinderte_wertmarke_de,
        age=wiek,
        child_with_guardian=child_with_guardian,
        obywatelstwo=obywatelstwo,
        legitymacja_zagraniczna=_kraj_legitymacji in ("DE", "other"),
    )
    for ostrzezenie in foreigner_warnings_for(profile):
        st.warning(ostrzezenie)
    try:
        with st.spinner(t("search.spinner")):
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
                departure_time=godzina.strftime("%H:%M:%S"),
                discounts=profile,
                checked_baggage=bagaz_rejestrowany,
            )
            # search() (routing/search_service.py, współdzielone z API w api/) nie przekazuje
            # alternative_destination_stops — patrz komentarz tam / w demo.py (podmieniłoby
            # rzeczywisty adres docelowy na sztywny dworzec, ucinając ostatni odcinek do adresu).
            search_result = search(request)
            built, skipped, recs, other_day = (
                search_result.built,
                search_result.skipped,
                search_result.recommendations,
                search_result.other_day,
            )
    except MotisError as exc:
        st.error(t("err.motis", exc=exc))
        st.stop()
    except Exception as exc:  # np. MOTIS nieuruchomiony
        st.error(t("err.search", exc=exc))
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
        "other_day": other_day,
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
    other_day = result.get("other_day", [])

    st.caption(
        t(
            "res.summary",
            origin=request.origin_label,
            dest=request.destination_label,
            date=date,
            built=len(built),
            skipped=len(skipped),
        )
    )
    if skipped:
        with st.expander(t("res.skipped")):
            for s in skipped:
                st.write(f"**{s.variant_name}**: {s.reason}")
    if not built:
        st.error(
            t("res.none_reasons", reasons=" ".join(f"{s.variant_name}: {s.reason}" for s in skipped))
            if skipped
            else t("res.none")
        )
        render_other_day_section(
            other_day, lambda it: render_itinerary(it, wiek, bc if bc != "brak" else None)
        )
        st.stop()
    header_col, toggle_col = st.columns([3, 1])
    with header_col:
        st.header(t("res.recommendations"))
    more_keys = [key for key in RECOMMENDATION_LABELS if key not in TOP_CATEGORY_KEYS]
    with toggle_col:
        pokaz_wiecej = st.checkbox(t("res.show_more", n=len(more_keys)), value=False, key="w_show_more")

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
            st.caption(t("res.same_route", label=rec_label(owner_key)))
        if key in SAFE_CATEGORY_KEYS and recs[key].is_safe_fallback:
            st.info(t("res.no_safe"))
        price_note = price_ranking_note(key, recs[key], built)
        if price_note:
            st.info(price_note)
        if key in ("najmniej_przesiadek", "najmniej_przesiadek_bezpieczna"):
            st.caption(t("res.fewest_transfers_note"))
        st.subheader(recs[key].variant_name)
        render_itinerary(recs[key], wiek, bc if bc != "brak" else None)

    visible_keys = list(RECOMMENDATION_LABELS) if pokaz_wiecej else list(TOP_CATEGORY_KEYS)
    tabs = st.tabs([rec_label(key) for key in visible_keys])
    for tab, key in zip(tabs, visible_keys):
        with tab:
            render_recommendation_tab(key)

    st.header(t("res.all_variants"))
    for it in built:
        if it.is_risky and _is_near_miss_itinerary(it):
            risk_suffix = t("res.risk_near")
        elif it.is_risky:
            risk_suffix = t("res.risk_risky")
        else:
            risk_suffix = ""
        price_text = variant_price_text(it)
        with st.expander(
            t(
                "res.variant_header",
                name=it.variant_name,
                hours=f"{it.total_duration_min / 60:.1f}",
                price=price_text,
                unverified="" if it.price_verified else t("price.unverified_suffix"),
                transfers=it.num_transfers,
                risk=risk_suffix,
            )
        ):
            render_itinerary(it, wiek, bc if bc != "brak" else None)

    render_attractions_and_city_cards(
        request.destination_label,
        fallback_text=st.session_state.get("dest_query", ""),
        attraction_profile=attraction_profile,
    )
