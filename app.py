"""Frontend Streamlit (Sesja 5): ten sam pipeline co demo.py, w przeglądarce.

Uruchomienie:  pip install streamlit  &&  streamlit run app.py
Wymaga działającego MOTIS (localhost:8080), patrz README.md.
"""

import datetime as dt
import json
import re
from html import escape
from pathlib import Path

import streamlit as st
from streamlit_searchbox import st_searchbox

from attractions import (
    CATEGORY_LABELS,
    AttractionCategory,
    HeldDocument,
    best_price_for_attraction,
    evaluate_city_cards,
    get_attractions,
    get_city_cards,
    localized_description,
    normalize_city,
    price_from_note,
    suggest_best_city_card,
)
from attractions import DiscountProfile as AttractionDiscountProfile
from demo import DEFAULT_FROM, DEFAULT_TO
from fares.foreigner_eligibility import warnings_for as foreigner_warnings_for
from fares.model import DiscountProfile
from flights.cabin_baggage import format_breakdown as format_cabin_breakdown
from i18n import DEFAULT_LANG, LANGUAGES, current_lang, exc_text, label_or, t, tm
from places.aliases import local_query, place_text
from routing import motis_client
from routing.card_suggestions import db_distance_km, suggest_bahncard_for_itinerary
from routing.model import LegMode
from routing.motis_client import MotisError
from routing.scoring import (
    RECOMMENDATION_LABELS,
    SAFE_CATEGORY_KEYS,
    price_ranking_note,
)
from routing.search_service import search
from routing.variants import RouteRequest
from ui_helpers import (
    MIN_SUGGEST_CHARS,
    SELECTED_KEY,
    SELECTED_SLOT_KEY,
    best_place,
    format_verified_date,
    leg_price_status,
    leg_source,
    place_input,
    place_label,
    render_bezplatne_info,
    render_other_day_section,
    render_price_summary,
    render_variant_cards,
    render_variant_list,
    set_html_lang,
    status_cell,
    suggest_places,
)
from ui_style import inject_style

with open("fares/data/pkp_intercity.json", encoding="utf-8") as fh:
    PKP_ULGI = list(json.load(fh)["ulgi_procent"])

# set_page_config musi być pierwszym poleceniem st.*, więc tytuł karty czyta język z poprzedniego
# przebiegu (po zmianie języka Streamlit robi rerun, w którym st.session_state["lang"] już jest).
st.set_page_config(
    page_title=t("app.page_title", lang=st.session_state.get("lang", DEFAULT_LANG)),
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_style()
with st.container(key="lang-switch"):
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
st.caption(t("app.subtitle"))

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


def render_foreigner_warnings(warnings) -> None:
    for ostrzezenie in warnings:
        st.warning(tm(ostrzezenie))


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
    render_price_summary(it)
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
                f"{p.amount:.2f} {p.currency}"
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
        src_url, src_date = leg_source(p)
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
                t("col.price_status"): status_cell(leg_price_status(p)),
                t("col.source"): src_url or "",
                t("col.verified"): format_verified_date(src_date) if leg_price_status(p) else "",
                t("col.flight_breakdown"): rozbicie,
                t("col.baggage_tariff"): zrodlo_bagazu,
                t("col.cabin_baggage"): bagaz_podreczny,
                t("col.alt_offer"): alternatywa,
            }
        )
    if not any(p.leg.mode is LegMode.FLIGHT for p in it.legs):
        # rozbicie ceny lotu i cennik bagażu mają sens tylko przy locie — bez lotu to puste kolumny
        for col in (t("col.flight_breakdown"), t("col.baggage_tariff")):
            for row in rows:
                row.pop(col, None)
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            t("col.source"): st.column_config.LinkColumn(
                t("col.source"), display_text=r"https?://(?:www\.)?([^/]+)"
            )
        },
    )
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
                st.warning(t("transfer.risky", reason=tm(w.reason)))
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
                price_text += f" — {price_from_note(attr, lang=current_lang())}"
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
                st.write(localized_description(attr, current_lang()))
                if attr.address:
                    st.caption(f"📍 {attr.address}")
                if attr.official_url:
                    st.markdown(f"[{t('attr.official')}]({attr.official_url})")


