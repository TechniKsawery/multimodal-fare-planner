"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import json
from datetime import date
from urllib.parse import urlparse

import streamlit as st

from fares.eligibility_info import eligibility_for, explain_ticket
from fares.model import PriceType
from i18n import label_or, t, tm
from routing.model import LegMode


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


# --- status ceny, źródło i data weryfikacji (ekran wyniku, research/ui-projekt.md §2, §6) ---
# Tylko prezentacja: statusy wynikają z pól, które model już ma (PricedLeg.price_known /
# price_verified / price_type / breakdown), nic nie jest przeliczane ani zgadywane.

PRICE_OFFICIAL = "OFFICIAL"
PRICE_ESTIMATE = "ESTIMATE"
PRICE_NO_PRICE = "NO_PRICE"
_STATUS_RANK = {PRICE_OFFICIAL: 0, PRICE_ESTIMATE: 1, PRICE_NO_PRICE: 2}
_STATUS_KEY = {PRICE_OFFICIAL: "official", PRICE_ESTIMATE: "estimate", PRICE_NO_PRICE: "no_price"}
_STATUS_EMOJI = {PRICE_OFFICIAL: "🟢", PRICE_ESTIMATE: "🟡", PRICE_NO_PRICE: "⚪"}
_STATUS_BADGE_COLOR = {PRICE_OFFICIAL: "green", PRICE_ESTIMATE: "orange", PRICE_NO_PRICE: "gray"}


def leg_price_status(p) -> str | None:
    """Status ceny odcinka; None dla odcinka pieszego (nie ma ceny).

    NO_PRICE: kwoty nie znamy albo jest to wartość zastępcza (breakdown["wartosc_zastepcza"]).
    ESTIMATE: kwota znana, ale nie jest sztywną taryfą — przedział (zakres_cen), price_type
    "szacunek" albo cena niepotwierdzona. OFFICIAL: wyłącznie price_type "oficjalna_taryfa" ORAZ
    price_verified; przy wątpliwości status jest słabszy, nigdy mocniejszy."""
    if p.leg.mode is LegMode.WALK:
        return None
    if not p.price_known or p.breakdown.get("wartosc_zastepcza"):
        return PRICE_NO_PRICE
    if p.breakdown.get("zakres_cen"):
        return PRICE_ESTIMATE
    if p.price_verified and p.price_type == PriceType.OFFICIAL.value:
        return PRICE_OFFICIAL
    return PRICE_ESTIMATE


def itinerary_price_status(it) -> str:
    """Status ceny łącznej = najsłabszy status odcinków z ceną; wariant bez żadnej ceny albo z
    ceną częściową (Itinerary.price_status) to NO_PRICE."""
    if it.price_status != "pelna":
        return PRICE_NO_PRICE
    statuses = [s for s in (leg_price_status(p) for p in it.legs) if s]
    if it.total_price_pln_high is not None:
        statuses.append(PRICE_ESTIMATE)
    return max(statuses, key=_STATUS_RANK.__getitem__, default=PRICE_NO_PRICE)


def status_label(status: str) -> str:
    return t(f"badge.{_STATUS_KEY[status]}")


def status_cell(status: str | None) -> str:
    """Tekst statusu do komórki tabeli (emoji + etykieta, żeby nie polegać na samym kolorze)."""
    return f"{_STATUS_EMOJI[status]} {status_label(status)}" if status else ""


def leg_source(p) -> tuple[str | None, str | None]:
    """(URL źródła cennika, data weryfikacji ISO) z breakdown odcinka; None, gdy moduł taryfy
    tego nie podaje (dziś: tylko część kalkulatorów, zob. opis PR). Nie zgadujemy źródła."""
    b = p.breakdown
    url = next((v for v in (b.get("zrodlo_url"), b.get("zrodlo")) if str(v or "").startswith("http")), None)
    return url, b.get("data_weryfikacji") or b.get("data_odczytu")


def source_host(url: str) -> str:
    host = urlparse(url).netloc
    return host.removeprefix("www.") or url


def format_verified_date(iso: str | None) -> str:
    if not iso:
        return t("source.none")
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def itinerary_verification(it) -> tuple[list[str], str | None, int, int]:
    """(hosty źródeł, NAJSTARSZA data weryfikacji ISO, odcinki ze źródłem i datą, odcinki z ceną).
    Najstarsza data, bo cała trasa jest tak aktualna jak jej najmniej świeży odcinek."""
    hosts, dates, covered, priced = [], [], 0, 0
    for p in it.legs:
        if leg_price_status(p) is None or not p.price_known:
            continue
        priced += 1
        url, day = leg_source(p)
        if url and day:
            covered += 1
        if url and source_host(url) not in hosts:
            hosts.append(source_host(url))
        if day:
            dates.append(day)
    return hosts, (min(dates) if dates else None), covered, priced


