"""Teksty generowane przez kod (nie przez UI): nazwy wariantów, powody pominięcia, komunikaty
przesiadek, ostrzeżenia dla cudzoziemców, notki rankingu i etykieta innego dnia. Polski jest
źródłem (`Msg` jest też zwykłym `str` po polsku), pozostałe 5 języków renderuje się z kluczy
w i18n/. Testy nie dotykają cen ani logiki taryf."""

import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import i18n
from fares.foreigner_eligibility import warnings_for
from fares.model import DiscountProfile
from i18n import LANGUAGES, TRANSLATIONS, Joined, Msg, exc_text, t, tm, transport_mode_name
from routing import airports, motis_client, search_service, variants
from routing.model import Itinerary, Leg, LegMode, OtherDayVariant, PricedLeg, SkippedVariant
from routing.scoring import build_itinerary, pick_recommendations, price_ranking_note
from routing.transfers import check_transfer
from tests.test_price_status_ui import open_details

ROOT = Path(__file__).resolve().parent.parent
PL = TRANSLATIONS["pl"]
OTHER_LANGS = [lang for lang in LANGUAGES if lang != "pl"]
# MOTIS (OpenAPI `Mode`): każdy tryb transportu publicznego, który może trafić do nazwy wariantu
MOTIS_TRANSIT_MODES = [
    "RAIL", "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL", "REGIONAL_RAIL",
    "SUBURBAN", "SUBWAY", "METRO", "TRAM", "BUS", "COACH", "FERRY", "AIRPLANE", "CABLE_CAR",
    "FUNICULAR", "AERIAL_LIFT", "AREAL_LIFT", "TRANSIT", "ODM", "FLEX", "TRAIN", "OTHER",
]  # fmt: skip
# Klucze, których tłumaczenie bywa identyczne z polskim (nazwa własna / zapożyczenie).
SAME_AS_PL_OK = {"tmode.metro", "tmode.subway", "tmode.funicular", "tmode.flex", "variant.airports"}


# --- klucze używane w kodzie istnieją w słownikach -----------------------------------------------


def test_klucze_msg_uzyte_w_kodzie_istnieja_we_wszystkich_jezykach():
    pattern = re.compile(r'Msg\(\s*f?"([a-z_]+\.[a-z_{}.\'"() ]*)"')
    used: set[str] = set()
    for path in [p for d in ("routing", "fares", "flights") for p in (ROOT / d).glob("*.py")]:
        used |= {k for k in pattern.findall(path.read_text(encoding="utf-8")) if "{" not in k}
    assert {"variant.rail_only", "skip.infeasible", "transfer.reason", "foreign.germany"} <= used
    for lang, table in TRANSLATIONS.items():
        assert used - set(table) == set(), f"{lang}: brak kluczy {sorted(used - set(table))}"


def test_klucze_dynamiczne_pokryte():
    for mode in MOTIS_TRANSIT_MODES:
        assert f"tmode.{mode.lower()}" in PL, mode
    for leg_mode in LegMode:
        assert f"mode.{leg_mode.value}" in PL
    for n in ("one", "many"):
        for when in ("later", "earlier"):
            assert f"other_day.{when}_{n}" in PL


@pytest.mark.parametrize("lang", OTHER_LANGS)
def test_nowe_klucze_sa_przetlumaczone_a_nie_skopiowane_z_polskiego(lang):
    new = [
        k
        for k in PL
        if k.split(".")[0] in {"tmode", "variant", "skip", "err", "foreign", "rank", "ptype"}
    ]
    new += [
        "transfer.reason",
        "transfer.why_same_stop",
        "transfer.why_walk",
        "transfer.why_same_platform",
    ]
    new += [
        k
        for k in PL
        if k.startswith("other_day.")
        and k not in {"other_day.title", "other_day.warning", "other_day.expander"}
    ]
    assert len(new) > 60
    same = [k for k in new if TRANSLATIONS[lang][k] == PL[k] and k not in SAME_AS_PL_OK]
    assert same == [], f"{lang}: nieprzetłumaczone {same}"


