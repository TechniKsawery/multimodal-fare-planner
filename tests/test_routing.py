from datetime import datetime, timedelta, timezone

import pytest

from fares.model import Carrier, DiscountProfile
from flights.travelpayouts import TravelpayoutsError
from routing import motis_client, pricing, scoring, transfers, variants
from routing.model import Leg, LegMode, PricedLeg
from routing.motis_client import MotisError


def _dt(hour, minute=0, day=28):
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


def make_leg(mode, origin, destination, depart, arrive, *, carrier="", requires_walk=True,
             distance_km=100.0, extra=None):
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
            "from": {"name": "Lublin Główny", "stopId": "pl_50500_RAIL_1_52", "lat": 51.23, "lon": 22.57,
                      "departure": "2026-09-28T06:25:00Z"},
            "to": {"name": "Warszawa Wschodnia", "stopId": "pl_38653_RAIL_1_10", "lat": 52.25, "lon": 21.05,
                    "arrival": "2026-09-28T08:11:00Z"},
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
            "from": {"name": "Warszawa Wschodnia", "stopId": "pl_38653_RAIL_1_10", "lat": 52.25, "lon": 21.05,
                      "departure": "2026-09-28T08:49:00Z"},
            "to": {"name": "Berlin-Lichtenberg", "stopId": "pl_140533_FALLBACK", "lat": 52.51, "lon": 13.5,
                    "arrival": "2026-09-28T14:03:00Z"},
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
    assert legs[1].requires_walk is True   # poprzedzony legiem WALK w surowych danych
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
    nxt = make_leg(LegMode.RAIL, "B", "C", _dt(8, 25), _dt(10), requires_walk=True)
    warning = transfers.check_transfer(prev, nxt, 0)
    assert warning is not None  # 25 min < 30 min (wymaga przejścia)


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
        make_leg(LegMode.RAIL, "B", "C", _dt(8, 5), _dt(10), requires_walk=False),   # zbyt krótko
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


def test_price_rail_leg_nieznany_przewoznik_uzywa_fallbacku():
    leg = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="Coś Nieznanego", distance_km=100)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_type == "szacunek"
    assert priced.amount == pytest.approx(100 * pricing.GENERIC_FALLBACK_PLN_PER_KM)
    assert priced.currency == "PLN"


def test_price_rail_leg_pkp_woła_fares(monkeypatch):
    leg = make_leg(LegMode.RAIL, "Lublin", "Warszawa Wschodnia", _dt(6), _dt(8),
                    carrier="PKP Intercity", distance_km=170)

    calls = {}

    def fake_estimate(segment):
        calls["segment"] = segment
        from fares.model import PriceEstimate, PriceType
        return PriceEstimate(
            carrier=segment.carrier, amount=49.0, currency="PLN",
            price_type=PriceType.OFFICIAL, breakdown={}, notes="test",
        )

    monkeypatch.setattr(pricing, "fares_estimate_price", fake_estimate)
    priced = pricing.price_rail_leg(leg, DiscountProfile())

    assert priced.amount == 49.0
    assert calls["segment"].carrier is Carrier.PKP_INTERCITY
    assert calls["segment"].distance_km == 170


def test_price_rail_leg_gdy_fares_odrzuci_segment_uzywa_fallbacku(monkeypatch):
    leg = make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=100)

    def fake_estimate(segment):
        raise ValueError("nieznany kod ulgi")

    monkeypatch.setattr(pricing, "fares_estimate_price", fake_estimate)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_type == "szacunek"
    assert "błąd" in priced.notes


def test_price_flight_leg_woła_flights(monkeypatch):
    leg = make_leg(LegMode.FLIGHT, "WAW", "DTM", _dt(6), _dt(8),
                    extra={"origin_iata": "WAW", "destination_iata": "DTM", "depart_date": "2026-11-15"})

    def fake_estimate(segment):
        from flights.model import PriceEstimate, PriceType
        return PriceEstimate(
            origin="WAW", destination="DTM", amount=350.0, currency="PLN",
            price_type=PriceType.ESTIMATE, breakdown={}, notes="test",
        )

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    priced = pricing.price_flight_leg(leg)
    assert priced.amount == 350.0
    assert priced.currency == "PLN"


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
    assert itinerary.total_price_pln == pytest.approx(10.0 * PLACEHOLDER_RATES_TO_PLN["EUR"])


