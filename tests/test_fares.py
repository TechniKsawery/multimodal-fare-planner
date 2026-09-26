import pytest

from fares import PriceType, estimate_price
from fares.model import Carrier, DiscountProfile, Segment


def test_pkp_bez_ulgi():
    seg = Segment(Carrier.PKP_INTERCITY, "Lublin", "Warszawa Wschodnia", distance_km=170)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == 50
    assert result.currency == "PLN"


def test_pkp_z_ulga_studencka_51():
    seg = Segment(
        Carrier.PKP_INTERCITY,
        "Lublin",
        "Warszawa Wschodnia",
        distance_km=170,
        discounts=DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(50 * 0.49, abs=0.01)


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
    assert result.amount == 148
    assert result.currency == "EUR"
    assert result.price_type is PriceType.ESTIMATE


def test_db_flexpreis_z_bahncard25():
    seg = Segment(
        Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550,
        discounts=DiscountProfile(bahncard="25"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(148 * 0.75)


@pytest.mark.parametrize("km,lo,hi", [(190, 42.30, 114.20), (285, 80, 100), (373, 106, 127), (570, 99.90, 185.10)])
def test_db_flexpreis_miesci_sie_w_realnych_przedzialach(km, lo, hi):
    seg = Segment(Carrier.DB, "A", "B", distance_km=km)
    assert lo <= estimate_price(seg).amount <= hi
