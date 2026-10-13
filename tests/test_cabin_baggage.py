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
    en = f["online przy rezerwacji, wg strony EN"]
    assert (en.min_amount, en.max_amount) == (12.49, 36.00)
    assert {x.currency for x in info.fees} == {"EUR"}
    assert (f["przy bramce"].min_amount, f["przy bramce"].max_amount) == (46.00, 75.00)


def test_wizz_platny_widelki_w_eur():
    f = _fees("W6")
    assert get_cabin_baggage("W6").state is S.PAID
    online = f["WIZZ Priority online / telecentrum"]
    assert (online.min_amount, online.max_amount, online.currency) == (13.00, 57.50, "EUR")


def test_easyjet_w_gbp_nie_przeliczane():
    info = get_cabin_baggage("U2")
    assert info.state is S.PAID
    assert {f.currency for f in info.fees} == {"GBP"}
    assert [(f.label, f.min_amount) for f in info.fees] == [("przy bramce", 60.0)]
    assert not any(f.is_from for f in info.fees)  # online zmienne: brak stałej kwoty


def test_easyjet_oplaty_dodatkowe_ze_zrodlem():
    info = get_cabin_baggage("U2")
    by = {e.label: e for e in info.extra_fees}
    assert by["bagaż rejestrowany online"].amount is None and not by["bagaż rejestrowany online"].confirmed
    drop = by["bagaż rejestrowany przy stanowisku bag drop"]
    assert (drop.amount, drop.currency, drop.confirmed) == (60.0, "GBP", True)
    assert (by["nadwaga bagażu, za kg"].amount, by["nadwaga bagażu, za kg"].currency) == (12.0, "GBP")
    assert by["dodatkowa waga do 32 kg, online, za 3 kg"].kind == "do"
    assert info.fees_source == "https://www.easyjet.com/en/terms-and-conditions/fees"
    assert info.fees_verified_on == "2026-10-13"
    assert "cena zmienna" in by["bagaż rejestrowany online"].format()


def test_eurowings_pola_od_w_swoich_walutach():
    info = get_cabin_baggage("EW")
    assert info.state is S.PAID
    by_cur = {(f.currency, f.is_from): f.min_amount for f in info.fees}
    assert by_cur == {("EUR", True): 21.0, ("EUR", False): 60.0}
    assert {f.label: f.min_amount for f in info.fees if not f.is_from} == {"na lotnisku": 45.0, "przy bramce": 60.0}


def test_eurowings_oplaty_dodatkowe_od_vs_stale():
    info = get_cabin_baggage("EW")
    by = {e.label: e for e in info.extra_fees}
    od = [e for e in info.extra_fees if e.kind == "od"]
    assert {e.amount for e in od} == {18.0, 75.0} and not any(e.confirmed for e in od)
    assert "niepotwierdzona" in od[0].format()
    assert by["bagaż rejestrowany do 23 kg na lotnisku / offline"].amount == 40.0
    assert by["nadwaga bagażu rejestrowanego, za kg"].amount == 15.0
    assert all(e.confirmed for e in info.extra_fees if e.kind == "stala")
    assert info.fees_source.startswith("https://www.eurowings.com/en/legal-information/schedule-of-charges")
    d = info.to_dict()
    assert len(d["oplaty_dodatkowe"]) == 4 and d["data_weryfikacji_oplat"] == "2026-10-13"
    assert "Inne opłaty bagażowe" in format_breakdown(d)


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
def test_doplaty_tanich_linii_jedna_waluta(code):
    info = get_cabin_baggage(code)
    assert info.price_verified
    assert len({f.currency for f in info.fees}) == 1


def test_eurowings_dopłata_podręczny_online_zostaje_niepotwierdzona():
    info = get_cabin_baggage("EW")
    assert not info.fees_verified
    assert info.to_dict()["oplaty_potwierdzone"] is False
    assert "NIEPOTWIERDZONA" in format_breakdown(info.to_dict())


def test_easyjet_oplata_bramkowa_potwierdzona_online_bez_kwoty():
    info = get_cabin_baggage("U2")
    assert info.fees_verified
    txt = format_breakdown(info.to_dict())
    assert "60.00 GBP (przy bramce)" in txt and "5.99" not in txt


