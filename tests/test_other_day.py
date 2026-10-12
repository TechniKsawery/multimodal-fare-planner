"""Sekcja "Najbliższe połączenia w innym dniu": gdy MOTIS zwraca połączenia, ale wszystkie w innym
dniu niż zapytany (np. Kraków -> Gorlice w sobotę 17.10, pociągi dopiero w poniedziałek), wynik
pokazuje je osobno, z datą i etykietą "to NIE jest dzień zapytania" — poza `built` i rankingami.

Fixtury: puste na dzień D (2026-10-17, sobota), połączenia na D+2 (poniedziałek 19.10). MOTIS jest
mockowany na poziomie routing.variants.motis_client, jak w tests/test_api.py (bez sieci)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import demo
from api.main import app
from routing import search_service, variants
from routing.model import OTHER_DAY_SECTION_TITLE, Leg, LegMode
from routing.motis_client import MotisError
from routing.scoring import pick_recommendations

D = "2026-10-17"  # sobota, dzień zapytania
client = TestClient(app)


def _rail(day, hour=6, minute=0, price_km=100.0, carrier="PKP Intercity"):
    """Jeden odcinek kolejowy Kraków Główny -> Gorlice; godziny w UTC (lokalnie +2 h, ten sam dzień)."""
    return Leg(
        mode=LegMode.RAIL,
        origin_name="Kraków Główny",
        destination_name="Gorlice",
        depart=datetime(2026, 10, day, hour, minute, tzinfo=UTC),
        arrive=datetime(2026, 10, day, hour + 2, minute, tzinfo=UTC),
        carrier_name=carrier,
        distance_km=price_km,
        requires_walk=False,
    )


def _request(date=D):
    return variants.RouteRequest(
        origin_stop_id="50.0647,19.9450",
        destination_stop_id="49.6553,21.1597",
        origin_label="Kraków Główny",
        destination_label="Gorlice",
        date=date,
    )


def _mock_motis(monkeypatch, options):
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **k: [list(o) for o in options]
    )
    boom = lambda *a, **k: (_ for _ in ()).throw(MotisError("brak połączenia (mock)"))
    monkeypatch.setattr(variants.motis_client, "plan_leg", boom)
    monkeypatch.setattr(variants.motis_client, "plan_leg_candidates", boom)


# --- build_rail_only_variants -------------------------------------------------------------


def test_puste_na_dzien_d_polaczenia_d_plus_2_trafiaja_do_other_day_out(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(19, 6)]])
    other_day: list = []

    with pytest.raises(MotisError, match="innym dniu"):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)

    assert len(other_day) == 1
    v = other_day[0]
    assert v.date == "2026-10-19"
    assert v.requested_date == D
    assert v.days_offset == 2
    assert "2026-10-19" in v.label and "NIE jest dzień zapytania" in v.label
    assert "za 2 dni" in v.label


def test_cena_innego_dnia_liczona_tak_samo_jak_zwykle(monkeypatch):
    """Ten sam odcinek zapytany wprost na jego dzień (D+2) daje identyczną cenę i czas."""
    legs = [_rail(19, 6)]
    _mock_motis(monkeypatch, [legs])
    other_day: list = []
    with pytest.raises(MotisError):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)

    reference = variants.build_rail_only_variants(_request("2026-10-19"))[0]
    got = other_day[0].itinerary
    assert got.total_price_pln == reference.total_price_pln
    assert got.total_price_pln_high == reference.total_price_pln_high
    assert got.total_duration_min == reference.total_duration_min
    assert got.variant_name == reference.variant_name


def test_limit_trzech_wariantow_i_trzech_dni(monkeypatch):
    options = [
        [_rail(18, 6)],  # D+1
        [_rail(18, 9)],  # D+1
        [_rail(19, 6)],  # D+2
        [_rail(19, 9)],  # D+2 — czwarty z dozwolonego okna, ucięty limitem 3
        [_rail(20, 6)],  # D+3
        [_rail(22, 6)],  # D+5 — poza oknem 3 dni
    ]
    _mock_motis(monkeypatch, options)
    other_day: list = []
    with pytest.raises(MotisError):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)

    assert variants.OTHER_DAY_MAX_VARIANTS == 3 and variants.OTHER_DAY_MAX_DAYS == 3
    assert len(other_day) == 3
    # najbliższe wg odjazdu, rosnąco
    assert [v.itinerary.legs[0].leg.depart.day for v in other_day] == [18, 18, 19]
    assert all(1 <= v.days_offset <= 3 for v in other_day)


def test_polaczenia_dalej_niz_3_dni_nie_tworza_sekcji(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(21, 6)], [_rail(22, 6)]])  # D+4, D+5
    other_day: list = []
    with pytest.raises(MotisError, match="innym dniu"):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)
    assert other_day == []


def test_granica_trzech_dni_wlacznie(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(20, 6)], [_rail(21, 6)]])  # D+3 tak, D+4 nie
    other_day: list = []
    with pytest.raises(MotisError):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)
    assert [v.days_offset for v in other_day] == [3]


def test_jest_polaczenie_w_dniu_zapytania_other_day_out_zostaje_pusty(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(17, 6)], [_rail(19, 6)]])
    other_day: list = []
    result = variants.build_rail_only_variants(_request(), other_day_out=other_day)
    assert len(result) == 1
    assert other_day == []  # sekcja tylko przy "wszystkie połączenia w innym dniu"


def test_pusty_motis_nie_tworzy_sekcji(monkeypatch):
    _mock_motis(monkeypatch, [])
    other_day: list = []
    with pytest.raises(MotisError, match="nie zwrócił żadnego połączenia"):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)
    assert other_day == []


def test_bez_other_day_out_zachowanie_jak_dotad(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(19, 6)]])
    with pytest.raises(MotisError, match="innym dniu"):
        variants.build_rail_only_variants(_request())


# --- generate_variants / search_service ------------------------------------------------------


def test_generate_variants_other_day_poza_built(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(19, 6)], [_rail(19, 9)]])
    other_day: list = []

    built, skipped = variants.generate_variants(_request(), other_day_out=other_day)

    assert built == []
    assert len(other_day) == 2
    assert any("innym dniu" in s.reason for s in skipped)  # powód z PR #100 zostaje
    with pytest.raises(ValueError):
        pick_recommendations(built)  # niczego z other_day nie ma w puli rankingów


def test_generate_variants_niepusty_wynik_nie_dokleja_sekcji(monkeypatch):
    """Gdy wynik nie jest pusty (tu: wariant z alternatywnego startu w dniu zapytania), sekcji
    "inny dzień" nie ma — jest tylko przy pustym wyniku."""
    main = [[_rail(19, 6)]]
    alt = [[_rail(17, 6)]]

    def fake_all(origin, destination, time):
        return [list(o) for o in (alt if origin == "ALT" else main)]

    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", fake_all)
    monkeypatch.setattr(variants.motis_client, "stop_id", lambda s: s)
    other_day: list = []

    built, _ = variants.generate_variants(
        _request(),
        alternative_origin_stops=[variants.AlternativeStop("Alt", "ALT")],
        other_day_out=other_day,
    )

    assert len(built) == 1
    assert other_day == []


def test_search_zwraca_other_day_i_puste_rankingi(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(19, 6)], [_rail(19, 9)], [_rail(20, 6)], [_rail(20, 9)]])
    monkeypatch.setattr(search_service, "discover_hubs", lambda *a, **k: ([], []))

    result = search_service.search(_request())

    assert result.built == []
    assert result.recommendations == {}
    assert len(result.other_day) == 3
    built_ids = {id(it) for it in result.built}
    assert all(id(v.itinerary) not in built_ids for v in result.other_day)


# --- API ----------------------------------------------------------------------------------------


def test_api_route_zwraca_other_day_variants(monkeypatch):
    monkeypatch.setattr(
        variants.motis_client,
        "geocode",
        lambda text: (50.0647, 19.9450, "Kraków Główny")
        if "krak" in text.lower()
        else (49.6553, 21.1597, "Gorlice"),
    )
    monkeypatch.setattr(variants.motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")
    _mock_motis(monkeypatch, [[_rail(19, 6)], [_rail(19, 9)]])
    monkeypatch.setattr(search_service, "discover_hubs", lambda *a, **k: ([], []))

    response = client.post(
        "/route", json={"origin": "Kraków Główny", "destination": "Gorlice", "date": D}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["built"] == []
    assert body["recommendations"] == {}
    other = body["other_day_variants"]
    assert len(other) == 2
    for item in other:
        assert item["date"] == "2026-10-19"
        assert item["requested_date"] == D
        assert item["days_offset"] == 2
        assert "NIE jest dzień zapytania" in item["label"]
        assert item["itinerary"]["legs"][0]["leg"]["origin_name"] == "Kraków Główny"
        assert item["itinerary"]["total_price_pln"] > 0


def test_api_route_dzien_zapytania_ma_polaczenie_other_day_variants_puste(monkeypatch):
    monkeypatch.setattr(
        variants.motis_client, "geocode", lambda text: (50.0, 19.9, text)
    )
    monkeypatch.setattr(variants.motis_client, "coords_place", lambda lat, lon: f"{lat},{lon}")
    _mock_motis(monkeypatch, [[_rail(17, 6)], [_rail(19, 6)]])
    monkeypatch.setattr(search_service, "discover_hubs", lambda *a, **k: ([], []))

    body = client.post(
        "/route", json={"origin": "Kraków", "destination": "Gorlice", "date": D}
    ).json()

    assert len(body["built"]) == 1
    assert body["other_day_variants"] == []
    assert "najtansza" in body["recommendations"]


# --- demo.py ------------------------------------------------------------------------------------


def test_demo_format_other_day_section_ma_date_i_etykiete(monkeypatch):
    _mock_motis(monkeypatch, [[_rail(19, 6)]])
    other_day: list = []
    with pytest.raises(MotisError):
        variants.build_rail_only_variants(_request(), other_day_out=other_day)

    text = demo.format_other_day_section(other_day)

    assert OTHER_DAY_SECTION_TITLE in text
    assert "2026-10-19" in text
    assert "NIE jest dzień zapytania" in text
    assert "Cena łączna" in text
    assert demo.format_other_day_section([]) == ""


def test_demo_main_drukuje_sekcje_przy_pustym_wyniku(monkeypatch, capsys):
    monkeypatch.setattr(demo, "request_from_addresses", lambda *a, **kw: _request())
    monkeypatch.setattr(demo, "format_city_section", lambda *a, **kw: "")
    _mock_motis(monkeypatch, [[_rail(19, 6)]])
    monkeypatch.setattr(
        "sys.argv", ["demo.py", "--from", "Kraków", "--to", "Gorlice", "--date", D]
    )

    demo.main()

    out = capsys.readouterr().out
    assert "Brak żadnego działającego wariantu" in out
    assert OTHER_DAY_SECTION_TITLE in out
    assert "2026-10-19" in out and "NIE jest dzień zapytania" in out
    assert "rekomendacj" not in out  # żadnych rankingów dla innego dnia


# --- UI (ui_helpers) --------------------------------------------------------------------------


def _ui_app():
    from datetime import UTC, datetime

    from routing.model import Itinerary, OtherDayVariant
    from ui_helpers import render_other_day_section

    def it(day):
        return Itinerary(
            variant_name="Tylko kolej (rail, 0 przesiadki)",
            legs=[],
            total_price_pln=40.0,
            total_duration_min=120.0,
            num_transfers=0,
        )

    other_day = [
        OtherDayVariant(it(19), "2026-10-19", "2026-10-17", 2),
        OtherDayVariant(it(20), "2026-10-20", "2026-10-17", 3),
    ]
    import streamlit as st

    render_other_day_section(other_day, lambda itinerary: st.caption("RENDER-WARIANTU"))
    render_other_day_section([], lambda itinerary: st.caption("NIE-POWINNO-SIE-POJAWIC"))


def test_ui_sekcja_innego_dnia():
    at = AppTest.from_function(_ui_app).run()

    assert not at.exception
    assert [h.value for h in at.header] == [OTHER_DAY_SECTION_TITLE]
    assert "NIE jest dzień zapytania" in at.warning[0].value
    assert len(at.expander) == 2
    assert "2026-10-19" in at.expander[0].label and "2026-10-20" in at.expander[1].label
    assert all("NIE jest dzień zapytania" in e.error[0].value for e in at.expander)
    assert all("2026-10-" in e.error[0].value for e in at.expander)
    captions = [c.value for c in at.caption]
    assert captions.count("RENDER-WARIANTU") == 2
    assert "NIE-POWINNO-SIE-POJAWIC" not in captions


def test_model_etykieta_dnia_przed(monkeypatch):
    from routing.model import OtherDayVariant

    v = OtherDayVariant(SimpleNamespace(), "2026-10-16", D, -1)
    assert "1 dzień wcześniej" in v.label and "NIE jest dzień zapytania" in v.label