def test_build_itinerary_bez_legow_podnosi_blad():
    with pytest.raises(ValueError):
        scoring.build_itinerary("Test", [])


def _itinerary(name, price_pln, duration_min, num_transfers):
    from routing.model import Itinerary
    return Itinerary(
        variant_name=name, legs=[], total_price_pln=price_pln,
        total_duration_min=duration_min, num_transfers=num_transfers,
    )


def test_pick_recommendations_wybiera_cztery_kategorie():
    cheap = _itinerary("tania", 50, 60, 3)             # 50 PLN/h
    fast = _itinerary("szybka", 200, 30, 1)             # 400 PLN/h
    few_transfers = _itinerary("bez przesiadek", 300, 500, 0)  # 36 PLN/h
    balanced = _itinerary("zbalansowana", 150, 300, 2)  # 30 PLN/h, najniższe

    recs = scoring.pick_recommendations([cheap, fast, few_transfers, balanced])

    assert recs["najtansza"] is cheap
    assert recs["najszybsza"] is fast
    assert recs["najmniej_przesiadek"] is few_transfers
    assert recs["najlepszy_stosunek_ceny_do_czasu"] is balanced


def test_pick_recommendations_pusta_lista_podnosi_blad():
    with pytest.raises(ValueError):
        scoring.pick_recommendations([])


# --- variants: generowanie wariantów, w tym pomijanie na błędach -------------------------

def test_generate_variants_pomija_lot_bez_tokena(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="a", destination_stop_id="b",
        origin_label="A", destination_label="B", date="2026-11-15",
    )

    rail_legs = [make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)]
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [rail_legs])

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
        origin_stop_id="a", destination_stop_id="b",
        origin_label="A", destination_label="B", date="2026-11-15",
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
        origin_stop_id="a", destination_stop_id="b",
        origin_label="A", destination_label="B", date="2026-11-15",
    )
    legs_a = [make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=170)]
    legs_b = [make_leg(LegMode.RAIL, "A", "B", _dt(7), _dt(9), carrier="PKP Intercity", distance_km=170)]

    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs",
                         lambda *a, **kw: [legs_a, legs_b])

    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1  # ta sama sygnatura trasy (A->B) -> zliczona raz


def test_build_rail_flight_rail_variant_laczy_trzy_odcinki(monkeypatch):
    request = variants.RouteRequest(
        origin_stop_id="lublin", destination_stop_id="gelsenkirchen",
        origin_label="Lublin", destination_label="Gelsenkirchen", date="2026-11-15",
    )
    hub = variants.HubConfig("Warszawa-Dortmund", "WAW", "DTM", "waw_airport", "dortmund_hbf")

    access_legs = [make_leg(LegMode.RAIL, "Lublin", "Warszawa Lotnisko Chopina", _dt(6), _dt(8),
                             carrier="PKP Intercity", distance_km=170)]
    onward_legs = [make_leg(LegMode.RAIL, "Dortmund Hbf", "Gelsenkirchen Hbf", _dt(16), _dt(16, 30),
                             carrier="DB Regio", distance_km=25)]

    calls = []

    def fake_plan_leg(origin, destination, time, **kw):
        calls.append((origin, destination))
        return access_legs if origin == "lublin" else onward_legs

    monkeypatch.setattr(variants.motis_client, "plan_leg", fake_plan_leg)
    monkeypatch.setattr(variants.pricing, "price_leg",
                         lambda leg, discounts, currency="PLN": PricedLeg(leg, 10.0, "PLN", "szacunek"))

    itinerary = variants.build_rail_flight_rail_variant(request, hub)

    assert len(itinerary.legs) == 3
    assert itinerary.legs[1].leg.mode is LegMode.FLIGHT
    assert calls[0] == ("lublin", "waw_airport")
    assert calls[1] == ("dortmund_hbf", "gelsenkirchen")
