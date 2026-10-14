"""Fragmenty UI Streamlit wydzielone z app.py, żeby dało się je testować bez uruchamiania całej aplikacji."""

import json
import re
import unicodedata
from datetime import date
from urllib.parse import urlparse

import streamlit as st

from fares.eligibility_info import eligibility_for, explain_ticket
from fares.model import PriceType
from i18n import current_lang, label_or, t, tm
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
SELECTED_SLOT_KEY = "selected_slot"  # karta/lista, pod którą rozwinięto szczegóły
SLOT_LIST = "list"
SORT_OPTIONS = ("price", "time", "transfers")

# Podświetlenie wybranej karty: sama ramka kontenera z kluczem "card-selected-*" (poza tym wybraną
# kartę znaczy też plakietka "wybrana", więc kolor nie jest jedynym sygnałem).
_CARD_CSS = (
    "<style>[class*='st-key-card-selected-']{"
    "border:2px solid #1f77b4 !important;background:rgba(31,119,180,.07);}</style>"
)


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


def duration_text(minutes: float) -> str:
    """"8 h 30 min" zamiast "8.5 h" (zaokrąglone do pełnych minut)."""
    total = round(minutes)
    hours, mins = divmod(total, 60)
    if not hours:
        return f"{mins} min"
    return f"{hours} h {mins:02d} min" if mins else f"{hours} h"


def transfers_text(n: int, lang: str | None = None) -> str:
    """"bez przesiadek" / "1 przesiadka" / "2 przesiadki" / "5 przesiadek" (polska odmiana tylko
    w polskim; w pozostałych językach liczba pojedyncza i mnoga)."""
    if n <= 0:
        return t("plain.transfers_0", lang=lang)
    if n == 1:
        return t("plain.transfers_1", lang=lang)
    polish_few = (lang or current_lang()) == "pl" and 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return t("plain.transfers_few" if polish_few else "plain.transfers_many", lang=lang, n=n)


def unique_places(suggestions: list[dict]) -> list[dict]:
    """Kandydaci geokodera bez powtórzeń (ta sama nazwa i punkt po zaokrągleniu do ~10 m), w
    kolejności od geokodera."""
    seen, out = set(), []
    for s in suggestions:
        key = (s["name"].strip().casefold(), round(s["lat"], 4), round(s["lon"], 4))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


PLACE_STOP, PLACE_CITY, PLACE_ADDRESS, PLACE_UNKNOWN = "stop", "city", "address", "unknown"

# Kategorie PLACE (jeśli geokoder je poda), które są miejscowością, dworcem, przystankiem lub lotniskiem.
_SETTLEMENT_CATEGORIES = {
    "city", "town", "village", "hamlet", "suburb", "borough", "quarter", "neighbourhood",
    "municipality", "locality",
}  # fmt: skip
_TRANSPORT_CATEGORIES = {
    "station", "halt", "railway", "public_transport", "tram_stop", "bus_station", "bus_stop",
    "platform", "stop_position", "aerodrome", "airport",
}  # fmt: skip
_STATION_NAME = re.compile(
    r"\b(hbf|hauptbahnhof|bahnhof|bf|g[łl]ówny|glowny|centralny|dworzec|stacja|station|gare)\b",
    re.IGNORECASE,
)
_DOMAIN_LIKE = re.compile(r"\S\.(?:[a-z]{2,}\.)*[a-z]{2,}\b|https?:|www\.", re.IGNORECASE)


def _fold(text: str) -> str:
    """Nazwa do porównań: małe litery, bez polskich/niemieckich znaków diakrytycznych i interpunkcji."""
    text = text.casefold().replace("ł", "l").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def place_kind(suggestion: dict, query: str = "") -> str | None:
    """Rodzaj kandydata z geokodera wg jego typu miejsca: "stop" (dworzec/przystanek), "city"
    (miejscowość), "address", "unknown" (geokoder nie podał typu) albo None = nie nadaje się
    (np. firma/strona WWW z nazwą w OSM, rzeka, obiekt).

    PLACE jest miejscowością lub dworcem tylko wtedy, gdy jego kategoria na to wskazuje; bez
    kategorii uznajemy go za miejscowość, jeśli jego nazwa to dokładnie wpisany tekst ("Wroclaw" ->
    "Wrocław"), a "KLOCKI.wroclaw.pl" czy "Lublin suyu" odpadają."""
    kind = (suggestion.get("type") or "").upper()
    if not kind:
        return PLACE_UNKNOWN
    if kind == "STOP":
        return PLACE_STOP
    if kind == "ADDRESS":
        return PLACE_ADDRESS
    if kind != "PLACE":
        return None
    name = suggestion["name"].strip()
    if _DOMAIN_LIKE.search(name):
        return None
    category = (suggestion.get("category") or "").lower()
    if category in _TRANSPORT_CATEGORIES:
        return PLACE_STOP
    if category in _SETTLEMENT_CATEGORIES:
        return PLACE_CITY
    if not category and query and _fold(name) == _fold(query):
        return PLACE_CITY
    return None