# --- Msg: polski tekst + render w języku ----------------------------------------------------------


def test_msg_jest_str_po_polsku_i_renderuje_sie_w_innych_jezykach():
    m = Msg("variant.via", via="Poznań Główny")
    assert isinstance(m, str) and m == "Kolej przez Poznań Główny"
    assert tm(m, "en") == "Rail via Poznań Główny"
    assert tm(m, "de") == "Bahn über Poznań Główny"
    assert tm("zwykły tekst", "de") == "zwykły tekst"  # str bez klucza przechodzi bez zmian


def test_msg_zagniezdzone_i_listy_oraz_kopiowanie():
    import copy
    import pickle

    inner = Msg("skip.no_airport_pairs")
    outer = Msg("skip.skipped", reason=inner)
    assert outer == "Pominięty: brak par lotnisk w promieniu bez objazdu (tabela lotnisk PL+DE)"
    assert tm(outer, "nl").startswith("Overgeslagen: geen luchthavenparen")
    joined = Msg("skip.flights_unconfirmed", reason="x", pairs=Joined(["A→B", "C→D"]))
    assert joined == "x. Pary: A→B, C→D"
    for clone in (copy.deepcopy(outer), pickle.loads(pickle.dumps(outer))):
        assert isinstance(clone, Msg) and tm(clone, "fr") == tm(outer, "fr")


def test_exc_text_zachowuje_msg_a_zwykly_wyjatek_daje_str():
    err = motis_client.MotisError(Msg("skip.no_access", stop="X", date="2026-10-20"))
    assert (
        isinstance(exc_text(err), Msg)
        and tm(exc_text(err), "en") == "No way to get to X on 2026-10-20."
    )
    assert str(err) == "Brak dojazdu do X w dniu 2026-10-20."
    assert exc_text(motis_client.MotisError("surowy")) == "surowy"


# --- nazwy wariantów: rodzaje transportu zamiast surowych kluczy ---------------------------------


def _leg(mode="REGIONAL_RAIL", a="Kraków", b="Katowice", h1=6, h2=8, requires_walk=False):
    return Leg(
        mode=LegMode.RAIL,
        origin_name=a,
        destination_name=b,
        depart=datetime(2026, 10, 18, h1, 0, tzinfo=UTC),
        arrive=datetime(2026, 10, 18, h2, 0, tzinfo=UTC),
        carrier_name="POLREGIO",
        distance_km=100.0,
        requires_walk=requires_walk,
        extra={"motis_mode": mode},
    )


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_nazwa_wariantu_kolejowego_nie_ma_surowych_kluczy(lang):
    name = variants._rail_only_name([_leg("REGIONAL_RAIL"), _leg("HIGHSPEED_RAIL", h1=9, h2=11)])
    text = tm(name, lang)
    assert "regional_rail" not in text.lower() and "highspeed" not in text.lower()
    assert "_" not in text
    assert tm(transport_mode_name("REGIONAL_RAIL"), lang) in text
    assert tm(transport_mode_name("HIGHSPEED_RAIL"), lang) in text
    assert ", " in text and "1" in text  # liczba przesiadek


def test_nazwa_wariantu_po_polsku_to_nazwy_rodzajow_transportu():
    name = variants._rail_only_name([_leg("REGIONAL_RAIL"), _leg("SUBURBAN", h1=9, h2=10)])
    assert name == "Tylko kolej (kolej regionalna/kolej miejska, przesiadek: 1)"


def test_nieznany_tryb_transportu_nie_pokazuje_surowego_klucza():
    assert transport_mode_name("SOME_NEW_MODE") == "some new mode"


def test_wariant_zbudowany_z_motis_dostaje_przetlumaczalna_nazwe(monkeypatch):
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **k: [[_leg()]]
    )
    monkeypatch.setattr(
        variants,
        "_price_legs",
        lambda legs, request: [PricedLeg(l, 10.0, "PLN", "szacunek") for l in legs],
    )
    request = variants.RouteRequest("50,19", "50,20", "A", "B", "2026-10-18")
    (it,) = variants.build_rail_only_variants(request)
    assert it.variant_name == "Tylko kolej (kolej regionalna, przesiadek: 0)"
    assert tm(it.variant_name, "es") == "Solo tren (tren regional, transbordos: 0)"