def render_price_summary(it) -> None:
    """Pod metrykami ekranu wyniku: badge statusu ceny łącznej, jedno zdanie wyjaśnienia oraz
    źródło i data weryfikacji (z zastrzeżeniem, ile odcinków ma takie dane)."""
    status = itinerary_price_status(it)
    st.badge(status_label(status), color=_STATUS_BADGE_COLOR[status])
    st.caption(t(f"badge.explain_{_STATUS_KEY[status]}"))
    hosts, oldest, covered, priced = itinerary_verification(it)
    if priced:
        st.caption(
            f"{t('col.source')}: {', '.join(hosts) or t('source.none')} • "
            f"{t('col.verified')}: {format_verified_date(oldest)}"
        )
        if covered < priced:
            st.caption(t("source.coverage", n=covered, total=priced))


# --- karty wariantów: najtańsza potwierdzona / najtańsza wg szacunku (research/ui-projekt.md, etap 2) ---
# Tylko prezentacja: wybór wśród już policzonych wariantów, bez zmian w cenach i taryfach.


def is_price_confirmed(it) -> bool:
    """Wszystkie odcinki płatne mają znaną i potwierdzoną cenę (PricedLeg.price_verified), a cena
    łączna jest jedną kwotą, nie przedziałem. Brak ceny i cena częściowa nigdy nie są potwierdzone."""
    if it.price_status != "pelna" or it.total_price_pln_high is not None:
        return False
    return all(p.price_verified for p in it.legs if p.leg.mode is not LegMode.WALK)


def _cheapest_key(it) -> tuple[float, float]:
    return it.total_price_pln, it.total_duration_min  # remis ceny rozstrzyga krótszy czas


def cheapest_variant_cards(built) -> tuple[object | None, object | None]:
    """(najtańsza potwierdzona, najtańsza wg szacunku). Wariant z "brak ceny" lub "ceną częściową"
    nie wygrywa żadnej kategorii. Szacunek liczy się od dolnej granicy przedziału. Gdy oba wskazują
    ten sam wariant, zwraca go jako potwierdzoną, a szacunek jako None (jedna karta)."""
    full = [it for it in built if it.price_status == "pelna"]
    confirmed = min((it for it in full if is_price_confirmed(it)), key=_cheapest_key, default=None)
    estimate = min(full, key=_cheapest_key, default=None)
    if confirmed is not None and estimate is not None and confirmed is estimate:
        estimate = None
    return confirmed, estimate


SELECTED_KEY = "selected_variant"  # indeks wariantu w st.session_state["search_result"]["built"]
SORT_OPTIONS = ("price", "time", "transfers")


def route_summary(it) -> str:
    """Skrót przystanków: "Lublin → Warszawa Wschodnia → Gdańsk Główny" (początek, miejsca zmiany
    odcinka i koniec; kolejne powtórzenia tej samej nazwy są zwijane)."""
    names = [it.legs[0].leg.origin_name] + [p.leg.destination_name for p in it.legs]
    stops = [n for i, n in enumerate(names) if i == 0 or n != names[i - 1]]
    return " → ".join(stops)


def carriers_summary(it) -> str:
    """Przewoźnicy odcinków w kolejności jazdy (bez powtórzeń); gdy odcinek nie ma przewoźnika,
    jego rodzaj transportu. Odcinki piesze są pomijane."""
    seen: list[str] = []
    for p in it.legs:
        if p.leg.mode is LegMode.WALK:
            continue
        name = p.leg.carrier_name or label_or("mode", p.leg.mode.value, p.leg.mode.value)
        if name not in seen:
            seen.append(name)
    return ", ".join(seen)


def time_span(it) -> str:
    """"06:00 → 14:10" (z "+1" przy przyjeździe w kolejnym dniu)."""
    first, last = it.legs[0].leg.depart, it.legs[-1].leg.arrive
    days = (last.date() - first.date()).days
    return f"{first:%H:%M} → {last:%H:%M}" + (f" +{days}" if days > 0 else "")


def variant_index(built, it) -> int:
    return next(i for i, x in enumerate(built) if x is it)