def _clear_result() -> None:
    for key in ("search_result", SELECTED_KEY, SELECTED_SLOT_KEY):
        st.session_state.pop(key, None)


def _change_route() -> None:
    """„zmień”: wraca do formularza z nazwami, które znalazł geokoder (do poprawienia). Pola Skąd/Dokąd
    same zauważają zmianę tekstu w session_state (render_place_input)."""
    result = st.session_state.get("search_result")
    if result is not None:
        st.session_state["origin_query"] = result["request"].origin_label
        st.session_state["dest_query"] = result["request"].destination_label
    _clear_result()


def run_search(inputs: dict, origin: dict, dest: dict) -> bool:
    """Szuka połączeń dla gotowych współrzędnych i zapisuje wynik w session_state. False przy błędzie
    (komunikat już wyświetlony)."""
    foreigner_warnings = inputs["foreigner_warnings"]
    try:
        with st.spinner(t("search.spinner")):
            request = RouteRequest(
                origin_stop_id=motis_client.coords_place(origin["lat"], origin["lon"]),
                destination_stop_id=motis_client.coords_place(dest["lat"], dest["lon"]),
                origin_label=origin["name"],
                destination_label=dest["name"],
                date=inputs["date"].isoformat(),
                departure_time=inputs["time"].strftime("%H:%M:%S"),
                discounts=inputs["profile"],
                checked_baggage=inputs["checked_baggage"],
            )
            # search() (routing/search_service.py, współdzielone z API w api/) nie przekazuje
            # alternative_destination_stops — patrz komentarz tam / w demo.py (podmieniłoby
            # rzeczywisty adres docelowy na sztywny dworzec, ucinając ostatni odcinek do adresu).
            search_result = search(request)
    except MotisError as exc:
        render_foreigner_warnings(foreigner_warnings)
        st.error(t("err.motis", exc=tm(exc_text(exc))))
        return False
    except Exception as exc:  # np. MOTIS nieuruchomiony
        render_foreigner_warnings(foreigner_warnings)
        st.error(t("err.search", exc=exc))
        return False
    # Wynik ląduje w session_state, a nie w zwykłej zmiennej lokalnej: widgety POZA formularzem
    # (karty, sortowanie, wybór adresu) wywołują kolejny rerun Streamlita, w którym wysłanie
    # formularza jest znów False - bez zapamiętania wyniku wyszukiwanie "znikałoby".
    st.session_state.pop(SELECTED_KEY, None)
    st.session_state.pop(SELECTED_SLOT_KEY, None)
    st.session_state["search_result"] = {
        "request": request,
        "date": inputs["date"],
        "built": search_result.built,
        "skipped": search_result.skipped,
        "recs": search_result.recommendations,
        "other_day": search_result.other_day,
        "foreigner_warnings": foreigner_warnings,
        # tekst z pola „Dokąd” z chwili wyszukiwania (nazwy miast w lokalnym zapisie, więc „Cologne”
        # też rozpozna miasto): zapas dla atrakcji, gdy adres celu nie zawiera nazwy miasta
        "dest_text": local_query(inputs["dest_text"]),
    }
    return True


def render_search_header(result) -> None:
    request = result["request"]
    with st.container(horizontal=True, vertical_alignment="center"):
        # nazwy miast w języku interfejsu, nazwa lokalna w nawiasie (request trzyma nazwy z geokodera)
        lang = current_lang()
        st.markdown(
            t(
                "res.searching",
                origin=place_text(request.origin_label, lang),
                dest=place_text(request.destination_label, lang),
            )
        )
        st.button(t("res.change"), key="change_route", type="tertiary", on_click=_change_route)
    st.caption(t("res.when", date=result["date"]))


def group_header(title_key: str, hint_key: str) -> None:
    """Nagłówek grupy opcji w formularzu: ikona i tytuł, pod spodem jedno zdanie, czego dotyczy.
    Jeden blok HTML (a nie st.markdown + st.caption): osobne elementy Streamlita nachodziły na siebie.
    """
    st.markdown(
        '<div class="mw-group-head">'
        f'<p class="mw-group-title">{escape(t(title_key))}</p>'
        f'<p class="mw-group-hint">{escape(t(hint_key))}</p>'
        "</div>",
        unsafe_allow_html=True,
    )


