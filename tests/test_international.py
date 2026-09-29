from datetime import datetime, timedelta

import pytest

from fares.international import estimate as international_estimate
from fares.model import Carrier, DiscountProfile, Segment
from routing.model import Leg, LegMode
from routing.pricing import is_cross_border_pl_de, price_rail_leg


WARSZAWA = {"lat": 52.2288, "lon": 21.0034}
BERLIN = {"lat": 52.5251, "lon": 13.3694}
LUBLIN = {"lat": 51.2465, "lon": 22.5684}
GELSENKIRCHEN = {"lat": 51.5177, "lon": 7.0857}


def _leg(origin_stop_id, destination_stop_id, distance_km=500.0, carrier_name="PKP Intercity",
         origin_latlon=None, destination_latlon=None):
    depart = datetime(2026, 10, 1, 8, 0)
    extra = {"origin_stop_id": origin_stop_id, "destination_stop_id": destination_stop_id}
    if origin_latlon:
        extra["origin_lat"], extra["origin_lon"] = origin_latlon["lat"], origin_latlon["lon"]
    if destination_latlon:
        extra["destination_lat"], extra["destination_lon"] = destination_latlon["lat"], destination_latlon["lon"]
    return Leg(
        mode=LegMode.RAIL,
        origin_name="A",
        destination_name="B",
        depart=depart,
        arrive=depart + timedelta(hours=5),
        carrier_name=carrier_name,
        distance_km=distance_km,
        extra=extra,
    )


# --- is_cross_border_pl_de --------------------------------------------------------------

def test_pl_do_de_jest_miedzynarodowy():
    assert is_cross_border_pl_de(_leg("pl_50500", "defv_344028")) is True


def test_de_do_pl_jest_miedzynarodowy():
    assert is_cross_border_pl_de(_leg("defv_344028", "pl_50500")) is True


def test_ztml_do_derv_jest_miedzynarodowy():
    assert is_cross_border_pl_de(_leg("ztml_1001", "derv_9")) is True


def test_pl_do_pl_nie_jest_miedzynarodowy():
    assert is_cross_border_pl_de(_leg("pl_50500", "pl_38653")) is False


def test_defv_do_derv_nie_jest_miedzynarodowy():
    # oba w Niemczech (dalekobieżny -> regionalny) — nie przekracza granicy
    assert is_cross_border_pl_de(_leg("defv_1", "derv_2")) is False


def test_brak_stop_id_nie_jest_miedzynarodowy():
    # punkt bez stopId (np. współrzędne z via-hub) — nie potrafimy stwierdzić, bezpieczny fallback False
    assert is_cross_border_pl_de(_leg(None, "defv_1")) is False
    assert is_cross_border_pl_de(_leg("pl_1", None)) is False


def test_stacja_w_niemczech_oznaczona_prefiksem_pl_jest_wykryta_geograficznie():
    # ZGŁOSZONY BUG (2026-09-29): Warszawa Wschodnia -> Berlin-Lichtenberg, oba stopId z
    # prefiksem 'pl_' (polski feed GTFS publikuje też zagraniczne przystanki dla kursów
    # międzynarodowych PKP Intercity) — sam prefiks datasetu błędnie mówił "oba w Polsce".
    # Współrzędne (Berlin-Lichtenberg fizycznie w Niemczech) muszą to poprawnie wykryć.
    leg = _leg("pl_100", "pl_200", origin_latlon=WARSZAWA, destination_latlon=BERLIN)
    assert is_cross_border_pl_de(leg) is True


def test_wspolrzedne_nadpisuja_mylacy_prefiks_datasetu_w_obie_strony():
    # to samo, odwrotny kierunek
    leg = _leg("pl_200", "pl_100", origin_latlon=BERLIN, destination_latlon=WARSZAWA)
    assert is_cross_border_pl_de(leg) is True


def test_oba_konce_w_polsce_mimo_roznych_datasetow_nie_jest_miedzynarodowy():
    leg = _leg("pl_1", "ztml_1", origin_latlon=WARSZAWA, destination_latlon=LUBLIN)
    assert is_cross_border_pl_de(leg) is False


def test_oba_konce_w_niemczech_mimo_roznych_datasetow_nie_jest_miedzynarodowy():
    leg = _leg("defv_1", "derv_1", origin_latlon=BERLIN, destination_latlon=GELSENKIRCHEN)
    assert is_cross_border_pl_de(leg) is False


def test_brak_wspolrzednych_spada_do_prefiksu_datasetu():
    # bez lat/lon (np. stare dane w cache) — fallback na starą heurystykę prefiksu
    assert is_cross_border_pl_de(_leg("pl_1", "defv_1")) is True
    assert is_cross_border_pl_de(_leg("pl_1", "pl_2")) is False


# --- fares/international.py ---------------------------------------------------------------

def test_krotka_relacja_cena_od_19_99():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin", "Poznan", distance_km=240)
    result = international_estimate(seg)
    assert result.amount == 19.99


def test_srednia_relacja_cena_od_29_99():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin", "Warszawa", distance_km=519)
    result = international_estimate(seg)
    assert result.amount == 29.99


def test_dluga_relacja_cena_od_39_99():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin", "Krakow", distance_km=532)
    result = international_estimate(seg)
    assert result.amount == 39.99


def test_bahncard_25_nie_daje_dodatkowego_rabatu_na_cene_promocyjna():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE, "Berlin", "Warszawa", distance_km=519,
        discounts=DiscountProfile(bahncard="25"),
    )
    assert international_estimate(seg).amount == 29.99


def test_bahncard_50_daje_25_procent():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE, "Berlin", "Warszawa", distance_km=519,
        discounts=DiscountProfile(bahncard="50"),
    )
    assert international_estimate(seg).amount == pytest.approx(29.99 * 0.75, abs=0.01)


def test_bledny_przewoznik_podnosi_blad():
    with pytest.raises(ValueError):
        international_estimate(Segment(Carrier.DB, "Berlin", "Warszawa", distance_km=519))


# --- routing/pricing.py::price_rail_leg — międzynarodowy leg wymusza Carrier.INTERNATIONAL_PL_DE

def test_price_rail_leg_wymusza_taryfe_miedzynarodowa_dla_odcinka_z_niemiecka_stacja_w_polskim_feedzie():
    # replika zgłoszonego bugu: oba stopId z prefiksem 'pl_' (Berlin-Lichtenberg opublikowany w
    # polskim feedzie GTFS dla kursu PKP Intercity), rozstrzyga geografia.
    leg = _leg("pl_50500", "pl_999999", distance_km=519, carrier_name="PKP Intercity",
               origin_latlon=WARSZAWA, destination_latlon=BERLIN)
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.amount == 29.99


def test_price_rail_leg_wymusza_taryfe_miedzynarodowa_dla_odcinka_przez_granice():
    leg = _leg("pl_50500", "defv_344028", distance_km=519, carrier_name="PKP Intercity")
    priced = price_rail_leg(leg, DiscountProfile())
    # 29.99 EUR (kategoria 'srednia'), NIE krajowa cena PKP wg pasma 519km (byłoby dużo więcej PLN)
    assert priced.currency == "EUR"
    assert priced.amount == 29.99


def test_price_rail_leg_krajowy_pkp_dziala_jak_wczesniej():
    leg = _leg("pl_50500", "pl_38653", distance_km=170, carrier_name="PKP Intercity")
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "PLN"
    assert priced.amount == 50  # krajowa tabela pasm PKP, jak w tests/test_fares.py
