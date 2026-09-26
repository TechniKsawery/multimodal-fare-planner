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
    assert result.amount == 150
    assert result.currency == "EUR"
    assert result.price_type is PriceType.ESTIMATE


def test_db_flexpreis_z_bahncard25():
    seg = Segment(
        Carrier.DB, "Berlin Hbf", "Gelsenkirchen Hbf", distance_km=550,
        discounts=DiscountProfile(bahncard="25"),
    )
    result = estimate_price(seg)
    assert result.amount == pytest.approx(150 * 0.75)


def test_db_flexpreis_odpowiada_rzeczywistej_probce():
    # Halle (Saale) -> München, ~373 km, rzeczywisty Flexpreis 2. klasy: 106-127 EUR
    # (bahndampf.de). Nasza formuła powinna dać wynik w tym przedziale.
    seg = Segment(Carrier.DB, "Halle (Saale) Hbf", "München Hbf", distance_km=373)
    result = estimate_price(seg)
    assert 106 <= result.amount <= 127


def test_vrr_eezy_krotki_dystans():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Duisburg Hbf", distance_km=20)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.amount == pytest.approx(1.73 + 0.29 * 20, abs=0.01)


def test_vrr_eezy_sufit_cenowy():
    seg = Segment(Carrier.VRR, "Duisburg Hbf", "Dortmund Hbf", distance_km=200)
    result = estimate_price(seg)
    assert result.amount == 19.80
    assert result.breakdown["sufit_zastosowany"] is True


def test_vrr_wymaga_dystansu():
    seg = Segment(Carrier.VRR, "Essen Hbf", "Dortmund Hbf")
    with pytest.raises(ValueError):
        estimate_price(seg)
