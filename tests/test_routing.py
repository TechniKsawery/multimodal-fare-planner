from datetime import UTC, datetime, timedelta

import pytest

from fares.model import Carrier, DiscountProfile
from flights.travelpayouts import TravelpayoutsError
from routing import motis_client, pricing, scoring, transfers, variants
from routing.model import Leg, LegMode, PricedLeg
from routing.motis_client import MotisError


def _dt(hour, minute=0, day=28):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def make_leg(
    mode,
    origin,
    destination,
    depart,
    arrive,
    *,
    carrier="",
    requires_walk=True,
    distance_km=100.0,
    extra=None,
):
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=arrive,
        carrier_name=carrier,
        distance_km=distance_km,
        requires_walk=requires_walk,
        extra=extra or {},
    )


# --- motis_client: parsowanie itinerary MOTIS na Leg -------------------------------------

RAW_ITINERARY = {
    "duration": 3600,
    "legs": [
        {
            "mode": "REGIONAL_RAIL",
            "from": {
                "name": "Lublin Główny",
                "stopId": "pl_50500_RAIL_1_52",
                "lat": 51.23,
                "lon": 22.57,
                "departure": "2026-09-28T06:25:00Z",
            },
            "to": {
                "name": "Warszawa Wschodnia",
                "stopId": "pl_38653_RAIL_1_10",
                "lat": 52.25,
                "lon": 21.05,
                "arrival": "2026-09-28T08:11:00Z",
            },
            "duration": 6360,
            "startTime": "2026-09-28T06:25:00Z",
            "endTime": "2026-09-28T08:11:00Z",
            "agencyName": "PKP Intercity",
            "routeShortName": "IC",
        },
        {
            "mode": "WALK",
            "from": {"name": "Warszawa Wschodnia", "lat": 52.25, "lon": 21.05},
            "to": {"name": "Warszawa Wschodnia", "lat": 52.25, "lon": 21.05},
            "duration": 120,
            "startTime": "2026-09-28T08:11:00Z",
            "endTime": "2026-09-28T08:13:00Z",
        },
        {
            "mode": "REGIONAL_RAIL",
            "from": {
                "name": "Warszawa Wschodnia",
                "stopId": "pl_38653_RAIL_1_10",
                "lat": 52.25,
                "lon": 21.05,
                "departure": "2026-09-28T08:49:00Z",
            },
            "to": {
                "name": "Berlin-Lichtenberg",
                "stopId": "pl_140533_FALLBACK",
                "lat": 52.51,
                "lon": 13.5,
                "arrival": "2026-09-28T14:03:00Z",
            },
            "duration": 18840,
            "startTime": "2026-09-28T08:49:00Z",
            "endTime": "2026-09-28T14:03:00Z",
            "agencyName": "PKP Intercity",
            "routeShortName": "EIC",
        },
    ],
}


def test_itinerary_to_legs_pomija_walk_i_wykrywa_przesiadke_z_przejsciem():
    legs = motis_client.itinerary_to_legs(RAW_ITINERARY)

    assert len(legs) == 2
    assert legs[0].origin_name == "Lublin Główny"
    assert legs[0].destination_name == "Warszawa Wschodnia"
    assert legs[0].requires_walk is False  # pierwszy leg, nic przed nim
    assert legs[1].requires_walk is True  # poprzedzony legiem WALK w surowych danych
    assert legs[0].carrier_name == "PKP Intercity"
    assert legs[0].distance_km > 0


def test_itinerary_to_legs_bez_walk_nie_wymaga_przejscia():
    raw = {
        "legs": [RAW_ITINERARY["legs"][0], RAW_ITINERARY["legs"][2]],
    }
    legs = motis_client.itinerary_to_legs(raw)
    assert legs[1].requires_walk is False


def test_fastest_itinerary_wybiera_najkrotszy_czas():
    payload = {"itineraries": [{"duration": 500, "id": "a"}, {"duration": 100, "id": "b"}]}
    assert motis_client.fastest_itinerary(payload)["id"] == "b"


def test_fewest_transfers_itinerary_preferuje_mniej_przesiadek():
    payload = {
        "itineraries": [
            {"duration": 100, "transfers": 2, "id": "a"},
            {"duration": 200, "transfers": 1, "id": "b"},
        ]
    }
    assert motis_client.fewest_transfers_itinerary(payload)["id"] == "b"


WALK_ONLY = {
    "duration": 420,
    "transfers": 0,
    "id": "pieszo",
    "legs": [
        {
            "mode": "WALK",
            "from": {"name": "Plac Defilad", "lat": 52.2318, "lon": 21.0060},
            "to": {"name": "Warszawa Centralna", "lat": 52.2289, "lon": 21.0033},
            "startTime": "2026-10-09T06:00:00Z",
            "endTime": "2026-10-09T06:07:00Z",
            "distance": 480,
        }
    ],
}


def test_fastest_itinerary_uwzglednia_direct_pieszo():
    """Regresja: Plac Defilad -> Dworzec Centralny (~500 m) dawał 7,3 h przez Poznań, bo lista
    `direct` (marsz) z odpowiedzi MOTIS była ignorowana."""
    payload = {"itineraries": [{"duration": 26400, "transfers": 3, "id": "poznan"}],
               "direct": [WALK_ONLY]}
    assert motis_client.fastest_itinerary(payload)["id"] == "pieszo"
    assert motis_client.fewest_transfers_itinerary(payload)["id"] == "pieszo"


def test_plan_tylko_direct_nie_podnosi_bledu(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"itineraries": [], "direct": [WALK_ONLY]}

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    payload = motis_client.plan("a", "b", "2026-10-09T06:00:00Z")
    legs = motis_client.itinerary_to_legs(motis_client.fastest_itinerary(payload))
    assert [l.mode for l in legs] == [LegMode.WALK]


def test_plan_bez_itinerariow_podnosi_motiserror(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"itineraries": []}

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    with pytest.raises(MotisError):
        motis_client.plan("a", "b", "2026-09-28T06:00:00Z")


# --- transfers: bezpieczeństwo przesiadek -------------------------------------------------


def test_przesiadka_na_tym_samym_peronie_wystarczajaca():
    prev = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), requires_walk=False)
    nxt = make_leg(LegMode.RAIL, "B", "C", _dt(8, 25), _dt(10), requires_walk=False)
    assert transfers.check_transfer(prev, nxt, 0) is None  # 25 min >= 20 min


def test_przesiadka_na_tym_samym_peronie_za_krotka():
    prev = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), requires_walk=False)
    nxt = make_leg(LegMode.RAIL, "B", "C", _dt(8, 10), _dt(10), requires_walk=False)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None
    assert warning.gap_minutes == 10
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_SAME_PLATFORM


