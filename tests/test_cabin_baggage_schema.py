"""Schemat flights/data/cabin_baggage.json: zasada absolutna - zweryfikowany wpis ma URL i datę."""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).parent.parent / "flights" / "data" / "cabin_baggage.json").read_text(encoding="utf-8"))
STANY = set(DATA["stany"]) | {"zalezy_od_taryfy"}


def test_kazdy_wpis_ma_flage_weryfikacji():
    for code, e in DATA["przewoznicy"].items():
        assert isinstance(e["price_verified"], bool), code
        assert e["nazwa"], code


def test_zweryfikowany_ma_zrodlo_i_date():
    for code, e in DATA["przewoznicy"].items():
        if e["price_verified"]:
            assert e["zrodlo"].startswith("https://"), code
            assert len(e["data_weryfikacji"]) == 10, code
            assert e["stan_w_cenie_bazowej"] in STANY, code


def test_niezweryfikowany_nie_ma_liczb_w_danych():
    for code, e in DATA["przewoznicy"].items():
        if not e["price_verified"]:
            assert e["cena_w_bazie"] is None and e["podreczny_platny"] is None, code
            assert e["zrodlo_oficjalne_do_sprawdzenia"].startswith("https://"), code
