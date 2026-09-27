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


def test_vrr_grundpreis_plus_km():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "EUR"
    assert result.amount == pytest.approx(1.73 + 0.29 * 10, abs=0.01)


def test_vrr_sufit_cenowy_ograniczajacy_dlugi_dystans():
    seg = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Bonn Hbf", distance_km=200)
    result = estimate_price(seg)
    assert result.amount == 19.80  # sufit preisstufe C


def test_vrr_bez_dystansu_podnosi_blad():
    seg = Segment(Carrier.VRR, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_vrr_kindertarif_50_procent_rabatu():
    normalny = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10)
    dziecko = Segment(
        Carrier.VRR, "Gelsenkirchen Hbf", "Essen Hbf", distance_km=10,
        discounts=DiscountProfile(vrr_dziecko=True),
    )
    cena_normalna = estimate_price(normalny).amount
    result = estimate_price(dziecko)
    assert result.amount == pytest.approx(cena_normalna * 0.5, abs=0.01)
    assert result.price_type is PriceType.OFFICIAL


def test_vrr_kindertarif_dziala_tez_na_sufit_cenowy():
    dziecko = Segment(
        Carrier.VRR, "Gelsenkirchen Hbf", "Bonn Hbf", distance_km=200,
        discounts=DiscountProfile(vrr_dziecko=True),
    )
    assert estimate_price(dziecko).amount == pytest.approx(19.80 * 0.5, abs=0.01)


def test_ztm_lublin_krotki_przejazd_bilet_15_minutowy():
    seg = Segment(Carrier.ZTM_LUBLIN, "Ogród Saski", "Dworzec Lublin", ride_duration_min=8)
    result = estimate_price(seg)
    assert result.price_type is PriceType.OFFICIAL
    assert result.currency == "PLN"
    assert result.amount == 3.40


def test_ztm_lublin_ulgowy():
    seg = Segment(
        Carrier.ZTM_LUBLIN, "Ogród Saski", "Dworzec Lublin", ride_duration_min=8,
        discounts=DiscountProfile(ztm_lublin_ulgowy=True),
    )
    result = estimate_price(seg)
    assert result.amount == 1.70


def test_ztm_lublin_dobiera_dluzszy_bilet():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=35)
    result = estimate_price(seg)
    assert result.amount == 4.60  # bilet 40-minutowy


def test_ztm_lublin_przekroczenie_najdluzszego_biletu_to_szacunek():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B", ride_duration_min=120)
    result = estimate_price(seg)
    assert result.amount == 5.20  # ekstrapolacja na bazie biletu 90-minutowego
    assert result.price_type is PriceType.ESTIMATE


def test_ztm_lublin_bez_czasu_jazdy_podnosi_blad():
    seg = Segment(Carrier.ZTM_LUBLIN, "A", "B")
    with pytest.raises(ValueError):
        estimate_price(seg)