st.session_state.setdefault("origin_query", DEFAULT_FROM)
st.session_state.setdefault("dest_query", DEFAULT_TO)


def _search_places(term: str) -> list[tuple[str, dict]]:
    """Funkcja podpowiedzi dla pól Skąd/Dokąd. Błąd geokodera nie psuje strony: lista jest wtedy
    pusta, a pod polami pojawia się krótka informacja (po udanym zapytaniu znika)."""
    try:
        options = suggest_places(term, current_lang())
    except MotisError:
        st.session_state["suggest_error"] = True
        return []
    st.session_state.pop("suggest_error", None)
    return options


def render_place_input(side: str, label: str) -> None:
    """Jedno pole miejsca z podpowiedziami przy pisaniu (streamlit-searchbox). Tekst, który ma być w
    polu, to st.session_state[f"{side}_query"]: ustawiony z zewnątrz („zmień”, test) albo po zmianie
    języka zakłada pole od nowa z tym tekstem. Pole pamięta wybraną podpowiedź w
    st.session_state[f"{side}_sb"], a place_input() czyta ją przy wysłaniu formularza."""
    key, text_key, mirror_key = f"{side}_sb", f"{side}_query", f"{side}_mirror"
    wanted = st.session_state[text_key]
    lang = current_lang()
    if key in st.session_state and (
        st.session_state.get(mirror_key) != wanted or st.session_state.get(f"{side}_lang") != lang
    ):
        del st.session_state[key]
    st_searchbox(
        _search_places,
        placeholder=t("addr.placeholder", n=MIN_SUGGEST_CHARS),
        label=label,
        help=t("addr.help"),
        default=wanted,
        default_searchterm=wanted,
        default_use_searchterm=True,
        edit_after_submit="current",
        debounce=300,  # ms po ostatnim znaku, zanim zapytamy geokoder
        rerun_scope="fragment",
        key=key,
    )
    text, pick = place_input(side)
    st.session_state[text_key] = st.session_state[mirror_key] = text
    st.session_state[f"{side}_lang"] = lang
    if pick is not None:  # pole zostawia wpisany tekst, więc pod spodem widać, co dokładnie wybrano
        st.caption(t("addr.picked", place=place_label(pick, lang=lang)))


# Pola Skąd/Dokąd są poza st.form i w osobnym fragmencie: pisanie przeładowuje tylko ten fragment
# (a nie cały ekran), więc pokazany wynik wyszukiwania zostaje (jest w st.session_state["search_result"]).
@st.fragment
def render_place_inputs() -> None:
    c_origin, c_dest = st.columns(2)
    with c_origin:
        render_place_input("origin", t("addr.origin"))
    with c_dest:
        render_place_input("dest", t("addr.dest"))
    if st.session_state.get("suggest_error"):
        st.caption(t("addr.suggest_error"))


render_place_inputs()