def test_pozostale_nazwy_wariantow_maja_klucze():
    hub = variants.HubConfig("WAW-DUS", "WAW", "DUS", "50,20", "51,7")
    assert (
        tm(Msg("variant.rail_flight_rail", hub=hub.label), "de")
        == "Bahn + Flug (WAW-DUS) + Nahverkehr"
    )
    assert (
        tm(Msg("variant.flight_regional", hub=hub.label), "fr")
        == "Vol (WAW-DUS) + transport régional"
    )
    assert tm(Msg("variant.walk"), "nl") == "Te voet"
    assert Msg("variant.rail_start", stop="Essen") == "Tylko kolej (start: Essen)"


# --- „Pominięte opcje”: powody pominięcia ---------------------------------------------------------


def test_powody_pominiecia_w_generate_variants_sa_msg_i_renderuja_sie_w_kazdym_jezyku(monkeypatch):
    request = variants.RouteRequest("51.2314,22.5692", "51.5049,7.1022", "A", "B", "2026-10-20")
    pairs_status = lambda a, b, d: (False, Msg("skip.no_direct_ticket"))
    discover = lambda o, d, skip: airports.discover_hubs(o, d, request.date, skip)
    boom = motis_client.MotisError(
        Msg("skip.no_connections_at_all", time="06:00:00", date=request.date)
    )
    with (
        patch("routing.variants.build_rail_only_variants", side_effect=boom),
        patch.object(airports, "direct_flight_status", pairs_status),
    ):
        _, skipped = variants.generate_variants(request, hub_discovery=discover)

    assert len(skipped) >= 2
    assert all(isinstance(s.variant_name, Msg) for s in skipped)
    assert all(isinstance(s.reason, Msg) for s in skipped)
    by_key = {s.variant_name.key: s for s in skipped}
    assert {"variant.rail_only_plain", "variant.unconfirmed_flights"} <= set(by_key)
    flights = by_key["variant.unconfirmed_flights"]
    assert flights.variant_name.startswith("Loty bez potwierdzenia (")
    assert (
        "brak biletu bezpośredniego w cache Travelpayouts" in flights.reason
        and "Pary: " in flights.reason
    )
    for lang in OTHER_LANGS:
        for s in skipped:
            rendered = tm(s.variant_name, lang) + " " + tm(s.reason, lang)
            assert rendered != s.variant_name + " " + s.reason, (lang, s.variant_name)
            assert "Pary:" not in rendered and "Loty bez potwierdzenia" not in rendered, lang
        assert "Travelpayouts" in tm(flights.reason, lang)
        assert "WAW→" in tm(flights.reason, lang) or "WMI→" in tm(flights.reason, lang)


def test_objazdy_hubow_i_stacji_maja_klucze():
    reason = variants.via_hub_detour_reason((50.06, 19.94), (52.4, 16.9), (49.66, 21.16))
    assert isinstance(reason, Msg) and reason.key == "skip.via_detour"
    assert reason.startswith("Pominięty: objazd — trasa przez ten węzeł to ok. ")
    assert "linii prostej" not in tm(reason, "en") and "as the crow flies" in tm(reason, "en")
    assert "Luftlinie" in tm(reason, "de")

    legs = [_leg(a="A", b="B"), _leg(a="B", b="C", h1=9, h2=10), _leg(a="C", b="B", h1=11, h2=12)]
    again = variants.revisited_station_reason(legs)
    assert isinstance(again, Msg) and again.key == "skip.revisited"
    assert again == "Pominięty: objazd — trasa wraca przez B (ta sama stacja dwa razy)."
    assert tm(again, "es").endswith("(la misma estación dos veces).")