def _is_station(suggestion: dict) -> bool:
    return place_kind(suggestion) == PLACE_STOP and bool(_STATION_NAME.search(suggestion["name"]))


def rank_places(suggestions: list[dict], query: str = "") -> list[dict]:
    """Odsiewa kandydatów, którzy nie są miejscowością, dworcem, przystankiem ani adresem, i wysuwa
    na górę dworce i miasta (potem zwykłe przystanki, adresy i kandydaci bez typu). Stabilnie:
    wewnątrz grupy zostaje kolejność od geokodera."""

    def group(s: dict) -> int:
        kind = place_kind(s, query)
        if kind == PLACE_CITY or _is_station(s):
            return 0
        return {PLACE_STOP: 1, PLACE_ADDRESS: 2, PLACE_UNKNOWN: 2}[kind]

    kept = [s for s in suggestions if place_kind(s, query) is not None]
    return sorted(kept, key=group)


def clear_place(options: list[dict], query: str) -> dict | None:
    """Kandydat, którego można wybrać bez pytania: pierwszy wynik jest miastem (albo dworcem) o nazwie
    równej wpisanemu tekstowi i żaden inny kandydat takiego rodzaju nie ma tej samej nazwy w innym
    punkcie (jak kilka miejscowości "Neustadt"). Inaczej None = pokaż wybór."""
    if not options:
        return None
    first = options[0]
    kind = place_kind(first, query)
    if kind != PLACE_CITY and not _is_station(first):
        return None
    name = _fold(first["name"])
    if name != _fold(query):
        return None
    rivals = [
        o
        for o in options[1:]
        if _fold(o["name"]) == name and (place_kind(o, query) == kind or _is_station(o))
    ]
    return None if rivals else first


def variant_index(built, it) -> int:
    return next(i for i, x in enumerate(built) if x is it)


def recommended_variant(built, recs):
    """Jedna polecana trasa: "najlepszy kompromis (bezpieczny)" z rekomendacji (kompromis ceny, czasu
    i przesiadek bez ryzykownych przesiadek, gdy takie są), a bez rekomendacji pierwszy wariant."""
    for key in ("najlepszy_kompromis_bezpieczny", "najlepszy_kompromis"):
        it = recs.get(key) if recs else None
        if it is not None and any(x is it for x in built):
            return it
    return built[0] if built else None


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


def select_variant(index: int, slot: str = SLOT_LIST, toggle: bool = True) -> None:
    """Wybiera wariant i miejsce (karta/lista), pod którym rozwija się jego szczegóły. Ponowne
    kliknięcie tej samej karty zwija szczegóły (toggle)."""
    state = st.session_state
    if toggle and state.get(SELECTED_KEY) == index and state.get(SELECTED_SLOT_KEY) == slot:
        state.pop(SELECTED_KEY, None)
        state.pop(SELECTED_SLOT_KEY, None)
        return
    state[SELECTED_KEY] = index
    state[SELECTED_SLOT_KEY] = slot


def _active_slot(cards: list[tuple[str, int]]) -> str | None:
    """Slot ze szczegółami: zapisany, jeśli pasuje do wybranego wariantu; w przeciwnym razie
    pierwsza karta z tym wariantem (np. gdy wybór ustawiono bez slotu)."""
    selected = st.session_state.get(SELECTED_KEY)
    if selected is None:
        return None
    slot = st.session_state.get(SELECTED_SLOT_KEY)
    if slot == SLOT_LIST or any(s == slot and i == selected for s, i in cards):
        return slot
    return next((s for s, i in cards if i == selected), None)