# Formularz: data, godzina i opcje wysyłane jednym przyciskiem (nic się nie odświeża przy ich zmianie).
# Widgety z domyślną wartością zależną od wieku (value=wiek < 18 itd.)
# są celowo BEZ key=: zmiana wieku nadal przestawia je na nową podpowiedź (przy wysłaniu formularza).
# Ceną jest to, że ręczne nadpisanie takiego checkboxa przepada przy zmianie wieku lub języka.
with st.form("search", border=False):
    c_date, c_time = st.columns(2)
    date = c_date.date_input(
        t("form.date"),
        dt.date.today() + dt.timedelta(days=5),
        help=t("form.date_help"),
        key="w_date",
    )
    godzina = c_time.time_input(
        t("form.time"),
        dt.time(6, 0),
        step=dt.timedelta(minutes=15),
        help=t("form.time_help"),
        key="w_time",
    )
    # Wszystkie opcje w 5 grupach z research/ui-styl.md (§7); grupy 1-4 w jednym panelu „Więcej
    # opcji”, grupa 5 (przejazdy bezpłatne) w osobnym, bo Streamlit nie zagnieżdża expanderów.
    # Nazwy zmiennych, domyślne wartości i brak kluczy przy widgetach zależnych od wieku bez zmian.
    with st.expander(t("form.more")):
        st.caption(t("form.more_hint"))
        with st.container(border=True, key="group-passenger"):
            group_header("group.passenger", "group.passenger_hint")
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
            _kraj_legitymacji = st.selectbox(
                t("idcountry.label"),
                ["none", "PL", "DE", "other"],
                format_func=lambda k: t(f"idcountry.{k}"),
                help=t("idcountry.help"),
                key="w_kraj_legitymacji",
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
        with st.container(border=True, key="group-rail"):
            group_header("group.rail", "group.rail_hint")
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
            child_with_guardian = False
            if 6 <= wiek <= 14:
                child_with_guardian = st.checkbox(
                    t("form.guardian"),
                    value=False,
                    help=t("form.guardian_help"),
                )
        with st.container(border=True, key="group-baggage"):
            group_header("group.baggage", "group.baggage_hint")
            bagaz_rejestrowany = st.checkbox(
                t("form.baggage"),
                value=True,
                help=t("form.baggage_help"),
                key="w_bagaz",
            )
        with st.container(border=True, key="group-city"):
            group_header("group.city", "group.city_hint")
            st.markdown(
                f'<p class="mw-sub-title">🇵🇱 {escape(t("group.city_pl"))}</p>',
                unsafe_allow_html=True,
            )
            st.caption(t("form.reduced_other"))
            u1, u2, u3 = st.columns(3)
            ztm_ulgowy = u1.checkbox(
                t("form.ztm_lublin"),
                value=wiek < 18,
                help=t("form.ztm_lublin_help"),
            )
            ztm_warszawa_ulgowy = u2.checkbox(t("city.warszawa"), value=wiek < 18)
            mpk_krakow_ulgowy = u3.checkbox(t("city.krakow"), value=wiek < 18)
            u4, u5, _u6 = st.columns(3)
            ztm_poznan_ulgowy = u4.checkbox(t("city.poznan"), value=wiek < 18)
            mpk_wroclaw_ulgowy = u5.checkbox(t("city.wroclaw"), value=wiek < 18)
            st.markdown(
                f'<p class="mw-sub-title">🇩🇪 {escape(t("group.city_de"))}</p>',
                unsafe_allow_html=True,
            )
            bvg_berlin_ulgowy = st.checkbox(t("city.berlin"), value=wiek < 18)
            st.caption(t("form.kinder_other"))
            vrr_dziecko = st.checkbox(
                t("form.vrr"),
                value=6 <= wiek <= 14,
                help=t("form.vrr_help"),
            )
            k1, k2, k3 = st.columns(3)
            hvv_dziecko = k1.checkbox(t("form.hamburg"), value=6 <= wiek <= 14)
            mvv_dziecko = k2.checkbox(t("form.munich"), value=6 <= wiek <= 14)
            vrs_koln_dziecko = k3.checkbox(t("form.cologne"), value=6 <= wiek <= 14)
    with st.expander(t("group.free")):
        st.caption(t("form.free_caption"))
        with st.container(border=True, key="group-free-pl"):
            st.markdown(
                f'<p class="mw-sub-title">🇵🇱 {escape(t("group.city_pl"))}</p>',
                unsafe_allow_html=True,
            )
            ztm_warszawa_bezplatny = st.checkbox(
                t("free.warszawa"),
                value=wiek >= 70,
                help=t("free.warszawa_help"),
            )
            mpk_krakow_bezplatny = st.checkbox(
                t("free.krakow"),
                value=wiek >= 70,
                help=t("free.krakow_help"),
            )
            ztm_poznan_bezplatny = st.checkbox(
                t("free.poznan"),
                value=wiek >= 70,
                help=t("free.poznan_help"),
            )
            mpk_wroclaw_bezplatny = st.checkbox(
                t("free.wroclaw"),
                value=wiek <= 7 or wiek <= 21 or wiek >= 65,
                help=t("free.wroclaw_help"),
            )
            ztm_lublin_bezplatny = st.checkbox(
                t("free.lublin"),
                value=wiek >= 65 or wiek <= 14,
                help=t("free.lublin_help"),
            )
        with st.container(border=True, key="group-free-de"):
            st.markdown(
                f'<p class="mw-sub-title">🇩🇪 {escape(t("group.city_de"))}</p>',
                unsafe_allow_html=True,
            )
            bvg_berlin_schwerbehindert = st.checkbox(
                t("free.berlin"),
                help=t("free.berlin_help"),
            )
            schwerbehinderte_wertmarke_de = st.checkbox(
                t("free.de_wertmarke"),
                help=t("free.de_wertmarke_help"),
            )
    submitted = st.form_submit_button(
        t("form.submit"), type="primary", width="stretch", icon=":material/search:"
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

if submitted:
    _clear_result()
    origin_text, origin_pick = place_input("origin")
    dest_text, dest_pick = place_input("dest")
    if not origin_text.strip() or not dest_text.strip():
        st.error(t("addr.empty"))
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
    inputs = {
        "profile": profile,
        "date": date,
        "time": godzina,
        "checked_baggage": bagaz_rejestrowany,
        "dest_text": dest_text,
        "foreigner_warnings": foreigner_warnings_for(profile),
    }
    # wybrana podpowiedź idzie wprost do wyszukiwania; sam wpisany tekst - najlepsze dopasowanie
    try:
        with st.spinner(t("search.spinner")):
            origin = origin_pick or best_place(origin_text)
            dest = dest_pick or best_place(dest_text)
    except MotisError as exc:
        render_foreigner_warnings(inputs["foreigner_warnings"])
        st.error(t("err.motis", exc=tm(exc_text(exc))))
        st.stop()
    for text, field, place in (
        (origin_text, t("addr.origin"), origin),
        (dest_text, t("addr.dest"), dest),
    ):
        if place is None:
            st.error(t("addr.not_found", text=text.strip(), field=field.lower()))
            st.stop()
    run_search(inputs, origin, dest)

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
    existing_bahncard = None if bc == "brak" else bc
    render_search_header(result)
    render_foreigner_warnings(result.get("foreigner_warnings", []))
    if skipped:
        st.caption(t("res.skipped_note", n=len(skipped)))
    if not built:
        st.error(
            t(
                "res.none_reasons",
                reasons=" ".join(f"{tm(s.variant_name)}: {tm(s.reason)}" for s in skipped),
            )
            if skipped
            else t("res.none")
        )
        render_other_day_section(
            other_day, lambda it: render_itinerary(it, wiek, existing_bahncard)
        )
        st.stop()

    def render_details(it) -> None:
        render_itinerary(it, wiek, existing_bahncard)

    render_variant_cards(built, recs, render_details)

    with st.expander(t("res.see_all")):
        st.caption(t("res.summary", built=len(built), skipped=len(skipped)))
        if skipped:
            # powody pominięcia są tu, w jednym miejscu, razem z resztą opcji (nad listą jest tylko
            # liczba pominiętych)
            st.subheader(t("res.skipped"))
            for s in skipped:
                st.markdown(f"- **{tm(s.variant_name)}**: {tm(s.reason)}")
        render_variant_list(built, render_details)

        st.subheader(t("res.recommendations"))

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
            if price_note is not None and price_note.key == "rank.skipped_cheaper":
                # tańszy wariant bez potwierdzonej ceny jest normalnie na liście i na karcie szacunku
                st.caption(t("rank.cheaper_in_list"))
            elif price_note:
                st.info(tm(price_note))
            if key in ("najmniej_przesiadek", "najmniej_przesiadek_bezpieczna"):
                st.caption(t("res.fewest_transfers_note"))
            st.subheader(tm(recs[key].variant_name))
            render_itinerary(recs[key], wiek, existing_bahncard)

        tabs = st.tabs([rec_label(key) for key in RECOMMENDATION_LABELS])
        for tab, key in zip(tabs, RECOMMENDATION_LABELS):
            with tab:
                render_recommendation_tab(key)

    render_attractions_and_city_cards(
        request.destination_label,
        fallback_text=result.get("dest_text", ""),
        attraction_profile=attraction_profile,
    )