def test_hub_to_objazd_i_brak_wspolrzednych_to_msg():
    request = variants.RouteRequest("51.2314,22.5692", "52.5251,13.3694", "A", "B", "2026-10-20")
    hub = variants.HubConfig("WAW-DUS", "WAW", "DUS", "52.17,20.96", "51.28,6.76")
    with patch("routing.variants.build_rail_only_variants", return_value=[]):
        _, skipped = variants.generate_variants(
            request, rail_flight_rail_hubs=[hub], hub_discovery=lambda *a: ([], [])
        )
    detour = [s for s in skipped if s.reason.key == "skip.hub_detour"]
    assert detour and detour[0].reason == "Pominięty: hub to objazd względem trasy."
    assert tm(detour[0].reason, "nl").startswith("Overgeslagen: het knooppunt")
    assert tm(detour[0].variant_name, "en") == "Rail + flight (WAW-DUS) + local rail"

    with patch("routing.variants.build_rail_only_variants", return_value=[]):
        _, skipped = variants.generate_variants(
            variants.RouteRequest("abc", "def", "A", "B", "2026-10-20"),
            hub_discovery=lambda *a: ([], []),
        )
    no_coords = next(s for s in skipped if s.variant_name.key == "variant.airport_selection")
    assert no_coords.reason.key == "skip.no_coordinates"
    assert tm(no_coords.variant_name, "de") == "Flüge (Flughafenauswahl)"


def test_brak_polaczen_i_niewykonalna_przesiadka_maja_klucze():
    request = variants.RouteRequest("a", "b", "A", "B", "2026-10-20", departure_time="06:00:00")
    none_at_all = variants._no_rail_reason(request, 0, 0, 0)
    assert none_at_all.startswith("MOTIS nie zwrócił żadnego połączenia (od 06:00:00, 2026-10-20)")
    assert "GTFS" in tm(none_at_all, "en") and "aucune liaison" in tm(none_at_all, "fr")
    mixed = variants._no_rail_reason(request, 5, 3, 2)
    assert mixed == (
        "MOTIS zwrócił 5 połączeń, ale żadne nie nadaje się do wyniku: "
        "3 połączeń rusza w innym dniu niż 2026-10-20, 2 odrzucono (przesiadka poniżej minimum)."
    )
    assert tm(mixed, "en") == (
        "MOTIS returned 5 connections, but none is usable for the result: "
        "3 connections depart on a day other than 2026-10-20, 2 rejected (transfer below the minimum)."
    )

    tight = build_itinerary(
        "x",
        [
            PricedLeg(_leg(), 1.0, "PLN", "szacunek"),
            PricedLeg(_leg(a="Katowice", b="Berlin", h1=8, h2=9), 1.0, "PLN", "szacunek"),
        ],
    )
    assert tight.is_infeasible
    infeasible = variants._infeasible_reason(tight)
    assert infeasible.startswith(
        "Odrzucony: przesiadka niewykonalna fizycznie. Tylko 0 min na przesiadkę"
    )
    assert tm(infeasible, "en").startswith(
        "Rejected: the transfer is physically impossible. Only 0 min"
    )