def test_przesiadka_z_przejsciem_wymaga_wiecej_czasu():
    prev = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), requires_walk=False)
    nxt = make_leg(LegMode.RAIL, "B2", "C", _dt(8, 25), _dt(10), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None  # 25 min < 30 min (wymaga przejścia, inny przystanek "B" -> "B2")


def test_przesiadka_ten_sam_przystanek_mimo_requires_walk_nie_wymaga_pelnego_bufora():
    """MOTIS czasem wstawia leg WALK (requires_walk=True) nawet między dwoma odcinkami z tym
    samym przystankiem po obu stronach (osobne perony/wejścia tego samego kompleksu, np. Essen
    Altenessen Bf -> Essen Altenessen Bf) — to NIE jest zmiana dworca, więc obowiązuje próg
    "ten sam peron" (20 min), a nie "zmiana dworca" (30 min)."""
    prev = make_leg(LegMode.BUS, "A", "Essen Altenessen Bf", _dt(6), _dt(8), requires_walk=False)
    nxt = make_leg(LegMode.RAIL, "Essen Altenessen Bf", "C", _dt(8, 4), _dt(10), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None  # 4 min < 20 min (nadal za krótko, ale tylko ryzykowne)
    assert warning.infeasible is False
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_SAME_PLATFORM

    ok_nxt = make_leg(
        LegMode.RAIL, "Essen Altenessen Bf", "C", _dt(8, 25), _dt(10), requires_walk=True
    )
    assert transfers.check_transfer(prev, ok_nxt, 0) is None  # 25 min >= 20 min, ten sam przystanek


def test_przesiadka_znany_alias_kompleksu_dworcowego_nie_wymaga_pelnego_bufora():
    """ "Dworzec Lublin - Kunickiego" i "Lublin Główny" to różne nazwy tego samego budynku
    (potwierdzone ręcznie, patrz KNOWN_STATION_COMPLEX_ALIASES) — mimo różnych nazw powinno
    dostać próg "ten sam peron" (20 min / 3 min absolutnego minimum), nie "zmiana dworca"
    (30 min / 8 min)."""
    prev = make_leg(
        LegMode.BUS, "A", "Dworzec Lublin - Kunickiego", _dt(6), _dt(8), requires_walk=False
    )

    # 5 min: poniżej absolutnego minimum "zmiana dworca" (8 min) -> pod starą logiką byłoby to
    # NIEWYKONALNE, mimo że to jeden budynek. Po poprawce: nadal za krótko na próg bezpieczny
    # (3-20 min), ale już nie niewykonalne.
    nxt = make_leg(LegMode.RAIL, "Lublin Główny", "C", _dt(8, 5), _dt(10), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None
    assert warning.infeasible is False
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_SAME_PLATFORM

    # Zgłoszony przez usera realny przypadek to tylko 2 min — to nadal poniżej absolutnego
    # minimum nawet w obrębie jednego budynku (3 min), więc zostaje NIEWYKONALNE, tak jak user
    # sam ocenił to zgłoszenie ("wygląda na realny, poprawnie odrzucony przypadek").
    too_tight = make_leg(LegMode.RAIL, "Lublin Główny", "C", _dt(8, 2), _dt(10), requires_walk=True)
    warning_too_tight = transfers.check_transfer(prev, too_tight, 0)
    assert warning_too_tight.infeasible is True


def test_przesiadka_dworzec_lublin_krotsza_nazwa_tez_jest_znanym_aliasem():
    """ "Dworzec Lublin" (bez "- Kunickiego") to ten sam kompleks metropolitalny w Lublinie —
    zaobserwowane w praktyce jako osobna nazwa przystanku w GTFS/MOTIS obok "Dworzec Lublin -
    Kunickiego" i "Lublin Główny" (patrz KNOWN_STATION_COMPLEX_ALIASES)."""
    prev = make_leg(LegMode.BUS, "A", "Dworzec Lublin", _dt(6), _dt(8), requires_walk=False)

    # 17 min: realny przypadek zaobserwowany lokalnie (wariant "Tylko kolej") — poniżej progu
    # "ten sam peron" (20 min), więc nadal RYZYKOWNE, ale (po poprawce) już nie niewykonalne
    # ani nie "zmiana dworca" wymagająca 30 min.
    nxt = make_leg(LegMode.RAIL, "Lublin Główny", "C", _dt(8, 17), _dt(10), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None
    assert warning.infeasible is False
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_SAME_PLATFORM

    ok_nxt = make_leg(LegMode.RAIL, "Lublin Główny", "C", _dt(8, 25), _dt(10), requires_walk=True)
    assert transfers.check_transfer(prev, ok_nxt, 0) is None  # 25 min >= 20 min


def test_przesiadka_berlin_lichtenberg_i_su_lichtenberg_to_ten_sam_wezel():
    """Zgłoszone w praktyce jako fałszywie oznaczone "wymaga zmiany dworca" (30 min) — to
    zintegrowany węzeł (dworzec dalekobieżny/regionalny + S-Bahn/U-Bahn), jeden budynek
    połączony przejściem podziemnym (potwierdzone na Wikipedii), patrz
    KNOWN_STATION_COMPLEX_ALIASES."""
    prev = make_leg(LegMode.RAIL, "A", "Berlin-Lichtenberg", _dt(6), _dt(8), requires_walk=False)
    nxt = make_leg(
        LegMode.BUS, "S+U Lichtenberg Bhf (Berlin)", "C", _dt(8, 3), _dt(10), requires_walk=True
    )
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None  # 3 min < 20 min, nadal ryzykowne
    assert warning.infeasible is False  # ale 3 min >= 3 min absolutnego minimum -> nie niewykonalne
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_SAME_PLATFORM


def test_przesiadka_kolej_lot_wymaga_duzego_bufora():
    prev = make_leg(LegMode.RAIL, "A", "Lotnisko", _dt(6), _dt(8))
    nxt = make_leg(LegMode.FLIGHT, "Lotnisko", "X", _dt(9), _dt(11))
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None  # tylko 60 min, potrzeba 120
    assert warning.minimum_required_minutes == transfers.MIN_TRANSFER_MINUTES_RAIL_TO_FLIGHT


def test_przesiadka_lot_kolej_z_wystarczajacym_buforem():
    prev = make_leg(LegMode.FLIGHT, "X", "Lotnisko", _dt(6), _dt(8))
    nxt = make_leg(LegMode.RAIL, "Lotnisko", "Y", _dt(9, 35), _dt(11))
    assert transfers.check_transfer(prev, nxt, 0) is None  # 95 min >= 90


def test_check_all_transfers_zbiera_wiele_ostrzezen():
    legs = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), requires_walk=False),
        make_leg(LegMode.RAIL, "B", "C", _dt(8, 5), _dt(10), requires_walk=False),  # zbyt krótko
        make_leg(LegMode.RAIL, "C", "D", _dt(10, 30), _dt(12), requires_walk=False),  # ok
    ]
    warnings = transfers.check_all_transfers(legs)
    assert len(warnings) == 1
    assert warnings[0].after_leg_index == 0


# --- pricing: dispatch kolej/lot -----------------------------------------------------------


def test_infer_rail_carrier_pkp():
    assert pricing.infer_rail_carrier("PKP Intercity") is Carrier.PKP_INTERCITY


def test_infer_rail_carrier_db():
    assert pricing.infer_rail_carrier("DB Fernverkehr AG") is Carrier.DB


def test_infer_rail_carrier_regionalny_niemiecki_jako_vrr():
    assert pricing.infer_rail_carrier("S Bahn Berlin GmbH") is Carrier.VRR


def test_infer_rail_carrier_nieznany_zwraca_none():
    assert pricing.infer_rail_carrier("Jakiś Nieznany Przewoźnik") is None


def test_currency_convert_ten_sam_kurs_co_to_pln():
    from routing import currency

    # 10 EUR -> PLN po kursie z PLACEHOLDER_RATES_TO_PLN (4.3775, kurs NBP 2026-10-09)
    assert currency.convert(10.0, "EUR", "PLN") == pytest.approx(43.775)
    # PLN -> EUR to odwrotność tego samego kursu
    assert currency.convert(43.775, "PLN", "EUR") == pytest.approx(10.0)
    # ta sama waluta: bez zmian
    assert currency.convert(10.0, "EUR", "EUR") == 10.0


def test_price_rail_leg_nieznany_przewoznik_uzywa_fallbacku():
    leg = make_leg(
        LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="Coś Nieznanego", distance_km=100
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_type == "szacunek"
    assert priced.amount == pytest.approx(100 * pricing.GENERIC_FALLBACK_PLN_PER_KM)
    assert priced.currency == "PLN"


def test_price_rail_leg_pkp_woła_fares(monkeypatch):
    leg = make_leg(
        LegMode.RAIL,
        "Lublin",
        "Warszawa Wschodnia",
        _dt(6),
        _dt(8),
        carrier="PKP Intercity",
        distance_km=170,
    )

    calls = {}

    def fake_estimate(segment):
        calls["segment"] = segment
        from fares.model import PriceEstimate, PriceType

        return PriceEstimate(
            carrier=segment.carrier,
            amount=49.0,
            currency="PLN",
            price_type=PriceType.OFFICIAL,
            breakdown={},
            notes="test",
        )

    monkeypatch.setattr(pricing, "fares_estimate_price", fake_estimate)
    priced = pricing.price_rail_leg(leg, DiscountProfile())

    assert priced.amount == 49.0
    assert calls["segment"].carrier is Carrier.PKP_INTERCITY
    assert calls["segment"].distance_km == 170


def test_price_rail_leg_s_bahn_hamburg_uzywa_hvv_nie_vrr():
    # Regresja 2026-10-11: MOTIS klasyfikuje S-Bahn Hamburg jako RAIL (nie BUS), a nazwa
    # przewoźnika "S-Bahn Hamburg" zawiera "s-bahn" z VRR_AREA_KEYWORDS — bez poprawki
    # infer_rail_carrier() łapał to jako Carrier.VRR i liczył taryfą eezy.nrw (Zagłębie
    # Ruhry) zamiast HVV. Realny test na żywym MOTIS: 4.10/1.50/0.00 EUR (HVV) vs błędne
    # 2.46 EUR (VRR) przed poprawką — patrz verification/.
    leg = make_leg(
        LegMode.RAIL,
        "Hamburg Hbf",
        "Landungsbrücken",
        _dt(6),
        _dt(6, 6),
        carrier="S-Bahn Hamburg",
        distance_km=1.5,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.amount == pytest.approx(4.10)
    assert priced.price_type == "oficjalna_taryfa"

    priced_dziecko = pricing.price_rail_leg(leg, DiscountProfile(hvv_dziecko=True))
    assert priced_dziecko.amount == pytest.approx(1.50)

    priced_niepelnosprawnosc = pricing.price_rail_leg(
        leg, DiscountProfile(schwerbehinderte_wertmarke_de=True)
    )
    assert priced_niepelnosprawnosc.amount == pytest.approx(0.0)


def test_price_rail_leg_db_regio_koln_uzywa_vrs_nie_vrr():
    # Ta sama regresja co wyżej, ale dla Kolonii: agencja "DB Regio AG NRW" nie zawiera
    # "köln" w nazwie (w przeciwieństwie do Hamburga, gdzie "hamburg" jest w nazwie
    # przewoźnika) — rozpoznanie musi patrzeć też na origin/destination, nie tylko carrier_name.
    leg = make_leg(
        LegMode.RAIL,
        "Köln Hbf",
        "Köln Messe/Deutz Bf",
        _dt(6),
        _dt(6, 6),
        carrier="DB Regio AG NRW",
        distance_km=2.0,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.price_type == "oficjalna_taryfa"
    # fares/kvb.py (VRS Köln Preisstufe 1b) — nie eezy.nrw (VRR), inna kwota/strefa.
    from fares.calculator import estimate_price as _estimate_price
    from fares.model import Carrier as _Carrier
    from fares.model import Segment as _Segment

    vrs_result = _estimate_price(_Segment(carrier=_Carrier.VRS_KOLN, origin="a", destination="b"))
    assert priced.amount == pytest.approx(vrs_result.amount)


def test_price_rail_leg_regionalny_nrw_bez_miasta_nadal_vrr():
    # Upewniamy się, że poprawka nie zepsuła domyślnego dopasowania VRR dla regionalnych
    # tras NRW, które nie wspominają Hamburga/Monachium/Kolonii (np. Essen-Dortmund).
    leg = make_leg(
        LegMode.RAIL,
        "Essen Hbf",
        "Dortmund Hbf",
        _dt(6),
        _dt(7),
        carrier="DB Regio AG NRW",
        distance_km=40,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.price_type == "oficjalna_taryfa"

    from fares.calculator import estimate_price as _estimate_price
    from fares.model import Carrier as _Carrier
    from fares.model import Segment as _Segment

    vrr_result = _estimate_price(_Segment(carrier=_Carrier.VRR, origin="a", destination="b", distance_km=40))
    assert priced.amount == pytest.approx(vrr_result.amount)


def test_price_rail_leg_gdy_fares_odrzuci_segment_uzywa_fallbacku(monkeypatch):
    leg = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=100)

    def fake_estimate(segment):
        raise ValueError("nieznany kod ulgi")

    monkeypatch.setattr(pricing, "fares_estimate_price", fake_estimate)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_type == "szacunek"
    assert "błąd" in priced.notes


def test_price_flight_leg_woła_flights(monkeypatch):
    leg = make_leg(
        LegMode.FLIGHT,
        "WAW",
        "DTM",
        _dt(6),
        _dt(8),
        extra={"origin_iata": "WAW", "destination_iata": "DTM", "depart_date": "2026-11-15"},
    )

    def fake_estimate(segment):
        from flights.model import PriceEstimate, PriceType

        return PriceEstimate(
            origin="WAW",
            destination="DTM",
            amount=350.0,
            currency="PLN",
            price_type=PriceType.ESTIMATE,
            breakdown={"cena_biletu": 200.0, "bagaz": 150.0},
            notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    priced = pricing.price_flight_leg(leg)
    assert priced.amount == 350.0
    assert priced.currency == "PLN"
    assert priced.breakdown == {"cena_biletu": 200.0, "bagaz": 150.0}


def test_price_flight_leg_doklada_tylko_bagaz_bez_dojazdu_i_transferu(monkeypatch):
    """WAW-DTM ma w flights/data/extras_placeholder.json wpis z bagaz+dojazd_na_lotnisko+
    transfer_z_lotniska — routing ma doliczyć TYLKO bagaz, bo dojazd/transfer są już osobnymi
    odcinkami kolejowymi w wariancie mieszanym (patrz build_rail_flight_rail_variant)."""
    leg = make_leg(
        LegMode.FLIGHT,
        "WAW",
        "DTM",
        _dt(6),
        _dt(8),
        extra={"origin_iata": "WAW", "destination_iata": "DTM", "depart_date": "2026-11-15"},
    )

    captured = {}

    def fake_estimate(segment):
        captured["segment"] = segment
        from flights.model import PriceEstimate, PriceType

        return PriceEstimate(
            origin="WAW",
            destination="DTM",
            amount=0.0,
            currency="PLN",
            price_type=PriceType.ESTIMATE,
            breakdown={},
            notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    pricing.price_flight_leg(leg)

    extras = captured["segment"].extras
    assert extras is not None
    assert extras.baggage_cost == 150.0  # z tabeli WAW-DTM
    assert extras.airport_access_cost == 0.0  # NIE dokładamy — to już osobny leg kolejowy
    assert extras.destination_transfer_cost == 0.0


def test_price_flight_leg_nadpisuje_bagaz_realnym_cennikiem_linii(monkeypatch):
    """Gdy bilet wraca z linią znaną w flights/data/baggage_by_airline.json (tu: Ryanair, FR),
    routing ma nadpisać placeholderowy bagaż z tabeli relacji realną ceną tej linii."""
    leg = make_leg(
        LegMode.FLIGHT,
        "WAW",
        "DTM",
        _dt(6),
        _dt(8),
        extra={"origin_iata": "WAW", "destination_iata": "DTM", "depart_date": "2026-11-15"},
    )

    def fake_estimate(segment):
        from flights.model import PriceEstimate, PriceType

        # symuluje flights.calculator: bagaz=150 z placeholderowej tabeli WAW-DTM, zanim
        # routing dowie się, że linią jest Ryanair (FR)
        return PriceEstimate(
            origin="WAW",
            destination="DTM",
            amount=650.0,
            currency="PLN",
            price_type=PriceType.ESTIMATE,
            breakdown={"cena_biletu": 500.0, "linia": "FR", "bagaz": 150.0},
            notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    priced = pricing.price_flight_leg(leg)

    # 21 EUR (Ryanair, tabela baggage_by_airline.json) x 4.3775 PLN/EUR (routing/currency.py) = 91.9275, zaokrąglone do 91.93
    assert priced.breakdown["bagaz"] == pytest.approx(91.93)
    assert priced.amount == pytest.approx(500.0 + 91.93)
    assert "Ryanair" in priced.breakdown["bagaz_zrodlo"]
    assert "Ryanair" in priced.notes


def test_price_flight_leg_nieznana_linia_zostawia_bagaz_z_tabeli_relacji(monkeypatch):
    leg = make_leg(
        LegMode.FLIGHT,
        "WAW",
        "DTM",
        _dt(6),
        _dt(8),
        extra={"origin_iata": "WAW", "destination_iata": "DTM", "depart_date": "2026-11-15"},
    )

    def fake_estimate(segment):
        from flights.model import PriceEstimate, PriceType

        return PriceEstimate(
            origin="WAW",
            destination="DTM",
            amount=650.0,
            currency="PLN",
            price_type=PriceType.ESTIMATE,
            breakdown={"cena_biletu": 500.0, "linia": "ZZ", "bagaz": 150.0},
            notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    priced = pricing.price_flight_leg(leg)

    assert priced.amount == 650.0
    assert priced.breakdown["bagaz"] == 150.0
    assert "bagaz_zrodlo" not in priced.breakdown


def test_price_flight_leg_nieznana_relacja_uzywa_domyslnego_szacunku_bagazu(monkeypatch):
    leg = make_leg(
        LegMode.FLIGHT,
        "XXX",
        "YYY",
        _dt(6),
        _dt(8),
        extra={"origin_iata": "XXX", "destination_iata": "YYY", "depart_date": "2026-11-15"},
    )

    captured = {}

    def fake_estimate(segment):
        captured["segment"] = segment
        from flights.model import PriceEstimate, PriceType

        return PriceEstimate(
            origin="XXX",
            destination="YYY",
            amount=0.0,
            currency="PLN",
            price_type=PriceType.ESTIMATE,
            breakdown={},
            notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    pricing.price_flight_leg(leg)

    extras = captured["segment"].extras
    assert extras.baggage_cost == pricing.DEFAULT_BAGGAGE_ESTIMATE_PLN
    assert extras.airport_access_cost == 0.0
    assert extras.destination_transfer_cost == 0.0


def test_price_leg_dispatch_na_podstawie_mode(monkeypatch):
    monkeypatch.setattr(pricing, "infer_rail_carrier", lambda name: None)
    rail_leg = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), distance_km=50)
    priced = pricing.price_leg(rail_leg, DiscountProfile())
    assert priced.currency == "PLN"


# --- scoring: budowa Itinerary i wybór rekomendacji ---------------------------------------


def _priced(mode, origin, destination, depart, arrive, amount, currency="PLN", requires_walk=False):
    leg = make_leg(mode, origin, destination, depart, arrive, requires_walk=requires_walk)
    return PricedLeg(leg=leg, amount=amount, currency=currency, price_type="szacunek")


def test_build_itinerary_liczy_cene_czas_i_przesiadki():
    legs = [
        _priced(LegMode.RAIL, "A", "B", _dt(6), _dt(8), 50.0),
        _priced(LegMode.RAIL, "B", "C", _dt(8, 30), _dt(10), 30.0),
    ]
    itinerary = scoring.build_itinerary("Test", legs)

    assert itinerary.total_price_pln == 80.0
    assert itinerary.total_duration_min == 240  # 06:00 -> 10:00
    assert itinerary.num_transfers == 1
    assert itinerary.transfer_warnings == []
    assert itinerary.is_risky is False


def test_build_itinerary_wykrywa_ryzykowna_przesiadke():
    legs = [
        _priced(LegMode.RAIL, "A", "B", _dt(6), _dt(8), 50.0),
        _priced(LegMode.RAIL, "B", "C", _dt(8, 5), _dt(10), 30.0),
    ]
    itinerary = scoring.build_itinerary("Test", legs)
    assert itinerary.is_risky is True
    assert len(itinerary.transfer_warnings) == 1


def test_build_itinerary_konwertuje_eur_do_pln_dla_sumy():
    legs = [_priced(LegMode.RAIL, "A", "B", _dt(6), _dt(8), 10.0, currency="EUR")]
    itinerary = scoring.build_itinerary("Test", legs)
    from routing.currency import PLACEHOLDER_RATES_TO_PLN

    assert itinerary.total_price_pln == pytest.approx(10.0 * PLACEHOLDER_RATES_TO_PLN["EUR"], abs=0.01)


def test_build_itinerary_bez_legow_podnosi_blad():
    with pytest.raises(ValueError):
        scoring.build_itinerary("Test", [])


def _itinerary(name, price_pln, duration_min, num_transfers):
    from routing.model import Itinerary

    return Itinerary(
        variant_name=name,
        legs=[],
        total_price_pln=price_pln,
        total_duration_min=duration_min,
        num_transfers=num_transfers,
    )


def test_pick_recommendations_wybiera_cztery_kategorie():
    cheap = _itinerary("tania", 50, 600, 3)  # 50 + 10h*40 = 450
    fast = _itinerary("szybka", 400, 30, 1)  # 400 + 0.5h*40 = 420
    few_transfers = _itinerary("bez przesiadek", 300, 500, 0)  # ~633
    balanced = _itinerary("zbalansowana", 150, 120, 2)  # 150 + 2h*40 = 230, najniższe

    recs = scoring.pick_recommendations([cheap, fast, few_transfers, balanced])

    assert recs["najtansza"] is cheap
    assert recs["najszybsza"] is fast
    assert recs["najmniej_przesiadek"] is few_transfers
    assert recs["najlepszy_stosunek_ceny_do_czasu"] is balanced


def test_pick_recommendations_pusta_lista_podnosi_blad():
    with pytest.raises(ValueError):
        scoring.pick_recommendations([])


# --- "najlepszy kompromis": znormalizowana pozycja w cenie i czasie względem puli ------------


def test_pick_recommendations_kompromis_wybiera_srodek_a_nie_ekstrema():
    tania_wolna = _itinerary("tania i wolna", 50, 600, 2)  # cena 0.0, czas 1.0 -> 0.5
    droga_szybka = _itinerary("droga i szybka", 500, 60, 2)  # cena 1.0, czas 0.0 -> 0.5
    srodek = _itinerary("kompromisowa", 200, 250, 2)  # cena ~0.33, czas ~0.35 -> najniższe

    recs = scoring.pick_recommendations([tania_wolna, droga_szybka, srodek])

    assert recs["najlepszy_kompromis"] is srodek
    # ekstrema nadal wygrywają w swoich czystych kategoriach
    assert recs["najtansza"] is tania_wolna
    assert recs["najszybsza"] is droga_szybka


def test_pick_recommendations_kompromis_identyczne_ceny_i_czasy_nie_dzieli_przez_zero():
    a = _itinerary("a", 100, 200, 1)
    b = _itinerary("b", 100, 200, 0)  # taka sama cena/czas, mniej przesiadek
    recs = scoring.pick_recommendations([a, b])
    # bez ValueError/ZeroDivisionError przy p_hi == p_lo i d_hi == d_lo; min() bierze pierwszy remis
    assert recs["najlepszy_kompromis"] in (a, b)


def test_pick_recommendations_kompromis_bezpieczny_pomija_ryzykowne_gdy_jest_bezpieczna_alternatywa():
    tania_ryzykowna = _itinerary_z_ryzykiem("ryzykowna", 50, 100, 1, num_risky=1)
    bezpieczna = _itinerary_z_ryzykiem("bezpieczna", 200, 500, 1, num_risky=0)
    recs = scoring.pick_recommendations([tania_ryzykowna, bezpieczna])
    assert recs["najlepszy_kompromis_bezpieczny"] is bezpieczna
    assert bezpieczna.is_safe_fallback is False
    # zwykła kategoria nie filtruje po ryzyku
    assert recs["najlepszy_kompromis"] is tania_ryzykowna


def test_pick_recommendations_kompromis_bezpieczny_ma_fallback_gdy_wszystko_ryzykowne():
    mniej_ryzykowna = _itinerary_z_ryzykiem("mniej ryzykowna", 100, 300, 1, num_risky=1)
    bardziej_ryzykowna = _itinerary_z_ryzykiem("bardziej ryzykowna", 90, 250, 2, num_risky=2)
    recs = scoring.pick_recommendations([mniej_ryzykowna, bardziej_ryzykowna])
    assert recs["najlepszy_kompromis_bezpieczny"] is mniej_ryzykowna
    assert mniej_ryzykowna.is_safe_fallback is True


def test_pick_recommendations_kompromis_pomija_niewykonalne():
    from routing.model import TransferWarning

    impossible = _itinerary("niewykonalna", 1, 1, 0)
    impossible.transfer_warnings = [TransferWarning(0, 2, 8, "x", infeasible=True)]
    ok = _itinerary("ok", 100, 300, 2)
    recs = scoring.pick_recommendations([impossible, ok])
    assert recs["najlepszy_kompromis"] is ok
    assert recs["najlepszy_kompromis_bezpieczny"] is ok


# --- "najszybsza (z Twoimi ulgami)": trzyma się czubka rankingu czasowego, cena rozstrzyga --


def test_pick_recommendations_najszybsza_z_ulgami_wybiera_tansza_wsrod_blisko_najszybszych():
    najszybsza_droga = _itinerary("najszybsza, droga", 500, 600, 1)  # czas referencyjny
    prawie_tak_szybka_tansza = _itinerary(
        "prawie tak szybka, tania", 100, 640, 1
    )  # +40 min (<10%=60)
    dużo_wolniejsza_bardzo_tania = _itinerary(
        "dużo wolniejsza, bardzo tania", 10, 1200, 1
    )  # poza tolerancją

    recs = scoring.pick_recommendations(
        [najszybsza_droga, prawie_tak_szybka_tansza, dużo_wolniejsza_bardzo_tania]
    )

    assert recs["najszybsza_z_ulgami"] is prawie_tak_szybka_tansza
    # samo "najszybsza" (bez tolerancji) nadal bierze czysty czas
    assert recs["najszybsza"] is najszybsza_droga
    # a "najtansza" (czysta cena, bez progu czasowego) bierze najbardziej ekstremalny wariant
    assert recs["najtansza"] is dużo_wolniejsza_bardzo_tania


def test_pick_recommendations_najszybsza_z_ulgami_ma_minimalna_tolerancje_dla_krotkich_tras():
    najszybsza = _itinerary("najszybsza", 200, 60, 0)  # 10% z 60 min = 6 min < próg 10 min
    w_progu_taniej = _itinerary(
        "w progu 10 min, taniej", 50, 69, 0
    )  # +9 min, w tolerancji (próg=10)
    poza_progiem = _itinerary("poza progiem", 10, 80, 0)  # +20 min, poza tolerancją

    recs = scoring.pick_recommendations([najszybsza, w_progu_taniej, poza_progiem])

    assert recs["najszybsza_z_ulgami"] is w_progu_taniej


def test_pick_recommendations_najszybsza_z_ulgami_bezpieczna_pomija_ryzykowne():
    szybka_ryzykowna = _itinerary_z_ryzykiem("szybka ryzykowna", 50, 100, 1, num_risky=1)
    wolna_bezpieczna = _itinerary_z_ryzykiem("wolna bezpieczna", 40, 400, 1, num_risky=0)
    recs = scoring.pick_recommendations([szybka_ryzykowna, wolna_bezpieczna])
    # tylko jeden bezpieczny wariant w puli, więc to on wygrywa mimo że jest wolniejszy
    assert recs["najszybsza_z_ulgami_bezpieczna"] is wolna_bezpieczna
    # zwykła kategoria (bez filtra ryzyka) trzyma się czasu, tu jest tylko jeden szybki wariant
    assert recs["najszybsza_z_ulgami"] is szybka_ryzykowna


def test_pick_recommendations_najszybsza_z_ulgami_pomija_niewykonalne():
    from routing.model import TransferWarning

    impossible = _itinerary("niewykonalna", 1, 1, 0)
    impossible.transfer_warnings = [TransferWarning(0, 2, 8, "x", infeasible=True)]
    ok = _itinerary("ok", 100, 300, 2)
    recs = scoring.pick_recommendations([impossible, ok])
    assert recs["najszybsza_z_ulgami"] is ok
    assert recs["najszybsza_z_ulgami_bezpieczna"] is ok


# --- variants: generowanie wariantów, w tym pomijanie na błędach -------------------------


def test_generate_variants_pomija_lot_bez_tokena(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )

    rail_legs = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)
    ]
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [rail_legs]
    )

    def raise_travelpayouts(*args, **kwargs):
        raise TravelpayoutsError("brak tokena")

    monkeypatch.setattr(variants, "build_rail_flight_rail_variant", raise_travelpayouts)
    monkeypatch.setattr(variants, "build_flight_regional_variant", raise_travelpayouts)

    hub = variants.HubConfig("Test-Hub", "WAW", "DTM", "waw_stop", "dortmund_stop")
    built, skipped = variants.generate_variants(
        request, rail_flight_rail_hubs=[hub], flight_regional_hubs=[hub]
    )

    assert len(built) == 1  # tylko wariant kolejowy
    assert len(skipped) == 2
    assert all("brak tokena" in s.reason for s in skipped)


def test_generate_variants_pomija_kolej_gdy_motis_nie_znajduje_polaczenia(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )

    def raise_motis_error(*args, **kwargs):
        raise MotisError("brak połączenia")

    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", raise_motis_error)

    built, skipped = variants.generate_variants(request)
    assert built == []
    assert len(skipped) == 1
    assert skipped[0].variant_name == "Tylko kolej"


def test_build_rail_only_variants_deduplikuje_identyczne_trasy(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )
    legs_a = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)
    ]
    legs_b = [
        make_leg(LegMode.RAIL, "A", "B", _dt(7), _dt(9), carrier="PKP Intercity", distance_km=170)
    ]

    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [legs_a, legs_b]
    )

    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1  # ta sama sygnatura trasy (A->B) -> zliczona raz


def test_build_rail_flight_rail_variant_laczy_trzy_odcinki(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="lublin",
        destination_stop_id="gelsenkirchen",
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date="2026-09-28",
    )
    hub = variants.HubConfig("Warszawa-Dortmund", "WAW", "DTM", "waw_airport", "dortmund_hbf")

    access_legs = [
        make_leg(
            LegMode.RAIL,
            "Lublin",
            "Warszawa Lotnisko Chopina",
            _dt(6),
            _dt(8),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    onward_legs = [
        make_leg(
            LegMode.RAIL,
            "Dortmund Hbf",
            "Gelsenkirchen Hbf",
            _dt(16),
            _dt(16, 30),
            carrier="DB Regio",
            distance_km=25,
        )
    ]

    calls = []

    def fake_plan_leg_candidates(origin, destination, time, max_candidates=3):
        calls.append((origin, destination))
        return [access_legs] if origin == "lublin" else [onward_legs]

    monkeypatch.setattr(variants.motis_client, "plan_leg_candidates", fake_plan_leg_candidates)
    monkeypatch.setattr(
        variants.pricing,
        "price_leg",
        lambda leg, discounts, currency="PLN": PricedLeg(leg, 10.0, "PLN", "szacunek"),
    )

    itinerary = variants.build_rail_flight_rail_variant(request, hub)

    assert len(itinerary.legs) == 3
    assert itinerary.legs[1].leg.mode is LegMode.FLIGHT
    assert calls[0] == ("lublin", "waw_airport")
    assert calls[1] == ("dortmund_hbf", "gelsenkirchen")


def test_build_rail_flight_rail_variant_wybiera_najlepsza_kombinacje_calosciowo(monkeypatch):
    """Najszybszy dojazd do lotniska ma ryzykowną przesiadkę / droższy bilet niż odrobinę
    wolniejsza alternatywa — wariant powinien wybrać tę drugą, nie automatycznie najszybszy
    pojedynczy fragment (single-itinerary limitation, patrz backlog)."""
    request = variants.RouteRequest(
        origin_stop_id="lublin",
        destination_stop_id="gelsenkirchen",
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date="2026-09-28",
    )
    hub = variants.HubConfig("Warszawa-Dortmund", "WAW", "DTM", "waw_airport", "dortmund_hbf")

    # Najszybszy dojazd: przyjazd 7:55, zostawia tylko 5 min do (sztywnego) bufora 150 min
    # przed lotem liczonym od MOMENTU PRZYJAZDU, więc to akurat nie wpływa na wykonalność —
    # różnicuje je za to CENA (symulowana przez różne distance_km -> różna cena via fares).
    fast_but_pricier = [
        make_leg(
            LegMode.RAIL,
            "Lublin",
            "Warszawa Lotnisko Chopina",
            _dt(6),
            _dt(7, 55),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    slower_but_cheaper = [
        make_leg(
            LegMode.RAIL,
            "Lublin",
            "Warszawa Lotnisko Chopina",
            _dt(6),
            _dt(8, 30),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    onward_legs = [
        make_leg(
            LegMode.RAIL,
            "Dortmund Hbf",
            "Gelsenkirchen Hbf",
            _dt(16),
            _dt(16, 30),
            carrier="DB Regio",
            distance_km=25,
        )
    ]

    def fake_plan_leg_candidates(origin, destination, time, max_candidates=3):
        if origin == "lublin":
            return [fast_but_pricier, slower_but_cheaper]  # posortowane wg czasu, jak prawdziwe API
        return [onward_legs]

    def fake_price_leg(leg, discounts, currency="PLN"):
        amount = 500.0 if leg is fast_but_pricier[0] else 10.0
        return PricedLeg(leg, amount, "PLN", "szacunek")

    monkeypatch.setattr(variants.motis_client, "plan_leg_candidates", fake_plan_leg_candidates)
    monkeypatch.setattr(variants.pricing, "price_leg", fake_price_leg)

    itinerary = variants.build_rail_flight_rail_variant(request, hub)

    assert itinerary.legs[0].leg is slower_but_cheaper[0]
    assert itinerary.total_price_pln < 500


def test_build_flight_regional_variant_wybiera_najlepsza_kombinacje_calosciowo(monkeypatch):
    """Analogicznie do build_rail_flight_rail_variant: odjazd z huba sprawdza kilka alternatyw
    zamiast automatycznie brać najszybszą."""
    request = variants.RouteRequest(
        origin_stop_id="lublin",
        destination_stop_id="gelsenkirchen",
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date="2026-09-28",
    )
    hub = variants.HubConfig("Dortmund", "LUX", "DTM", None, "dortmund_hbf")

    fast_but_pricier = [
        make_leg(
            LegMode.RAIL,
            "Dortmund Hbf",
            "Gelsenkirchen Hbf",
            _dt(16),
            _dt(16, 15),
            carrier="DB Regio",
            distance_km=25,
        )
    ]
    slower_but_cheaper = [
        make_leg(
            LegMode.RAIL,
            "Dortmund Hbf",
            "Gelsenkirchen Hbf",
            _dt(16),
            _dt(16, 40),
            carrier="DB Regio",
            distance_km=25,
        )
    ]

    def fake_plan_leg_candidates(origin, destination, time, max_candidates=3):
        return [fast_but_pricier, slower_but_cheaper]  # posortowane wg czasu, jak prawdziwe API

    def fake_price_leg(leg, discounts, currency="PLN"):
        amount = 500.0 if leg is fast_but_pricier[0] else 10.0
        return PricedLeg(leg, amount, "PLN", "szacunek")

    monkeypatch.setattr(variants.motis_client, "plan_leg_candidates", fake_plan_leg_candidates)
    monkeypatch.setattr(variants.pricing, "price_leg", fake_price_leg)

    itinerary = variants.build_flight_regional_variant(request, hub)

    assert itinerary.legs[-1].leg is slower_but_cheaper[0]
    assert itinerary.total_price_pln < 500


# --- adresy: odcinki piesze (dojście z adresu / do adresu), autobus, geocoding ---------------

ADDRESS_ITINERARY = {
    "legs": [
        {
            "mode": "WALK",
            "from": {"name": "START", "lat": 51.2477, "lon": 22.5592},
            "to": {"name": "Ogród Saski", "stopId": "ztml_1001", "lat": 51.2474, "lon": 22.5514},
            "startTime": "2026-10-05T07:16:00Z",
            "endTime": "2026-10-05T07:24:00Z",
            "distance": 565.0,
        },
        {
            "mode": "BUS",
            "from": {"name": "Ogród Saski", "stopId": "ztml_1001", "lat": 51.2474, "lon": 22.5514},
            "to": {"name": "Dworzec Lublin", "stopId": "ztml_2", "lat": 51.2318, "lon": 22.5692},
            "startTime": "2026-10-05T07:24:00Z",
            "endTime": "2026-10-05T07:32:00Z",
            "agencyName": "ZDiTM Lublin",
        },
        {
            "mode": "WALK",
            "from": {"name": "Dworzec Lublin", "lat": 51.2318, "lon": 22.5692},
            "to": {"name": "Lublin Główny", "lat": 51.2313, "lon": 22.5692},
            "startTime": "2026-10-05T07:32:00Z",
            "endTime": "2026-10-05T07:34:00Z",
        },
        {
            "mode": "REGIONAL_RAIL",
            "from": {"name": "Lublin Główny", "stopId": "pl_50500", "lat": 51.2313, "lon": 22.5692},
            "to": {
                "name": "Gelsenkirchen Hbf",
                "stopId": "defv_344028",
                "lat": 51.5049,
                "lon": 7.1022,
            },
            "startTime": "2026-10-05T08:00:00Z",
            "endTime": "2026-10-05T20:00:00Z",
            "agencyName": "PKP Intercity",
        },
        {
            "mode": "WALK",
            "from": {"name": "Gelsenkirchen Hbf", "lat": 51.5049, "lon": 7.1022},
            "to": {"name": "END", "lat": 51.5060, "lon": 7.1016},
            "startTime": "2026-10-05T20:00:00Z",
            "endTime": "2026-10-05T20:04:00Z",
            "distance": 246.0,
        },
    ]
}


def test_itinerary_z_adresow_zawiera_dojscie_i_autobus():
    legs = motis_client.itinerary_to_legs(ADDRESS_ITINERARY)
    assert [l.mode for l in legs] == [LegMode.WALK, LegMode.BUS, LegMode.RAIL, LegMode.WALK]
    assert legs[0].extra["walk_role"] == "dojscie"
    assert legs[-1].extra["walk_role"] == "dojscie_do_celu"
    assert legs[2].requires_walk is True  # WALK między autobusem a pociągiem


def test_odcinki_piesze_nie_licza_sie_jako_przesiadki():
    legs = motis_client.itinerary_to_legs(ADDRESS_ITINERARY)
    priced = [pricing.price_leg(l, DiscountProfile()) for l in legs]
    itinerary = scoring.build_itinerary("adres-adres", priced)
    assert itinerary.num_transfers == 1  # autobus -> pociąg
    assert itinerary.total_duration_min == 768  # 07:16 -> 20:04
    # autobus 07:32 -> pociąg 08:00 = 28 min. "Dworzec Lublin" -> "Lublin Główny" to znany alias
    # tego samego kompleksu (KNOWN_STATION_COMPLEX_ALIASES) -> próg "ten sam peron" (20 min),
    # 28 min >= 20 min -> bez ostrzeżenia (przed poprawką: 28 < 30 -> 1 ostrzeżenie).
    assert len(itinerary.transfer_warnings) == 0


def test_przesiadka_autobus_pociag_za_krotka_jest_ryzykowna():
    raw = {"legs": [dict(ADDRESS_ITINERARY["legs"][i]) for i in range(5)]}
    raw["legs"][3] = {**raw["legs"][3], "startTime": "2026-10-05T07:36:00Z"}
    legs = motis_client.itinerary_to_legs(raw)
    warnings = transfers.check_all_transfers(legs)
    assert len(warnings) == 1
    assert warnings[0].after_leg_index == 1  # indeks oryginalny (autobus), nie licząc walk


def test_wycena_pieszo_zero_i_autobus_ztm_lublin():
    legs = motis_client.itinerary_to_legs(ADDRESS_ITINERARY)
    assert pricing.price_leg(legs[0], DiscountProfile()).amount == 0
    # Ogród Saski -> Dworzec Lublin, ZDiTM Lublin, 8 min jazdy -> bilet 15-minutowy normalny
    priced = pricing.price_leg(legs[1], DiscountProfile())
    assert priced.amount == 3.40
    assert priced.price_type == "oficjalna_taryfa"


def test_geocode_zwraca_wspolrzedne(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": "Krakowskie Przedmieście 46-50", "lat": 51.2477, "lon": 22.5592}]

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    assert motis_client.geocode("x") == (51.2477, 22.5592, "Krakowskie Przedmieście 46-50")


def test_geocode_brak_wynikow_podnosi_blad(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    with pytest.raises(MotisError):
        motis_client.geocode("nieistniejący adres")


def test_geocode_suggestions_zwraca_liste_i_limituje(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": f"Wynik {i}", "lat": i, "lon": i} for i in range(10)]

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    results = motis_client.geocode_suggestions("Lublin", limit=3)
    assert len(results) == 3
    assert results[0] == {"name": "Wynik 0", "lat": 0, "lon": 0}


def test_geocode_suggestions_pusty_tekst_nie_odpytuje_motis(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("nie powinno wołać MOTIS dla pustego tekstu")

    monkeypatch.setattr(motis_client.requests, "get", boom)
    assert motis_client.geocode_suggestions("   ") == []


def test_geocode_suggestions_brak_wynikow_nie_podnosi_bledu(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(motis_client.requests, "get", lambda *a, **kw: FakeResponse())
    assert motis_client.geocode_suggestions("nieistniejący adres") == []


def test_request_from_addresses_uzywa_wspolrzednych(monkeypatch):
    coords = {"a": (51.0, 22.0, "Adres A"), "b": (51.5, 7.1, "Adres B")}
    monkeypatch.setattr(variants.motis_client, "geocode", lambda text: coords[text])
    request = variants.request_from_addresses("a", "b", "2026-10-05")
    assert request.origin_stop_id == "51.0,22.0"
    assert request.destination_stop_id == "51.5,7.1"
    assert request.origin_label == "Adres A"


def test_tramwaj_i_metro_to_transport_lokalny_a_pociag_to_kolej():
    def raw(mode):
        return {
            "legs": [
                {
                    "mode": mode,
                    "from": {"name": "A", "lat": 51.0, "lon": 7.0},
                    "to": {"name": "B", "lat": 51.1, "lon": 7.0},
                    "startTime": "2026-10-05T07:00:00Z",
                    "endTime": "2026-10-05T07:10:00Z",
                }
            ]
        }

    assert motis_client.itinerary_to_legs(raw("TRAM"))[0].mode is LegMode.BUS
    assert motis_client.itinerary_to_legs(raw("SUBWAY"))[0].mode is LegMode.BUS
    assert motis_client.itinerary_to_legs(raw("REGIONAL_RAIL"))[0].mode is LegMode.RAIL
    assert motis_client.itinerary_to_legs(raw("HIGHSPEED_RAIL"))[0].mode is LegMode.RAIL


def test_autobus_lubelski_taryfa_czasowa_a_inny_autokar_dalekobiezny_fallback_km():
    city = make_leg(
        LegMode.BUS,
        "A",
        "B",
        _dt(6),
        _dt(7),
        carrier="ZDiTM Lublin",
        distance_km=5,
        extra={"motis_mode": "BUS"},
    )
    coach = make_leg(
        LegMode.BUS,
        "A",
        "B",
        _dt(6),
        _dt(12),
        carrier="RegioJet",
        distance_km=500,
        extra={"motis_mode": "BUS"},
    )
    # 60 min jazdy -> najkrótszy pokrywający bilet to 90-minutowy (5.20 PLN normalny)
    assert pricing.price_bus_leg(city).amount == 5.20
    assert pricing.price_bus_leg(coach).amount == pytest.approx(
        500 * pricing.GENERIC_FALLBACK_PLN_PER_KM
    )


def test_flixbus_idzie_przez_fares_flixbus_i_spada_do_fallbacku_km_gdy_api_niedostepne(monkeypatch):
    from fares import _flixbus_api

    def boom(*a, **kw):
        raise _flixbus_api.FlixbusApiError("brak sieci (test)")

    monkeypatch.setattr(_flixbus_api, "find_city_id", boom)
    coach = make_leg(
        LegMode.BUS,
        "A",
        "B",
        _dt(6),
        _dt(12),
        carrier="Flixbus",
        distance_km=500,
        extra={"motis_mode": "BUS"},
    )
    priced = pricing.price_bus_leg(coach)
    from fares.flixbus import _FALLBACK

    assert priced.amount == pytest.approx(500 * _FALLBACK["pln_per_km"])
    assert priced.price_type == "szacunek"


def test_tramwaj_vrr_wyceniany_eezy_nrw():
    tram = make_leg(
        LegMode.BUS,
        "Essen Hbf",
        "Essen Rüttenscheid",
        _dt(6),
        _dt(6, 12),
        carrier="Ruhrbahn",
        distance_km=3.5,
        extra={"motis_mode": "TRAM"},
    )
    priced = pricing.price_bus_leg(tram)
    assert priced.currency == "EUR"
    assert priced.price_type == "oficjalna_taryfa"
    assert priced.amount > 0


def test_autobus_nieznanego_operatora_bez_dystansu_ryczalt():
    leg = make_leg(
        LegMode.BUS,
        "A",
        "B",
        _dt(6),
        _dt(6, 10),
        carrier="Jakiś Nieznany Operator",
        distance_km=None,
        extra={"motis_mode": "BUS"},
    )
    priced = pricing.price_bus_leg(leg)
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
    assert priced.price_type == "szacunek"


# --- przesiadki niewykonalne (poniżej absolutnego minimum) są odrzucane, ciasne = ryzykowne -----


def test_przesiadka_2_min_ze_zmiana_dworca_jest_niewykonalna():
    prev = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8))
    nxt = make_leg(LegMode.BUS, "B2", "C", _dt(8, 2), _dt(9), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning.infeasible is True


def test_przesiadka_ciasna_ale_wykonalna_to_tylko_ryzyko():
    prev = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8))
    nxt = make_leg(LegMode.RAIL, "B2", "C", _dt(8, 15), _dt(9), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None and warning.infeasible is False
    itinerary = scoring.build_itinerary(
        "t",
        [
            _priced(LegMode.RAIL, "A", "B", _dt(6), _dt(8), 10),
            _priced(LegMode.RAIL, "B2", "C", _dt(8, 15), _dt(9), 10, requires_walk=True),
        ],
    )
    assert itinerary.is_risky and not itinerary.is_infeasible


def test_rail_to_flight_45_min_niewykonalne_90_ryzykowne():
    flight = lambda start: make_leg(LegMode.FLIGHT, "X", "Y", start, start + timedelta(hours=2))
    prev = make_leg(LegMode.RAIL, "A", "X", _dt(6), _dt(8))
    assert transfers.check_transfer(prev, flight(_dt(8, 45)), 0).infeasible is True
    w = transfers.check_transfer(prev, flight(_dt(9, 30)), 0)
    assert w is not None and w.infeasible is False


def _itinerary_z_ryzykiem(name, price_pln, duration_min, num_transfers, num_risky):
    from routing.model import Itinerary, TransferWarning

    warnings = [TransferWarning(0, 5, 10, "ciasna przesiadka") for _ in range(num_risky)]
    return Itinerary(
        variant_name=name,
        legs=[],
        total_price_pln=price_pln,
        total_duration_min=duration_min,
        num_transfers=num_transfers,
        transfer_warnings=warnings,
    )


def test_pick_recommendations_bezpieczna_pomija_ryzykowne_gdy_jest_bezpieczna_alternatywa():
    tania_ryzykowna = _itinerary_z_ryzykiem("ryzykowna", 50, 400, 1, num_risky=1)
    droga_bezpieczna = _itinerary_z_ryzykiem("bezpieczna", 200, 500, 1, num_risky=0)
    recs = scoring.pick_recommendations([tania_ryzykowna, droga_bezpieczna])
    assert recs["najtansza_bezpieczna"] is droga_bezpieczna
    assert recs["najszybsza_bezpieczna"] is droga_bezpieczna
    assert droga_bezpieczna.is_safe_fallback is False
    # zwykłe kategorie nie filtrują po ryzyku
    assert recs["najtansza"] is tania_ryzykowna


def test_pick_recommendations_bezpieczna_ma_fallback_gdy_wszystko_ryzykowne():
    mniej_ryzykowna = _itinerary_z_ryzykiem("mniej ryzykowna", 100, 300, 1, num_risky=1)
    bardziej_ryzykowna = _itinerary_z_ryzykiem("bardziej ryzykowna", 90, 250, 2, num_risky=2)
    recs = scoring.pick_recommendations([mniej_ryzykowna, bardziej_ryzykowna])
    assert recs["najtansza_bezpieczna"] is mniej_ryzykowna
    assert recs["najszybsza_bezpieczna"] is mniej_ryzykowna
    assert mniej_ryzykowna.is_safe_fallback is True


def test_pick_recommendations_pomija_niewykonalne():
    from routing.model import TransferWarning

    impossible = _itinerary("niewykonalna", 1, 1, 0)
    impossible.transfer_warnings = [TransferWarning(0, 2, 8, "x", infeasible=True)]
    ok = _itinerary("ok", 100, 300, 2)
    recs = scoring.pick_recommendations([impossible, ok])
    assert all(r is ok for r in recs.values())


def test_rail_only_odrzuca_warianty_z_niewykonalna_przesiadka(monkeypatch):
    request = variants.RouteRequest("a", "b", "A", "B", "2026-09-28")
    bad = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=100),
        make_leg(
            LegMode.RAIL,
            "B2",
            "C",
            _dt(8, 2),
            _dt(9),
            carrier="PKP Intercity",
            distance_km=100,
            requires_walk=True,
        ),
    ]
    good = [
        make_leg(LegMode.RAIL, "A", "C", _dt(6), _dt(10), carrier="PKP Intercity", distance_km=200)
    ]
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [bad, good]
    )
    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1 and result[0].num_transfers == 0


def test_rail_only_domyslnie_zwraca_wszystkie_rozne_warianty(monkeypatch):
    request = variants.RouteRequest("a", "b", "A", "B", "2026-09-28")
    options = [
        [
            make_leg(
                LegMode.RAIL,
                f"A{i}",
                "B",
                _dt(6),
                _dt(8 + i),
                carrier="PKP Intercity",
                distance_km=100,
            )
        ]
        for i in range(4)
    ]
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: options)
    assert len(variants.build_rail_only_variants(request)) == 4


# --- kary w "najlepszy stosunek cena/czas": ryzykowne przesiadki i liczba przewoźników -------


def _scored(price, minutes, risky=0, carriers=("PKP Intercity",)):
    from routing.model import Itinerary, TransferWarning

    legs = [_priced(LegMode.RAIL, "A", "B", _dt(6), _dt(7), 0) for _ in carriers]
    for pl, c in zip(legs, carriers):
        pl.leg.carrier_name = c
    warnings = [TransferWarning(0, 20, 30, "x") for _ in range(risky)]
    return Itinerary("v", legs, price, minutes, len(carriers) - 1, warnings)


def test_kara_za_ryzykowne_przesiadki_zmienia_zwyciezce():
    prosta = _scored(400, 900)  # 26.7 PLN/h
    ryzykowna = _scored(350, 850, risky=3)  # bez kary 24.7 PLN/h (lepsza), z karą gorsza
    assert ryzykowna.price_per_hour < prosta.price_per_hour
    assert ryzykowna.value_score > prosta.value_score
    recs = scoring.pick_recommendations([prosta, ryzykowna])
    assert recs["najlepszy_stosunek_ceny_do_czasu"] is prosta
    assert (
        recs["najtansza"] is ryzykowna and recs["najszybsza"] is ryzykowna
    )  # czyste kryteria bez kar


def test_kara_za_dodatkowych_przewoznikow():
    jeden = _scored(400, 900)
    trzech = _scored(390, 890, carriers=("PKP Intercity", "DB Fernverkehr AG", "Flixbus"))
    assert trzech.num_carriers == 3
    assert jeden.value_score < trzech.value_score


def test_all_itineraries_prosi_motis_o_30_wynikow(monkeypatch):
    seen = {}

    def fake_plan(from_place, to_place, time, max_transfers=4, num_itineraries=None):
        seen["n"] = num_itineraries
        return {"itineraries": []}

    monkeypatch.setattr(motis_client, "plan", fake_plan)
    motis_client.all_itineraries_as_legs("a", "b", "2026-10-05T06:00:00Z")
    assert seen["n"] == 30


def test_plan_leg_candidates_sortuje_wg_czasu_i_limituje(monkeypatch):
    def _walk_leg(to_name, end_time):
        return {
            "mode": "WALK",
            "from": {"name": "A", "lat": 0.0, "lon": 0.0},
            "to": {"name": to_name, "lat": 0.0, "lon": 0.0},
            "startTime": "2026-10-05T06:00:00Z",
            "endTime": end_time,
        }

    def fake_plan(from_place, to_place, time, max_transfers=4, num_itineraries=None):
        return {
            "itineraries": [
                {"duration": 7200, "legs": [_walk_leg("B", "2026-10-05T08:00:00Z")]},
                {"duration": 3600, "legs": [_walk_leg("C", "2026-10-05T07:00:00Z")]},
                {"duration": 5400, "legs": [_walk_leg("D", "2026-10-05T07:30:00Z")]},
            ]
        }

    monkeypatch.setattr(motis_client, "plan", fake_plan)
    candidates = motis_client.plan_leg_candidates(
        "a", "b", "2026-10-05T06:00:00Z", max_candidates=2
    )

    assert len(candidates) == 2
    assert [legs[0].destination_name for legs in candidates] == ["C", "D"]  # 3600s, potem 5400s


# --- Sesja 6: alternatywne węzły przesiadkowe/miasta i dworce ----------------------------


def _flat_price_leg(monkeypatch):
    monkeypatch.setattr(
        variants.pricing,
        "price_leg",
        lambda leg, discounts, currency="PLN": PricedLeg(leg, 10.0, "PLN", "szacunek"),
    )


def test_build_rail_via_stop_variant_spina_dwa_zapytania_przez_wezel(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="lublin",
        destination_stop_id="gelsenkirchen",
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date="2026-09-28",
    )
    via = variants.AlternativeStop("Poznań Główny", "pl_poznan")

    first_legs = [
        make_leg(
            LegMode.RAIL,
            "Lublin",
            "Poznań Główny",
            _dt(6),
            _dt(10),
            carrier="PKP Intercity",
            distance_km=300,
        )
    ]
    second_legs = [
        make_leg(
            LegMode.RAIL,
            "Poznań Główny",
            "Gelsenkirchen",
            _dt(11),
            _dt(18),
            carrier="DB Fernverkehr AG",
            distance_km=500,
        )
    ]

    calls = []

    def fake_plan_leg(origin, destination, time, **kw):
        calls.append((origin, destination, time))
        return first_legs if origin == "lublin" else second_legs

    monkeypatch.setattr(variants.motis_client, "plan_leg", fake_plan_leg)
    _flat_price_leg(monkeypatch)

    itinerary = variants.build_rail_via_stop_variant(request, via)

    assert [(o, d) for o, d, _ in calls] == [
        ("lublin", "pl_poznan"),
        ("pl_poznan", "gelsenkirchen"),
    ]
    assert len(itinerary.legs) == 2
    assert "Poznań Główny" in itinerary.variant_name

    # drugie zapytanie NIE startuje dokładnie od przyjazdu pierwszego odcinka (10:00) — ma bufor
    # przesiadki, żeby nie łapać połączenia na styk kilku minut
    second_query_time = datetime.fromisoformat(calls[1][2].replace("Z", "+00:00"))
    assert second_query_time > first_legs[0].arrive
    assert (
        second_query_time - first_legs[0].arrive
    ).total_seconds() / 60 == transfers.MIN_TRANSFER_MINUTES_WALK

    # przesiadka w węźle pośrednim jest jawnie oznaczona jako wymagająca przejścia (nie wiemy,
    # czy to ten sam peron — to dwa niezależnie zapytane odcinki)
    assert itinerary.legs[1].leg.requires_walk is True


def test_generate_variants_via_hub_stops_dedup_wobec_glownego_zapytania(monkeypatch):
    """Trasa via-hub identyczna z tą, którą MOTIS już zwrócił w głównym zapytaniu, nie
    powinna się zdublować w wyniku."""
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )
    main_legs = [
        make_leg(
            LegMode.RAIL, "A", "Hub", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170
        ),
        make_leg(
            LegMode.RAIL, "Hub", "B", _dt(9), _dt(12), carrier="DB Fernverkehr AG", distance_km=300
        ),
    ]
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [main_legs]
    )

    def fake_plan_leg(origin, destination, time, **kw):
        return [main_legs[0]] if origin == "a" else [main_legs[1]]

    monkeypatch.setattr(variants.motis_client, "plan_leg", fake_plan_leg)
    _flat_price_leg(monkeypatch)

    via = variants.AlternativeStop("Hub", "hub_stop")
    built, skipped = variants.generate_variants(request, via_hub_stops=[via])

    assert len(built) == 1  # sama trasa znaleziona dwiema drogami -> policzona raz
    assert skipped == []


def test_generate_variants_via_hub_dodaje_nowa_trase_gdy_rozna_od_glownej(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )
    main_legs = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)
    ]
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [main_legs]
    )

    via_first = [
        make_leg(
            LegMode.RAIL, "A", "Poznań", _dt(6), _dt(9), carrier="PKP Intercity", distance_km=300
        )
    ]
    via_second = [
        make_leg(
            LegMode.RAIL,
            "Poznań",
            "B",
            _dt(10),
            _dt(16),
            carrier="DB Fernverkehr AG",
            distance_km=500,
        )
    ]

    def fake_plan_leg(origin, destination, time, **kw):
        return via_first if origin == "a" else via_second

    monkeypatch.setattr(variants.motis_client, "plan_leg", fake_plan_leg)
    _flat_price_leg(monkeypatch)

    via = variants.AlternativeStop("Poznań", "poznan_stop")
    built, skipped = variants.generate_variants(request, via_hub_stops=[via])

    assert len(built) == 2  # główna trasa A->B + odrębna trasa przez Poznań
    assert any("Poznań" in i.variant_name for i in built)


def test_generate_variants_via_hub_motis_error_laduje_w_skipped(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-09-28",
    )
    main_legs = [
        make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)
    ]
    monkeypatch.setattr(
        variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [main_legs]
    )
    _flat_price_leg(monkeypatch)

    def raise_motis_error(*a, **kw):
        raise MotisError("brak połączenia przez ten węzeł")

    monkeypatch.setattr(variants.motis_client, "plan_leg", raise_motis_error)

    via = variants.AlternativeStop("Ślepy węzeł", "dead_end")
    built, skipped = variants.generate_variants(request, via_hub_stops=[via])

    assert len(built) == 1  # główna trasa i tak się liczy
    assert len(skipped) == 1
    assert "Ślepy węzeł" in skipped[0].variant_name