def test_easyjet_stala_kwota_pokazana_jako_kwota_nie_jako_przedzial():
    txt = format_breakdown(get_cabin_baggage("U2").to_dict())
    dopl = txt.split("Dopłata", 1)[1].split("Inne opłaty", 1)[0]
    assert "STAŁA kwota" in dopl and "PRZEDZIAŁ" not in dopl and "–" not in dopl


def test_tag_rodzaju_oplaty_zalezy_od_pozycji_a_nie_od_samej_flagi_potwierdzenia():
    def fee(od, do=None, tylko_od=False):
        return {"etykieta": "x", "od": od, "do": do, "waluta": "EUR", "tylko_od": tylko_od,
                "tekst": f"{od}-{do} EUR (x)"}

    def render(*fees):
        return format_breakdown({"stan": "platny", "oplaty": list(fees), "oplaty_potwierdzone": True,
                                 "opis": ""})

    assert "PRZEDZIAŁ" in render(fee(6.0, 36.0)) and "STAŁA" not in render(fee(6.0, 36.0))
    assert "STAŁA kwota" in render(fee(60.0)) and "PRZEDZIAŁ" not in render(fee(60.0))
    assert "STAŁA kwota" in render(fee(60.0, 60.0))  # min == max to kwota, nie przedział
    assert "cena „od”" in render(fee(21.0, tylko_od=True))
    mixed = render(fee(6.0, 36.0), fee(60.0))
    assert "[przedział]" in mixed and "[kwota stała]" in mixed
    assert mixed.index("[przedział]") < mixed.index("[kwota stała]")


@pytest.mark.parametrize("code", ["FR", "W6"])
def test_ryanair_i_wizz_maja_potwierdzony_oficjalny_przedzial(code):
    info = get_cabin_baggage(code)
    assert info.fees_verified and info.to_dict()["oplaty_potwierdzone"] is True
    txt = format_breakdown(info.to_dict())
    assert "oficjalny PRZEDZIAŁ" in txt and "NIEPOTWIERDZONA" not in txt
    assert "nie cena konkretnego lotu" in txt
    # każda pozycja to przedział min-max, nigdy pojedyncza kwota ani "od X"
    assert info.fees and all(f.max_amount is not None and f.max_amount > f.min_amount and not f.is_from for f in info.fees)
    pot = next(e for c, e in cb._DATA["przewoznicy"].items() if c == code)["doplata_potwierdzenie"]
    assert pot["data"] == "2026-10-12" and pot["zrodla"] and all(u.startswith("https://") for u in pot["zrodla"])
    assert "niezweryfikowane niezależnie" in pot["metoda"]


def test_ryanair_zapisuje_oba_przedzialy_pl_i_en_i_wskazuje_rozbieznosc():
    fees = {f.label: (f.min_amount, f.max_amount) for f in get_cabin_baggage("FR").fees}
    assert fees["online przy rezerwacji, wg strony PL"] == (6.0, 36.0)
    assert fees["online przy rezerwacji, wg strony EN"] == (12.49, 36.0)
    assert fees["przy bramce"] == (46.0, 75.0)
    desc = get_cabin_baggage("FR").description
    assert "różnią się" in desc and "PL podaje 6–36" in desc and "EN 12,49–36" in desc


def test_wizz_rozdziela_priority_na_lotnisku_od_kary_za_bagaz_do_luku():
    info = get_cabin_baggage("W6")
    fees = {f.label: (f.min_amount, f.max_amount) for f in info.fees}
    assert fees["zakup WIZZ Priority na lotnisku"] == (65.0, 75.0)
    assert fees["kara za bagaż podręczny wysłany do luku"] == (55.0, 65.0)
    assert fees["WIZZ Priority online / telecentrum"] == (13.0, 57.5)
    assert "zakup WIZZ Priority na lotnisku" in info.description and "kara za bagaż podręczny wysłany do luku" in info.description


def test_lot_i_lufthansa_bez_dopłat_nie_maja_etykiety_niepotwierdzonej():
    assert "NIEPOTWIERDZONA" not in format_breakdown(get_cabin_baggage("LO").to_dict())


def test_potwierdzony_przedzial_jest_nazwany_przedzialem(monkeypatch):
    d = get_cabin_baggage("FR").to_dict()
    d["oplaty_potwierdzone"] = True
    txt = format_breakdown(d)
    assert "PRZEDZIAŁ" in txt and "NIEPOTWIERDZONA" not in txt