def test_bledy_motis_i_travelpayouts_to_msg(monkeypatch):
    from flights import travelpayouts

    monkeypatch.delenv(travelpayouts.TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(travelpayouts, "load_dotenv", lambda *a, **k: None, raising=False)
    with pytest.raises(travelpayouts.TravelpayoutsError) as info:
        travelpayouts._get_token()
    err = exc_text(info.value)
    assert isinstance(err, Msg) and err.startswith(
        "Brak tokena API Travelpayouts w zmiennej środowiskowej"
    )
    assert "Missing Travelpayouts API token" in tm(err, "en")
    assert "Das Token" not in tm(err, "de") and "Token" in tm(err, "de")


def test_direct_flight_status_zwraca_msg(monkeypatch):
    from flights import travelpayouts

    monkeypatch.setattr(travelpayouts, "fetch_direct_tickets", lambda *a, **k: [])
    ok, reason = airports.direct_flight_status("WAW", "DUS", "2026-10-20")
    assert ok is False and isinstance(reason, Msg) and reason.key == "skip.no_direct_ticket"
    monkeypatch.setattr(
        travelpayouts,
        "fetch_direct_tickets",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sieć")),
    )
    ok, reason = airports.direct_flight_status("WAW", "DUS", "2026-10-20")
    assert (
        reason == "błąd Travelpayouts: sieć" and tm(reason, "es") == "error de Travelpayouts: sieć"
    )


# --- komunikaty przesiadek ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "walk,same,why_key",
    [
        (False, False, "transfer.why_same_platform"),
        (True, False, "transfer.why_walk"),
        (True, True, "transfer.why_same_stop"),
    ],
)
def test_powod_ryzykownej_przesiadki_jest_msg(walk, same, why_key):
    prev = _leg(a="Kraków", b="Katowice", h1=6, h2=8)
    nxt = _leg(
        a="Katowice" if same else "Katowice Zachodnie", b="Berlin", h1=8, h2=14, requires_walk=walk
    )
    nxt.depart = nxt.depart.replace(minute=12)  # 12 min przerwy: ciasno, ale wykonalnie
    warning = check_transfer(prev, nxt, 0)
    assert warning is not None and not warning.infeasible
    reason = warning.reason
    assert isinstance(reason, Msg) and reason.params["why"].key == why_key
    assert reason.startswith("Tylko 12 min na przesiadkę kolej -> kolej (")
    assert reason.endswith(f"potrzeba minimum {warning.minimum_required_minutes:.0f} min.")
    assert tm(reason, "en").startswith("Only 12 min for the rail -> rail transfer (")
    assert tm(reason, "de").startswith("Nur 12 Min. für den Umstieg Bahn -> Bahn (")


def test_przesiadka_lot_kolej_tlumaczy_rodzaje_odcinkow():
    flight = Leg(
        LegMode.FLIGHT,
        "WAW",
        "DUS",
        datetime(2026, 10, 18, 6, tzinfo=UTC),
        datetime(2026, 10, 18, 8, tzinfo=UTC),
    )
    rail = _leg(a="Düsseldorf", b="Essen", h1=8, h2=9)
    rail.depart = rail.depart.replace(minute=50)
    warning = check_transfer(flight, rail, 0)
    assert warning and "lot -> kolej" in warning.reason
    assert "flight -> rail" in tm(warning.reason, "en")


# --- ostrzeżenia dla cudzoziemców -----------------------------------------------------------------


def _all_foreigner_warnings():
    profile = DiscountProfile(
        obywatelstwo="UE",
        legitymacja_zagraniczna=True,
        pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat",
        ztm_warszawa_ulgowy=True,
        mpk_krakow_ulgowy=True,
        ztm_poznan_ulgowy=True,
        ztm_lublin_ulgowy=True,
        mpk_wroclaw_ulgowy=True,
        bvg_berlin_ulgowy=True,
    )
    out = warnings_for(profile)
    out += warnings_for(
        DiscountProfile(
            obywatelstwo="poza_UE", pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"
        )
    )
    return out


def test_ostrzezenia_dla_cudzoziemcow_pokrywaja_wszystkie_klucze_foreign():
    msgs = _all_foreigner_warnings()
    assert all(isinstance(m, Msg) for m in msgs)
    assert {m.key for m in msgs} == {k for k in PL if k.startswith("foreign.")}
    assert any("karty pobytu" in m for m in msgs) and any(
        "spoza UE" in m for m in msgs
    )  # polski bez zmian


@pytest.mark.parametrize("lang", OTHER_LANGS)
def test_ostrzezenia_dla_cudzoziemcow_w_jezyku(lang):
    for m in _all_foreigner_warnings():
        text = tm(m, lang)
        assert text != str(m), (lang, m.key)
        assert not re.search(r"obywatel|legitymacj|ulga|zniżk|przyzna", text.lower()), (lang, m.key)
        assert "ISIC" in text or m.key not in {"foreign.krakow", "foreign.lublin"}


# --- notki rankingu i „inny dzień” ----------------------------------------------------------------


def _priced(amount, verified=True):
    leg = _leg()
    return PricedLeg(
        leg, amount, "PLN", "szacunek", breakdown={"price_verified": verified}
    )


