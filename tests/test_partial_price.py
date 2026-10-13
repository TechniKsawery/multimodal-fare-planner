"""Cena nieznana nie jest 0 zł (UI: "brak ceny" / "cena częściowa") i "szacunek" bez jawnej
flagi nie jest "potwierdzony" (przyczyna verified=True przy FlixBusie)."""

from datetime import datetime, timedelta

import demo
from i18n import TRANSLATIONS, t
from routing import pricing, scoring
from routing.model import Leg, LegMode, PricedLeg
from ui_helpers import variant_price_text


def _leg(mode=LegMode.RAIL, minutes=60, carrier="X"):
    depart = datetime(2026, 10, 20, 8, 0)
    return Leg(
        mode=mode,
        origin_name="A",
        destination_name="B",
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name=carrier,
        distance_km=50.0,
    )


def _unknown():
    return pricing.price_gorlitz_area_unconfirmed_leg(_leg(LegMode.BUS, 10, "Inny operator"))


def _priced(amount, **breakdown):
    return PricedLeg(
        leg=_leg(), amount=amount, currency="PLN", price_type="oficjalna_taryfa", breakdown=breakdown
    )


def test_wszystkie_odcinki_z_cena_to_cena_pelna():
    it = scoring.build_itinerary("v", [_priced(30.0)])
    assert it.price_status == "pelna"
    assert variant_price_text(it) == "30 PLN"


def test_sam_odcinek_bez_ceny_to_brak_ceny_a_nie_0_zl():
    it = scoring.build_itinerary("v", [_unknown()])
    assert it.total_price_pln == 0.0
    assert it.price_status == "brak"
    text = variant_price_text(it)
    assert text == "brak ceny" and "0" not in text
    out = demo.format_itinerary(it)
    assert "brak ceny" in out and "0.00 PLN" not in out


def test_odcinek_pieszy_nie_udaje_ceny_znanej():
    walk = PricedLeg(
        leg=_leg(LegMode.WALK, 5), amount=0.0, currency="PLN", price_type="oficjalna_taryfa"
    )
    it = scoring.build_itinerary("v", [walk, _unknown()])
    assert it.price_status == "brak"


def test_czesc_odcinkow_bez_ceny_to_cena_czesciowa():
    it = scoring.build_itinerary("v", [_priced(30.0), _unknown()])
    assert it.total_price_pln == 30.0  # nic nie dopisujemy za nieznany odcinek
    assert it.price_status == "czesciowa"
    assert variant_price_text(it) == "cena częściowa: od 30 PLN"
    out = demo.format_itinerary(it)
    assert "cena częściowa, od 30.00 PLN" in out and "brak ceny" in out


def test_cena_czesciowa_z_przedzialem_pkp():
    spi = _priced(40.0, zakres_cen={"od": 20.0, "do": 60.0, "waluta": "PLN"})
    it = scoring.build_itinerary("v", [spi, _unknown()])
    assert it.price_status == "czesciowa"
    assert variant_price_text(it) == "cena częściowa: od 40 do 60 PLN"


def test_wszystkie_jezyki_maja_teksty_braku_i_czesci_ceny():
    for lang, texts in TRANSLATIONS.items():
        for key in ("price.variant_none", "price.variant_partial", "price.unknown_leg"):
            assert texts[key].strip(), (lang, key)
        assert t("price.variant_none", lang=lang) != t("price.variant_single", lang=lang, price=0)


def test_szacunek_bez_jawnej_flagi_nie_jest_potwierdzony():
    estimate = PricedLeg(
        leg=_leg(), amount=19.99, currency="EUR", price_type="szacunek",
        breakdown={"zrodlo": "api_flixbus_live"},
    )
    assert not estimate.price_verified


def test_jawna_flaga_wygrywa_z_typem_ceny():
    polregio_like = PricedLeg(
        leg=_leg(), amount=10.0, currency="PLN", price_type="szacunek",
        breakdown={"price_verified": True},
    )
    assert polregio_like.price_verified
    assert _priced(10.0).price_verified  # oficjalna taryfa bez flagi: bez zmian
    assert not _priced(10.0, price_verified=False).price_verified
