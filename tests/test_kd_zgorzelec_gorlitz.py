"""Pociąg KD Zgorzelec - Görlitz: 0 zł, oficjalna taryfa (potwierdzone na stronie KD)."""

from datetime import datetime, timedelta

import pytest

from fares import kd_zgorzelec_gorlitz
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing
from routing.model import Leg, LegMode

ZGORZELEC = (51.1500, 15.0200)
GOERLITZ = (51.1468, 14.9757)
WROCLAW_GLOWNY = (51.0987, 17.0366)


def _leg(origin, destination, origin_xy, destination_xy, *, carrier, mode=LegMode.RAIL, extra=None):
    extra = dict(extra or {})
    extra.update(
        origin_lat=origin_xy[0],
        origin_lon=origin_xy[1],
        destination_lat=destination_xy[0],
        destination_lon=destination_xy[1],
    )
    depart = datetime(2026, 10, 20, 8, 0)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=10),
        carrier_name=carrier,
        distance_km=motis_client.haversine_km(*origin_xy, *destination_xy),
        extra=extra,
    )


@pytest.mark.parametrize(
    "a, b, axy, bxy",
    [
        ("Zgorzelec", "Görlitz", ZGORZELEC, GOERLITZ),
        ("Görlitz", "Zgorzelec", GOERLITZ, ZGORZELEC),
    ],
)
def test_pociag_kd_zgorzelec_gorlitz_jest_za_0_zl_oficjalnie(a, b, axy, bxy):
    priced = pricing.price_rail_leg(
        _leg(a, b, axy, bxy, carrier="Koleje Dolnośląskie"), DiscountProfile()
    )
    assert priced.carrier is Carrier.KD_ZGORZELEC_GORLITZ
    assert (priced.amount, priced.currency) == (0.0, "PLN")
    assert priced.price_type == "oficjalna_taryfa"
    assert priced.breakdown["price_verified"] is True
    assert priced.breakdown["zrodlo_url"].endswith("/oferty-przygraniczne/")


def test_status_wg_gemini_to_niepotwierdzony_szacunek(monkeypatch):
    tabela = dict(kd_zgorzelec_gorlitz._TABLE)
    tabela["weryfikacja"] = {
        **tabela["weryfikacja"],
        "status": kd_zgorzelec_gorlitz.STATUS_WERYFIKACJI,
    }
    monkeypatch.setattr(kd_zgorzelec_gorlitz, "_TABLE", tabela)
    result = kd_zgorzelec_gorlitz.estimate(
        Segment(Carrier.KD_ZGORZELEC_GORLITZ, "Zgorzelec", "Görlitz")
    )
    assert (result.amount, result.price_type) == (0.0, PriceType.ESTIMATE)
    assert result.breakdown["price_verified"] is False


def test_autobus_zastepczy_kd_nie_dostaje_0_zl():
    leg = _leg(
        "Zgorzelec",
        "Görlitz",
        ZGORZELEC,
        GOERLITZ,
        carrier="Koleje Dolnośląskie",
        extra={"motis_mode": "BUS"},
    )
    assert pricing.is_kd_zgorzelec_gorlitz(leg) is False


def test_dluzszy_przejazd_i_inny_przewoznik_nie_dostaja_0_zl():
    dlugi = _leg(
        "Wrocław Główny", "Görlitz", WROCLAW_GLOWNY, GOERLITZ, carrier="Koleje Dolnośląskie"
    )
    inny = _leg("Zgorzelec", "Görlitz", ZGORZELEC, GOERLITZ, carrier="Polregio")
    assert pricing.is_kd_zgorzelec_gorlitz(dlugi) is False
    assert pricing.is_kd_zgorzelec_gorlitz(inny) is False
    priced = pricing.price_rail_leg(dlugi, DiscountProfile())
    assert priced.carrier is not Carrier.KD_ZGORZELEC_GORLITZ
    assert priced.amount > 0