def test_notki_rankingu_cen_to_msg_po_polsku_bez_zmian():
    a = build_itinerary(Msg("variant.via", via="Poznań"), [_priced(30.0, verified=False)])
    b = build_itinerary("B", [_priced(10.0, verified=False)])
    note = price_ranking_note("najtansza", b, [a, b])
    assert isinstance(note, Msg) and note.key == "rank.unverified_only"
    assert note.startswith("Żaden wariant w tej kategorii nie ma w pełni potwierdzonej ceny")

    ok = build_itinerary("OK", [_priced(40.0)])
    cheap = build_itinerary(Msg("variant.via", via="Poznań"), [_priced(20.0, verified=False)])
    note = price_ranking_note("najtansza", ok, [cheap, ok])
    assert note.key == "rank.skipped_cheaper"
    assert (
        "Pominięto 1 wariant(y) nominalnie tańsze" in note
        and "Kolej przez Poznań: 20.00 PLN" in note
    )
    # nazwa wariantu w notce też jest tłumaczona
    assert "Rail via Poznań: 20.00 PLN" in tm(note, "en")
    assert price_ranking_note("najszybsza", ok, [cheap, ok]) is None


@pytest.mark.parametrize(
    "offset,lang,expected",
    [
        (2, "pl", "za 2 dni"),
        (1, "pl", "za 1 dzień"),
        (-1, "pl", "1 dzień wcześniej"),
        (-3, "pl", "3 dni wcześniej"),
        (2, "en", "in 2 days"),
        (-1, "en", "1 day earlier"),
        (3, "de", "in 3 Tagen"),
        (1, "es", "en 1 día"),
        (-2, "fr", "2 jours plus tôt"),
        (1, "nl", "over 1 dag"),
    ],
)
def test_etykieta_innego_dnia_w_jezykach(offset, lang, expected):
    v = OtherDayVariant(Itinerary("x", [], 1.0, 1.0, 0), "2026-10-19", "2026-10-17", offset)
    assert expected in tm(v.label, lang)
    assert "2026-10-19" in tm(v.label, lang) and "2026-10-17" in tm(v.label, lang)
    if lang == "pl":
        assert (
            v.label
            == f"INNY DZIEŃ: 2026-10-19 ({expected}, zapytano o 2026-10-17) — to NIE jest dzień zapytania"
        )


# --- cała aplikacja: sekcje generowane przez kod w każdym języku ----------------------------------


def _risky_itinerary() -> Itinerary:
    legs = [
        PricedLeg(
            _leg("REGIONAL_RAIL", "Kraków", "Katowice", 6, 8), 40.0, "PLN", "oficjalna_taryfa"
        ),
        PricedLeg(
            _leg("SUBURBAN", "Katowice Zachodnie", "Gliwice", 8, 9, requires_walk=True),
            20.0,
            "PLN",
            "szacunek",
            breakdown={"price_verified": False, "cena_nieznana": True},
        ),
    ]
    legs[0].leg.arrive = legs[0].leg.arrive.replace(
        hour=7, minute=48
    )  # 12 min przerwy: ryzykownie, ale wykonalnie
    it = build_itinerary(variants._rail_only_name([pl.leg for pl in legs]), legs)
    assert it.is_risky and not it.is_infeasible
    return it