def _sort_key(sort: str):
    if sort == "time":
        return lambda it: (it.total_duration_min, it.total_price_pln)
    if sort == "transfers":
        return lambda it: (it.num_transfers, it.total_duration_min, it.total_price_pln)
    # cena: warianty bez pełnej ceny (brak / częściowa) na końcu, nie na początku jako "0 zł"
    return lambda it: (it.price_status != "pelna", it.total_price_pln, it.total_duration_min)


def variant_list(built, sort: str = "price", only_confirmed: bool = False) -> list[int]:
    """Indeksy WSZYSTKICH zbudowanych wariantów w kolejności sortowania; filtr "tylko potwierdzone"
    zostawia warianty, dla których is_price_confirmed. Sortowanie stabilne."""
    idx = [i for i, it in enumerate(built) if not only_confirmed or is_price_confirmed(it)]
    key = _sort_key(sort)
    return sorted(idx, key=lambda i: key(built[i]))


def select_variant(index: int) -> None:
    st.session_state[SELECTED_KEY] = index


def _variant_card(built, it, title: str, tag: str | None = None, key: str = "card") -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if tag:
            st.markdown(f":orange-badge[{tag}]")
        st.subheader(route_summary(it))
        st.caption(f"{tm(it.variant_name)} • {carriers_summary(it)}")
        st.markdown(f"🕒 {time_span(it)}")
        st.caption(
            t(
                "cards.meta",
                hours=f"{it.total_duration_min / 60:.1f}",
                transfers=it.num_transfers,
            )
        )
        st.markdown(f"**{variant_price_text(it)}**")
        status = itinerary_price_status(it)
        st.badge(status_label(status), color=_STATUS_BADGE_COLOR[status])
        st.button(
            t("cards.details"),
            key=f"show_{key}",
            on_click=select_variant,
            args=(variant_index(built, it),),
        )


def render_variant_cards(built) -> None:
    """Na górze wyników: dwie karty obok siebie albo jedna, gdy to ten sam wariant. Przycisk
    "Pokaż szczegóły" wybiera wariant (SELECTED_KEY); sam wynik wyszukiwania zostaje w session_state."""
    confirmed, estimate = cheapest_variant_cards(built)
    if confirmed is None and estimate is None:
        st.info(t("cards.none"))
        return
    if estimate is None:
        _variant_card(built, confirmed, t("cards.confirmed"), key="confirmed")
        return
    if confirmed is None:
        st.info(t("cards.no_confirmed"))
        _variant_card(built, estimate, t("cards.estimate"), t("cards.estimate_tag"), key="estimate")
        return
    left, right = st.columns(2)
    with left:
        _variant_card(built, confirmed, t("cards.confirmed"), key="confirmed")
    with right:
        _variant_card(built, estimate, t("cards.estimate"), t("cards.estimate_tag"), key="estimate")


def _variant_row(it) -> dict:
    status = itinerary_price_status(it)
    return {
        t("list.col.variant"): ("⚠️ " if it.is_risky else "") + tm(it.variant_name),
        t("col.route"): route_summary(it),
        t("metric.time"): f"{it.total_duration_min / 60:.1f} h",
        t("metric.transfers"): it.num_transfers,
        t("list.col.price"): variant_price_text(it),
        t("col.price_status"): status_cell(status),
    }


def _on_row_select(table_key: str, order: list[int]) -> None:
    rows = st.session_state[table_key].selection.rows
    if rows:
        select_variant(order[rows[0]])


def render_variant_list(built) -> None:
    """Pełna lista wszystkich wariantów (potwierdzone, szacunki, loty) z sortowaniem i filtrem
    "tylko potwierdzone". Zaznaczenie wiersza wybiera wariant do podglądu szczegółów."""
    st.header(t("res.all_variants"))
    c_sort, c_filter = st.columns([2, 1])
    sort = c_sort.selectbox(
        t("list.sort"),
        SORT_OPTIONS,
        format_func=lambda k: t(f"list.sort_{k}"),
        key="w_variant_sort",
    )
    only_confirmed = c_filter.checkbox(t("list.only_confirmed"), key="w_only_confirmed")
    order = variant_list(built, sort, only_confirmed)
    if not order:
        st.info(t("list.empty"))
        return
    st.caption(t("list.hint", shown=len(order), total=len(built)))
    # klucz zależy od sortowania i filtra: po zmianie kolejności stare zaznaczenie wiersza traci sens
    table_key = f"variant_table_{sort}_{int(only_confirmed)}"
    st.dataframe(
        [_variant_row(built[i]) for i in order],
        width="stretch",
        hide_index=True,
        on_select=lambda: _on_row_select(table_key, order),
        selection_mode="single-row",
        key=table_key,
    )