def test_generate_variants_alternative_origin_stops_dodaje_i_dedupikuje(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="warszawa_centralna",
        destination_stop_id="b",
        origin_label="Warszawa",
        destination_label="B",
        date="2026-09-28",
    )
    main_legs = [
        make_leg(
            LegMode.RAIL,
            "Warszawa Centralna",
            "B",
            _dt(6),
            _dt(8),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    alt_legs = [
        make_leg(
            LegMode.RAIL,
            "Warszawa Wschodnia",
            "B",
            _dt(6, 30),
            _dt(8, 30),
            carrier="PKP Intercity",
            distance_km=175,
        )
    ]

    def fake_all_itineraries(origin, destination, time):
        return [main_legs] if origin == "warszawa_centralna" else [alt_legs]

    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", fake_all_itineraries)
    _flat_price_leg(monkeypatch)

    alt = variants.AlternativeStop("Warszawa Wschodnia", "warszawa_wschodnia")
    built, skipped = variants.generate_variants(request, alternative_origin_stops=[alt])

    assert len(built) == 2
    assert skipped == []

    # ta sama trasa (sygnatura) z alternatywnego dworca -> zdedup'owana wobec głównej
    built2, _ = variants.generate_variants(
        variants.RouteRequest(
            origin_stop_id="warszawa_centralna",
            destination_stop_id="b",
            origin_label="Warszawa",
            destination_label="B",
            date="2026-09-28",
        ),
        alternative_origin_stops=[
            variants.AlternativeStop("Centralna-duplikat", "warszawa_centralna")
        ],
    )
    assert len(built2) == 1


def test_motis_time_jest_czasem_lokalnym_z_offsetem():
    # 06:00 czasu polskiego w październiku to 04:00 UTC (CEST), nie 06:00Z
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-10-09",
    )
    assert request.motis_time == "2026-10-09T06:00:00+02:00"


def test_build_rail_only_variants_pomija_polaczenia_z_dnia_nastepnego(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-10-09",
    )
    # 2026-10-09 07:00 czasu lokalnego = 05:00 UTC; odjazd 2026-10-10 o 06:30 lokalnie = 04:30 UTC
    same_day = [
        make_leg(
            LegMode.RAIL,
            "A",
            "B",
            datetime(2026, 10, 9, 5, 0, tzinfo=UTC),
            datetime(2026, 10, 9, 9, 0, tzinfo=UTC),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    next_day = [
        make_leg(
            LegMode.RAIL,
            "A",
            "B",
            datetime(2026, 10, 10, 4, 30, tzinfo=UTC),
            datetime(2026, 10, 10, 6, 0, tzinfo=UTC),
            carrier="PKP Intercity",
            distance_km=170,
        )
    ]
    monkeypatch.setattr(
        variants.motis_client,
        "all_itineraries_as_legs",
        lambda *a, **kw: [next_day, same_day],
    )

    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1
    assert result[0].legs[0].leg.depart.astimezone(variants.LOCAL_TIMEZONE).day == 9


def test_build_rail_only_variants_nocny_przejazd_z_dnia_wyszukiwania_zostaje(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="b",
        origin_label="A",
        destination_label="B",
        date="2026-10-09",
    )
    # odjazd 23:30 lokalnie 2026-10-09 (21:30 UTC), przyjazd następnego dnia — to nadal dzień wyszukiwania
    night = [
        make_leg(
            LegMode.RAIL,
            "A",
            "B",
            datetime(2026, 10, 9, 21, 30, tzinfo=UTC),
            datetime(2026, 10, 10, 5, 0, tzinfo=UTC),
            carrier="PKP Intercity",
            distance_km=500,
        )
    ]
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [night])

    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1


def test_bus_miejski_zwraca_carrier_i_breakdown_dla_ui():
    from fares.model import Carrier, DiscountProfile

    leg = make_leg(
        LegMode.BUS, "Warszawa Centrum", "Warszawa Wola", _dt(6), _dt(6, 20), carrier="ZTM Warszawa"
    )
    priced = pricing.price_bus_leg(leg, DiscountProfile(ztm_warszawa_bezplatny=True))
    assert priced.carrier is Carrier.ZTM_WARSZAWA
    assert priced.amount == 0.0
    assert priced.breakdown["typ_biletu"].startswith("bezpłatny")