@pytest.fixture
def mocked_search(monkeypatch):
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text}],
    )
    monkeypatch.setattr(motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")

    def fake_search(request):
        it = _risky_itinerary()
        skipped = [
            SkippedVariant(
                Msg("variant.via", via="Poznań Główny"),
                variants.via_hub_detour_reason((50.06, 19.94), (52.4, 16.9), (49.66, 21.16)),
            ),
            SkippedVariant(
                Msg("variant.unconfirmed_flights", n=2),
                Msg(
                    "skip.flights_unconfirmed",
                    reason=Msg("skip.no_direct_ticket"),
                    pairs=Joined(["WAW→DUS", "WMI→DUS"]),
                ),
            ),
            SkippedVariant(
                Msg("variant.rail_only_plain"),
                Msg(
                    "skip.infeasible",
                    reasons=Joined(
                        [
                            Msg(
                                "transfer.reason",
                                gap="3",
                                prev=Msg("mode.kolej"),
                                next=Msg("mode.lot"),
                                why=Msg("transfer.why_walk"),
                                origin="A",
                                destination="B",
                                minimum="120",
                            )
                        ],
                        "; ",
                    ),
                ),
            ),
        ]
        other_day = [OtherDayVariant(it, "2026-10-19", request.date, 2)]
        return search_service.SearchResult(
            request=request,
            built=[it],
            skipped=skipped,
            recommendations=pick_recommendations([it]),
            other_day=other_day,
        )

    monkeypatch.setattr(search_service, "search", fake_search)
    monkeypatch.setattr(
        "fares.foreigner_eligibility.warnings_for",
        lambda profile: [Msg("foreign.warsaw"), Msg("foreign.germany")],
    )


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_aplikacja_pokazuje_pominiete_przesiadki_i_ostrzezenia_w_jezyku(
    mocked_search, monkeypatch, lang
):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    open_details(at)

    # ostrzeżenia dla cudzoziemców (st.warning) i ryzykowna przesiadka
    warnings = [w.value for w in at.warning]
    assert (
        tm(Msg("foreign.warsaw"), lang) in warnings and tm(Msg("foreign.germany"), lang) in warnings
    )
    risky = t("transfer.risky", lang=lang, reason="")
    assert any(w.startswith(risky.rstrip()) and "12" in w for w in warnings)
    if lang != "pl":
        assert not any(re.search(r"przesiadk|Tylko \d+ min", w) for w in warnings)

    # sekcja pominiętych: nazwy i powody w wybranym języku
    # (widoczna sekcja z nagłówkiem, nie zwinięty expander)
    assert t("res.skipped", lang=lang) in [h.value for h in at.subheader]
    assert t("res.skipped", lang=lang) not in [e.label for e in at.expander]
    text = " ".join(m.value for m in at.markdown if m.value.startswith("- **"))
    assert tm(Msg("variant.via", via="Poznań Główny"), lang) in text
    assert tm(Msg("variant.unconfirmed_flights", n=2), lang) in text
    assert "WAW→DUS, WMI→DUS" in text
    if lang != "pl":
        assert not re.search(r"Pominięt|Odrzucon|Pary:|Loty bez|objazd|przesiadk", text)

    # nazwy wariantów: rodzaje transportu, nigdy surowe klucze MOTIS
    subheaders = [s.value for s in at.subheader]
    labels = subheaders + [e.label for e in at.expander]
    joined = " ".join(labels)
    assert not re.search(r"regional_rail|highspeed_rail|suburban_|_rail", joined.lower())
    assert tm(transport_mode_name("REGIONAL_RAIL"), lang) in joined

    # tabela: typ ceny przetłumaczony, odcinek bez ceny opisany po ludzku
    rows = at.dataframe[1].value  # [0] to lista wariantów
    prices = list(rows[t("col.price", lang=lang)])
    # status ceny jest tylko w kolumnie "Status ceny", nie w nawiasie przy kwocie
    assert "(" not in prices[0].split(" — ")[0]
    assert t("ptype.oficjalna_taryfa", lang=lang) not in prices[0]
    assert t("price.unknown_leg", lang=lang) in prices[1]


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_blad_motis_w_ui_jest_w_jezyku_uzytkownika(monkeypatch, lang):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    monkeypatch.setattr(
        motis_client,
        "geocode_suggestions",
        lambda text, limit=5: [{"lat": 50.0, "lon": 19.9, "name": text}],
    )
    monkeypatch.setattr(motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")

    def boom(request):
        raise motis_client.MotisError(Msg("err.motis_rejected", detail="x"))

    monkeypatch.setattr(search_service, "search", boom)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["lang"] = lang
    at.run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert [e.value for e in at.error] == [
        t("err.motis", lang=lang, exc=t("err.motis_rejected", lang=lang, detail="x"))
    ]