def _variant_card(built, it, title: str, slot: str, active: str | None, render_details,
                  tag: str | None = None, note: str | None = None) -> None:
    """Karta wariantu; gdy to aktywny slot, szczegóły rozwijają się TUŻ POD kartą."""
    selected = active == slot
    with st.container(border=True, key=f"card-selected-{slot}" if selected else f"card-{slot}"):
        st.markdown(f"**{title}**" + (f"  :blue-badge[{t('cards.selected')}]" if selected else ""))
        if note:
            st.caption(note)
        if tag:
            st.badge(tag, color="orange", help=t("cards.estimate_help"))
        st.subheader(route_summary(it))
        st.caption(f"{tm(it.variant_name)} • {carriers_summary(it)}")
        st.markdown(f"🕒 {time_span(it)}")
        st.caption(f"{duration_text(it.total_duration_min)} • {transfers_text(it.num_transfers)}")
        st.markdown(f"**{variant_price_text(it)}**")
        status = itinerary_price_status(it)
        st.badge(
            status_label(status),
            color=_STATUS_BADGE_COLOR[status],
            help=t(f"badge.explain_{_STATUS_KEY[status]}"),
        )
        if it.is_risky:
            st.caption(t("cards.risky"))
        st.button(
            t("cards.hide") if selected else t("cards.details"),
            key=f"show_{slot}",
            on_click=select_variant,
            args=(variant_index(built, it), slot),
        )
    if selected:
        render_selected_details(it, render_details)


def render_selected_details(it, render_details) -> None:
    with st.container(border=True):
        st.subheader(t("details.title", name=tm(it.variant_name)))
        render_details(it)


def render_variant_cards(built, recs, render_details) -> None:
    """Na górze wyników trzy karty jedna pod drugą: polecana trasa, najtańsza potwierdzona i
    najtańsza wg szacunku (ta ostatnia tylko, gdy to inny wariant niż potwierdzona). "Pokaż
    szczegóły" wybiera wariant (SELECTED_KEY) i rozwija szczegóły pod daną kartą; sam wynik
    wyszukiwania zostaje w session_state."""
    st.html(_CARD_CSS)
    recommended = recommended_variant(built, recs)
    confirmed, estimate = cheapest_variant_cards(built)
    cards = []
    if recommended is not None:
        cards.append(("recommended", recommended))
    if confirmed is not None:
        cards.append(("confirmed", confirmed))
    if estimate is not None:
        cards.append(("estimate", estimate))
    active = _active_slot([(slot, variant_index(built, it)) for slot, it in cards])
    if recommended is not None:
        _variant_card(
            built, recommended, t("cards.recommended"), "recommended", active, render_details,
            note=t("cards.recommended_why"),
        )
    if confirmed is None and estimate is None:
        st.info(t("cards.none"))
        return
    if confirmed is None:
        st.info(t("cards.no_confirmed"))
    else:
        _variant_card(built, confirmed, t("cards.confirmed"), "confirmed", active, render_details)
    if estimate is not None:
        _variant_card(
            built, estimate, t("cards.estimate"), "estimate", active, render_details,
            tag=t("cards.estimate_tag"),
        )


def _variant_row(it) -> dict:
    status = itinerary_price_status(it)
    return {
        t("list.col.variant"): ("⚠️ " if it.is_risky else "") + tm(it.variant_name),
        t("col.route"): route_summary(it),
        t("metric.time"): duration_text(it.total_duration_min),
        t("metric.transfers"): it.num_transfers,
        t("list.col.price"): variant_price_text(it),
        t("col.price_status"): status_cell(status),
    }


def _on_row_select(table_key: str, order: list[int]) -> None:
    rows = st.session_state[table_key].selection.rows
    if rows:
        select_variant(order[rows[0]], SLOT_LIST, toggle=False)


def render_variant_list(built, render_details) -> None:
    """Pełna lista wszystkich wariantów (potwierdzone, szacunki, loty) z sortowaniem i filtrem
    "tylko potwierdzone". Zaznaczenie wiersza wybiera wariant; jego szczegóły rozwijają się pod
    tabelą (o ile nie otwarto ich pod którąś z kart na górze)."""
    st.subheader(t("res.all_variants"))
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
    selected = st.session_state.get(SELECTED_KEY)
    if (
        selected is not None
        and selected < len(built)
        and st.session_state.get(SELECTED_SLOT_KEY) == SLOT_LIST
    ):
        render_selected_details(built[selected], render_details)
