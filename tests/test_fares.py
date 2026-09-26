import pytest

from fares import PriceType, estimate_price
from fares.model import Carrier, DiscountProfile, Segment


def test_pkp_bez_ulgi():
    seg = Segment(Carrier.PKP_INTERCITY, "Lublin", "Warszawa Wschodnia", distance_km=170)
    result = estimate_price(seg)
    assert result.price_type is PriceType.ESTIMATE
    assert result.amount == 49
    assert result.currency == "PLN"


def test_pkp_z_ulga_37():
    seg = Segment(
        Carrier.PKP_INTERCITY,
        "Lublin",
        "Warszawa Wschodnia",
        distance_km=170,
        discounts=DiscountProfile(pkp_ulga_kod="ulga_37"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(49 * 0.63, abs=0.01)


def test_pkp_nieznana_ulga():
    seg = Segment(
        Carrier.PKP_INTERCITY, "A", "B", distance_km=100,
        discounts=DiscountProfile(pkp_ulga_kod="nieistniejaca"),
    )
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_db_flexpreis_bez_bahncard():
    seg = Segment(Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550)
    result = estimate_price(seg)
    assert result.amount == 110
    assert result.currency == "EUR"


def test_db_flexpreis_z_bahncard25():
    seg = Segment(
        Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550,
        discounts=DiscountProfile(bahncard="25"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(110 * 0.75)


def test_vrr_znana_relacja():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Duisburg Hbf")
    result = estimate_price(seg)
    assert result.amount == 8.80
    assert result.price_type is PriceType.ESTIMATE


def test_vrr_relacja_odwrotna_ten_sam_wynik():
    a = estimate_price(Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf"))
    b = estimate_price(Segment(Carrier.VRR, "Essen Hbf", "Gelsenkirchen Hbf"))
    assert a.amount == b.amount


def test_vrr_nieznana_relacja():
    seg = Segment(Carrier.VRR, "Nieznane Miasto", "Inne Miasto")
    with pytest.raises(ValueError):
        estimate_price(seg)
