from datetime import datetime, timedelta

import pytest

from routing.card_suggestions import (
    db_flexpreis_upper_bound_total,
    suggest_bahncard_for_itinerary,
)
from routing.model import Itinerary, Leg, LegMode, PricedLeg


def _db_leg(distance_km, amount):
    depart = datetime(2026, 10, 1, 8, 0)
    leg = Leg(
        mode=LegMode.RAIL,
        origin_name="A",
        destination_name="B",
        depart=depart,
        arrive=depart + timedelta(hours=2),
        carrier_name="DB Fernverkehr AG",
        distance_km=distance_km,
    )
    return PricedLeg(leg=leg, amount=amount, currency="EUR", price_type="szacunek")


def _itinerary(legs):
    return Itinerary(
        variant_name="test",
        legs=legs,
        total_price_pln=sum(pl.amount for pl in legs),
        total_duration_min=240,
        num_transfers=len(legs) - 1,
    )


def test_dwa_oddzielne_bilety_db_licza_sie_osobno_nie_jako_suma_dystansow():
    # zgłoszenie usera: trasa Berlin->Frankfurt (ok. 450 km, bilet 131 EUR bez karty) +
    # Frankfurt->Gelsenkirchen (ok. 180 km, bilet 80 EUR bez karty) to DWA oddzielne bilety
    # DB (przesiadka we Frankfurcie), a suma ich cen (131 + 80 = 211 EUR) nie zgadzała się z
    # sugestią BahnCard, która banowała SUMĘ dystansów (ok. 630 km -> płaskie pasmo 182 EUR).
    it = _itinerary([_db_leg(450, 98.25), _db_leg(180, 60.0)])
    assert db_flexpreis_upper_bound_total(it) == pytest.approx(131 + 80, abs=0.01)


def test_sugestia_bahncard_dla_dwoch_biletow_uzywa_sumy_biletow():
    it = _itinerary([_db_leg(450, 98.25), _db_leg(180, 60.0)])
    suggestions = suggest_bahncard_for_itinerary(it, age=15)
    jugend = next(r for r in suggestions if r.variant_key == "jugend_bc25_6_18")
    # 211 EUR (suma dwóch biletów), nie 182 EUR (błędne bandowanie sumy dystansów)
    assert jugend.cena_biletu_bez_karty == pytest.approx(211.0, abs=0.01)
    assert jugend.cena_biletu_z_karta == pytest.approx(211.0 * 0.75, abs=0.01)
