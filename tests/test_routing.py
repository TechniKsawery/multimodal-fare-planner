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


# --- adresy: odcinki piesze (dojście z adresu / do adresu), autobus, geocoding ---------------

ADDRESS_ITINERARY = {
    "legs": [
        {"mode": "WALK", "from": {"name": "START", "lat": 51.2477, "lon": 22.5592},
         "to": {"name": "Ogród Saski", "stopId": "ztml_1001", "lat": 51.2474, "lon": 22.5514},
         "startTime": "2026-10-05T07:16:00Z", "endTime": "2026-10-05T07:24:00Z", "distance": 565.0},
        {"mode": "BUS", "from": {"name": "Ogród Saski", "stopId": "ztml_1001", "lat": 51.2474, "lon": 22.5514},
         "to": {"name": "Dworzec Lublin", "stopId": "ztml_2", "lat": 51.2318, "lon": 22.5692},
         "startTime": "2026-10-05T07:24:00Z", "endTime": "2026-10-05T07:32:00Z", "agencyName": "ZDiTM Lublin"},
        {"mode": "WALK", "from": {"name": "Dworzec Lublin", "lat": 51.2318, "lon": 22.5692},
         "to": {"name": "Lublin Główny", "lat": 51.2313, "lon": 22.5692},
         "startTime": "2026-10-05T07:32:00Z", "endTime": "2026-10-05T07:34:00Z"},
        {"mode": "REGIONAL_RAIL", "from": {"name": "Lublin Główny", "stopId": "pl_50500", "lat": 51.2313, "lon": 22.5692},
         "to": {"name": "Gelsenkirchen Hbf", "stopId": "defv_344028", "lat": 51.5049, "lon": 7.1022},
         "startTime": "2026-10-05T08:00:00Z", "endTime": "2026-10-05T20:00:00Z", "agencyName": "PKP Intercity"},
        {"mode": "WALK", "from": {"name": "Gelsenkirchen Hbf", "lat": 51.5049, "lon": 7.1022},
         "to": {"name": "END", "lat": 51.5060, "lon": 7.1016},
         "startTime": "2026-10-05T20:00:00Z", "endTime": "2026-10-05T20:04:00Z", "distance": 246.0},
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
    assert len(itinerary.transfer_warnings) == 1  # autobus 07:32 -> pociąg 08:00 = 28 min < 30


def test_przesiadka_autobus_pociag_za_krotka_jest_ryzykowna():
    raw = {"legs": [dict(ADDRESS_ITINERARY["legs"][i]) for i in range(5)]}
    raw["legs"][3] = {**raw["legs"][3], "startTime": "2026-10-05T07:36:00Z"}
    legs = motis_client.itinerary_to_legs(raw)
    warnings = transfers.check_all_transfers(legs)
    assert len(warnings) == 1
    assert warnings[0].after_leg_index == 1  # indeks oryginalny (autobus), nie licząc walk


def test_wycena_pieszo_zero_i_autobus_ryczalt():
    legs = motis_client.itinerary_to_legs(ADDRESS_ITINERARY)
    assert pricing.price_leg(legs[0], DiscountProfile()).amount == 0
    assert pricing.price_leg(legs[1], DiscountProfile()).amount == pricing.LOCAL_BUS_FLAT_PLN


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


def test_request_from_addresses_uzywa_wspolrzednych(monkeypatch):
    coords = {"a": (51.0, 22.0, "Adres A"), "b": (51.5, 7.1, "Adres B")}
    monkeypatch.setattr(variants.motis_client, "geocode", lambda text: coords[text])
    request = variants.request_from_addresses("a", "b", "2026-10-05")
    assert request.origin_stop_id == "51.0,22.0"
    assert request.destination_stop_id == "51.5,7.1"
    assert request.origin_label == "Adres A"


def test_tramwaj_i_metro_to_transport_lokalny_a_pociag_to_kolej():
    def raw(mode):
        return {"legs": [{"mode": mode, "from": {"name": "A", "lat": 51.0, "lon": 7.0},
                          "to": {"name": "B", "lat": 51.1, "lon": 7.0},
                          "startTime": "2026-10-05T07:00:00Z", "endTime": "2026-10-05T07:10:00Z"}]}
    assert motis_client.itinerary_to_legs(raw("TRAM"))[0].mode is LegMode.BUS
    assert motis_client.itinerary_to_legs(raw("SUBWAY"))[0].mode is LegMode.BUS
    assert motis_client.itinerary_to_legs(raw("REGIONAL_RAIL"))[0].mode is LegMode.RAIL
    assert motis_client.itinerary_to_legs(raw("HIGHSPEED_RAIL"))[0].mode is LegMode.RAIL


def test_flixbus_wyceniany_za_km_a_autobus_miejski_ryczaltem():
    city = make_leg(LegMode.BUS, "A", "B", _dt(6), _dt(7), carrier="ZDiTM Lublin", distance_km=5,
                    extra={"motis_mode": "BUS"})
    coach = make_leg(LegMode.BUS, "A", "B", _dt(6), _dt(12), carrier="Flixbus", distance_km=500,
                     extra={"motis_mode": "BUS"})
    assert pricing.price_bus_leg(city).amount == pricing.LOCAL_BUS_FLAT_PLN
    assert pricing.price_bus_leg(coach).amount == pytest.approx(500 * pricing.GENERIC_FALLBACK_PLN_PER_KM)


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
    itinerary = scoring.build_itinerary("t", [
        _priced(LegMode.RAIL, "A", "B", _dt(6), _dt(8), 10),
        _priced(LegMode.RAIL, "B2", "C", _dt(8, 15), _dt(9), 10, requires_walk=True),
    ])
    assert itinerary.is_risky and not itinerary.is_infeasible


def test_rail_to_flight_45_min_niewykonalne_90_ryzykowne():
    flight = lambda start: make_leg(LegMode.FLIGHT, "X", "Y", start, start + timedelta(hours=2))
    prev = make_leg(LegMode.RAIL, "A", "X", _dt(6), _dt(8))
    assert transfers.check_transfer(prev, flight(_dt(8, 45)), 0).infeasible is True
    w = transfers.check_transfer(prev, flight(_dt(9, 30)), 0)
    assert w is not None and w.infeasible is False


def test_pick_recommendations_pomija_niewykonalne():
    from routing.model import TransferWarning
    impossible = _itinerary("niewykonalna", 1, 1, 0)
    impossible.transfer_warnings = [TransferWarning(0, 2, 8, "x", infeasible=True)]
    ok = _itinerary("ok", 100, 300, 2)
    recs = scoring.pick_recommendations([impossible, ok])
    assert all(r is ok for r in recs.values())


def test_rail_only_odrzuca_warianty_z_niewykonalna_przesiadka(monkeypatch):
    request = variants.RouteRequest("a", "b", "A", "B", "2026-10-05")
    bad = [make_leg(LegMode.RAIL, "A", "B", _dt(6), _dt(8), carrier="PKP Intercity", distance_km=100),
           make_leg(LegMode.RAIL, "B2", "C", _dt(8, 2), _dt(9), carrier="PKP Intercity", distance_km=100,
                    requires_walk=True)]
    good = [make_leg(LegMode.RAIL, "A", "C", _dt(6), _dt(10), carrier="PKP Intercity", distance_km=200)]
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: [bad, good])
    result = variants.build_rail_only_variants(request, max_variants=5)
    assert len(result) == 1 and result[0].num_transfers == 0


def test_rail_only_domyslnie_zwraca_wszystkie_rozne_warianty(monkeypatch):
    request = variants.RouteRequest("a", "b", "A", "B", "2026-10-05")
    options = [
        [make_leg(LegMode.RAIL, f"A{i}", "B", _dt(6), _dt(8 + i), carrier="PKP Intercity", distance_km=100)]
        for i in range(4)
    ]
    monkeypatch.setattr(variants.motis_client, "all_itineraries_as_legs", lambda *a, **kw: options)
    assert len(variants.build_rail_only_variants(request)) == 4
