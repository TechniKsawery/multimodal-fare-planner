"""Kilometry po torach z odpowiedzi MOTIS (geometria legu / przystanki pośrednie) dla taryfy
POLREGIO/KD/KŚ. Fixture tests/fixtures/motis_kd_wroclaw_klodzko.json jest SYNTETYCZNY (zgodny ze
schematem MOTIS API v6, przybliżone współrzędne): MOTIS nie działa w środowisku testów."""

import copy
import json
from pathlib import Path

import pytest

from fares.model import DiscountProfile, PriceType
from routing import motis_client, pricing

RAW = json.loads(
    (Path(__file__).parent / "fixtures" / "motis_kd_wroclaw_klodzko.json").read_text(
        encoding="utf-8"
    )
)
WROCLAW = (51.0989, 17.0362)
KLODZKO = (50.4337, 16.6537)


def _raw(*, geometry=True, stops=True):
    raw = copy.deepcopy(RAW)
    if not geometry:
        del raw["legs"][0]["legGeometry"]
    if not stops:
        del raw["legs"][0]["intermediateStops"]
    return raw


def _encode(points, precision=6):
    factor = 10**precision
    out, last_lat, last_lon = [], 0, 0
    for lat, lon in points:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - last_lat, ilon - last_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        last_lat, last_lon = ilat, ilon
    return "".join(out)


def _price(raw, discounts=None):
    (leg,) = motis_client.itinerary_to_legs(raw)
    return leg, pricing.price_rail_leg(leg, discounts or DiscountProfile())


# --- dekoder polilinii -------------------------------------------------------------------


def test_dekoder_polilinii_odtwarza_punkty_z_precyzja_6_i_7():
    punkty = [(51.0989, 17.0362), (50.7807, 17.0669), (-33.865143, 151.2099)]
    assert motis_client.decode_polyline(_encode(punkty), 6) == punkty
    assert motis_client.decode_polyline(_encode(punkty[:2], 7), 7) == punkty[:2]


# --- track_distance_km -------------------------------------------------------------------


def test_odpowiedz_motis_nie_niesie_shape_dist_traveled():
    # MOTIS API v6 nie wystawia shape_dist_traveled; fixture też go nie ma i nie jest potrzebny
    assert "shape_dist_traveled" not in json.dumps(RAW)


def test_geometria_i_przystanki_daja_wiecej_niz_linia_prosta():
    straight = motis_client.haversine_km(*WROCLAW, *KLODZKO)
    assert straight == pytest.approx(78.7, abs=0.1)
    km, label = motis_client.track_distance_km(RAW["legs"][0])
    assert km > straight + 5
    assert (
        label == motis_client.TRACK_KM_GEOMETRY
    )  # gęstszy kształt jest dłuższy od cięciw przystanków


def test_same_przystanki_posrednie_jako_zrodlo():
    km, label = motis_client.track_distance_km(_raw(geometry=False)["legs"][0])
    assert km == pytest.approx(83.9, abs=0.1)
    assert label == motis_client.TRACK_KM_STOPS


def test_sama_geometria_jako_zrodlo():
    km, label = motis_client.track_distance_km(_raw(stops=False)["legs"][0])
    assert km == pytest.approx(84.3, abs=0.1)
    assert label == motis_client.TRACK_KM_GEOMETRY


def test_brak_geometrii_i_przystankow_to_brak_km_po_torach():
    assert motis_client.track_distance_km(_raw(geometry=False, stops=False)["legs"][0]) is None


def test_pusta_polilinia_i_dwa_punkty_nie_sa_ksztaltem():
    raw = _raw(stops=False)
    raw["legs"][0]["legGeometry"] = {
        "points": "",
        "precision": 6,
        "length": 0,
    }  # detailedLegs=false
    assert motis_client.track_distance_km(raw["legs"][0]) is None
    raw["legs"][0]["legGeometry"] = {
        "points": _encode([WROCLAW, KLODZKO]),
        "precision": 6,
        "length": 2,
    }
    assert motis_client.track_distance_km(raw["legs"][0]) is None  # zwykła prosta, nic nowego


