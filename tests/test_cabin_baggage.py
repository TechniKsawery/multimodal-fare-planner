"""Bagaż podręczny: trzy stany (wliczony / płatny / nieznany), oryginalne waluty, brak zmian ceny."""
import pytest

from flights import cabin_baggage as cb
from flights.cabin_baggage import CabinBaggageState as S
from flights.cabin_baggage import format_breakdown, get_cabin_baggage
from routing import pricing
from routing.model import LegMode
from tests.test_routing import _dt, make_leg


def _fees(code):
    return {f.label: f for f in get_cabin_baggage(code).fees}


def test_lot_wliczony():
    info = get_cabin_baggage("lo")
    assert info.state is S.INCLUDED and info.fees == []
    assert info.source.startswith("https://") and info.verified_on == "2026-10-12"


def test_ryanair_platny_widelki_w_eur():
    info = get_cabin_baggage("FR")
    assert info.state is S.PAID
    f = _fees("FR")
    assert (f["online przy rezerwacji"].min_amount, f["online przy rezerwacji"].max_amount) == (12.49, 36.00)
    assert {x.currency for x in info.fees} == {"EUR"}
    assert (f["przy bramce"].min_amount, f["przy bramce"].max_amount) == (46.00, 75.00)


def test_wizz_platny_widelki_w_eur():
    f = _fees("W6")
    assert get_cabin_baggage("W6").state is S.PAID
    assert (f["online"].min_amount, f["online"].max_amount, f["online"].currency) == (13.00, 57.50, "EUR")


def test_easyjet_w_gbp_nie_przeliczane():
    info = get_cabin_baggage("U2")
    assert info.state is S.PAID
    assert {f.currency for f in info.fees} == {"GBP"}
    assert any(f.is_from and f.min_amount == 5.99 for f in info.fees)


def test_eurowings_pola_od_w_swoich_walutach():
    info = get_cabin_baggage("EW")
    assert info.state is S.PAID
    by_cur = {(f.currency, f.is_from): f.min_amount for f in info.fees}
    assert by_cur == {("EUR", True): 18.0, ("EUR", False): 60.0}


def test_lufthansa_zalezy_od_taryfy_to_nieznany():
    info = get_cabin_baggage("LH")
    assert info.state is S.UNKNOWN and info.fees == []
    assert "Basic" in info.description and "Light" in info.description


@pytest.mark.parametrize("code", [None, "", "ZZ"])
def test_nieznany_przewoznik(code):
    info = get_cabin_baggage(code)
    assert info.state is S.UNKNOWN and info.fees == [] and info.source is None


def test_niezweryfikowany_wpis_jest_nieznany(monkeypatch):
    data = {"przewoznicy": {"XX": {"nazwa": "Test Air", "price_verified": False,
                                   "zrodlo_oficjalne_do_sprawdzenia": "https://example.com"}}}
    monkeypatch.setattr(cb, "_DATA", data)
    info = get_cabin_baggage("XX")
    assert info.state is S.UNKNOWN and info.fees == []


def test_kazde_pole_doplaty_w_pliku_jest_rozpoznane():
    for code, e in cb._DATA["przewoznicy"].items():
        d = (e.get("podreczny") or {}).get("doplata")
        if not d:
            continue
        parsed = cb._parse_fees(d)
        for f in parsed:
            assert f.label in set(cb._FEE_LABELS.values()), (code, f.label)
            assert f.currency in {"EUR", "GBP", "PLN"}, (code, f.currency)
        n_keys = len([k for k in d if k != "waluta" and not k.endswith("_max")])
        assert len(parsed) == n_keys, code


def test_format_pokazuje_walute_i_brak_wliczenia_w_cene():
    txt = format_breakdown(get_cabin_baggage("FR").to_dict())
    assert "PŁATNY" in txt and "12.49–36.00 EUR" in txt and "NIE wliczona" in txt and "2026-10-12" in txt
    assert "NIEZNANY" in format_breakdown(get_cabin_baggage("ZZ").to_dict())


def _price(monkeypatch, linia, checked=False):
    leg = make_leg(LegMode.FLIGHT, "WAW", "DTM", _dt(6), _dt(8),
                   extra={"origin_iata": "WAW", "destination_iata": "DTM",
                          "depart_date": "2026-11-15", "checked_baggage": checked})

    def fake_estimate(segment):
        from flights.model import PriceEstimate, PriceType
        return PriceEstimate("WAW", "DTM", 200.0, "PLN", PriceType.ESTIMATE,
                             {"cena_biletu": 200.0, "linia": linia, "bagaz": 0.0}, "test")

    monkeypatch.setattr(pricing, "flights_estimate_price", fake_estimate)
    return pricing.price_flight_leg(leg)


@pytest.mark.parametrize("linia,stan", [("LO", "wliczony"), ("FR", "platny"), ("W6", "platny"),
                                        ("EW", "platny"), ("U2", "platny"), ("LH", "nieznany"),
                                        (None, "nieznany")])
def test_price_flight_leg_dodaje_stan_bagazu_i_nie_rusza_ceny(monkeypatch, linia, stan):
    priced = _price(monkeypatch, linia)
    assert priced.breakdown["bagaz_podreczny"]["stan"] == stan
    assert priced.amount == 200.0  # dopłata za podręczny nie wchodzi do ceny (bez przeliczania walut)
    assert priced.breakdown["cena_biletu"] == 200.0


@pytest.mark.parametrize("code", ["FR", "W6", "EW", "U2"])
def test_doplaty_tanich_linii_niepotwierdzone_i_jedna_waluta(code):
    info = get_cabin_baggage(code)
    assert info.price_verified and not info.fees_verified
    assert len({f.currency for f in info.fees}) == 1
    assert info.to_dict()["oplaty_potwierdzone"] is False
    assert "NIEPOTWIERDZONA" in format_breakdown(info.to_dict())


def test_lot_i_lufthansa_bez_dopłat_nie_maja_etykiety_niepotwierdzonej():
    assert "NIEPOTWIERDZONA" not in format_breakdown(get_cabin_baggage("LO").to_dict())