def test_geometria_niepasujaca_do_stacji_koncowych_jest_odrzucana():
    raw = _raw(stops=False)
    inny = [(52.2297, 21.0122), (52.4, 21.2), (52.5, 21.5)]
    raw["legs"][0]["legGeometry"]["points"] = _encode(inny)
    assert motis_client.track_distance_km(raw["legs"][0]) is None


def test_przystanek_posredni_bez_wspolrzednych_uniewaznia_te_sciezke():
    raw = _raw(geometry=False)
    del raw["legs"][0]["intermediateStops"][1]["lat"]
    assert motis_client.track_distance_km(raw["legs"][0]) is None


# --- itinerary_to_legs + wycena ----------------------------------------------------------


def test_leg_dostaje_km_po_torach_a_distance_km_zostaje_linia_prosta():
    (leg,) = motis_client.itinerary_to_legs(RAW)
    assert leg.distance_km == pytest.approx(78.7, abs=0.1)
    assert leg.extra["distance_along_track_km"] > 83
    assert leg.extra["distance_along_track_source"] == motis_client.TRACK_KM_GEOMETRY


def test_odcinek_pieszy_nie_dostaje_km_po_torach():
    raw = {
        "legs": [
            {
                "mode": "WALK",
                "from": {"name": "A", "lat": 51.0, "lon": 17.0},
                "to": {"name": "B", "lat": 51.001, "lon": 17.0},
                "startTime": "2026-10-20T08:00:00Z",
                "endTime": "2026-10-20T08:02:00Z",
            }
        ]
    }
    (leg,) = motis_client.itinerary_to_legs(raw)
    assert "distance_along_track_km" not in leg.extra


def test_wroclaw_klodzko_pasmo_z_torow_nie_z_linii_prostej():
    leg, priced = _price(RAW)
    # linia prosta 78,7 km -> pasmo do 80 km (25,90 zł); po torach ~84 km -> pasmo do 90 km
    assert priced.amount == 27.90
    assert priced.breakdown["pasmo_do_km"] == 90
    assert priced.price_type == PriceType.OFFICIAL.value
    assert priced.breakdown["odleglosc_taryfowa"] == "po torach"
    assert priced.breakdown["zrodlo_km"] == motis_client.TRACK_KM_GEOMETRY
    assert motis_client.TRACK_KM_GEOMETRY in priced.notes
    assert "linii prostej" not in priced.notes


def test_wycena_z_przystankow_pokazuje_zrodlo_km():
    _, priced = _price(_raw(geometry=False))
    assert priced.amount == 27.90
    assert priced.price_type == PriceType.OFFICIAL.value
    assert priced.breakdown["zrodlo_km"] == motis_client.TRACK_KM_STOPS


def test_bez_danych_o_torze_zostaje_linia_prosta_i_szacunek():
    leg, priced = _price(_raw(geometry=False, stops=False))
    assert "distance_along_track_km" not in leg.extra
    assert priced.amount == 25.90  # pasmo z linii prostej, bez żadnego współczynnika
    assert priced.price_type == PriceType.ESTIMATE.value
    assert priced.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert "zrodlo_km" not in priced.breakdown
    assert "linii prostej" in priced.notes


def test_ulga_nadal_robi_z_ceny_szacunek_mimo_km_po_torach():
    _, priced = _price(RAW, DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"))
    assert priced.breakdown["odleglosc_taryfowa"] == "po torach"
    assert priced.price_type == PriceType.ESTIMATE.value
    assert priced.breakdown["price_verified"] is False


def test_km_po_torach_nie_zmienia_wyceny_innych_przewoznikow():
    raw = _raw()
    raw["legs"][0]["agencyName"] = "PKP Intercity"
    (leg,) = motis_client.itinerary_to_legs(raw)
    segment_km = leg.distance_km
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert "zrodlo_km" not in priced.breakdown
    assert priced.breakdown.get("odleglosc_taryfowa") is None
    assert segment_km == pytest.approx(78.7, abs=0.1)
