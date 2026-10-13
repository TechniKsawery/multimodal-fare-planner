"""Regresje z audytu wyceny: K2 (taryfa VRR poza NRW), S2 (EIC/EIP jako cennik TLK/IC),
S3 (granica PL/DE: Görlitz, Szczecin), S4 (dopasowanie miast po fragmentach nazw).

Współrzędne stacji/miejsc są przybliżone (do ok. 0,01°) — wystarczą do rozróżnienia miast i
stron granicy, nie są danymi cenowymi."""

from datetime import datetime, timedelta

import pytest

from fares.model import Carrier, DiscountProfile
from routing import motis_client, pricing
from routing.model import Leg, LegMode

BERLIN_ALEXANDERPLATZ = (52.5219, 13.4132)
BERLIN_OSTKREUZ = (52.5030, 13.4690)
BERLIN_GESUNDBRUNNEN = (52.5486, 13.3884)
POTSDAM_HBF = (52.3917, 13.0669)
LUBLIN_GLOWNY = (51.2297, 22.5745)
DEBLIN = (51.5640, 21.8473)
NUERNBERG_HBF = (49.4456, 11.0827)
REGENSBURG_HBF = (49.0118, 12.0997)
DRESDEN_HBF = (51.0405, 13.7320)
DRESDEN_NEUSTADT = (51.0654, 13.7409)
ESSEN_HBF = (51.4514, 7.0139)
ESSEN_RUETTENSCHEID = (51.4300, 7.0000)
GOERLITZ = (51.1468, 14.9757)
ZGORZELEC = (51.1500, 15.0200)
SZCZECIN_GLOWNY = (53.4285, 14.5528)
WROCLAW_GLOWNY = (51.0983, 17.0367)
WARSZAWA_KRAKOWSKIE_PRZEDMIESCIE = (52.2410, 21.0150)
WARSZAWA_PLAC_ZAMKOWY = (52.2477, 21.0136)
LUBLIN_KRAKOWSKIE_PRZEDMIESCIE = (51.2484, 22.5610)
LUBLIN_PLAC_LITEWSKI = (51.2488, 22.5594)


def _leg(
    mode,
    origin,
    destination,
    *,
    carrier="",
    origin_xy=None,
    destination_xy=None,
    distance_km=None,
    minutes=15,
    extra=None,
):
    depart = datetime(2026, 10, 20, 8, 0)
    extra = dict(extra or {})
    if origin_xy and destination_xy:
        extra.update(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
        if distance_km is None:
            distance_km = motis_client.haversine_km(*origin_xy, *destination_xy)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=minutes),
        carrier_name=carrier,
        distance_km=distance_km if distance_km is not None else 10.0,
        extra=extra,
    )


def _assert_unverified_estimate(priced):
    assert priced.price_type == "szacunek"
    assert priced.breakdown.get("price_verified") is False
    assert priced.carrier is not Carrier.VRR


# --- K2: eezy.nrw (VRR) tylko w NRW ---------------------------------------------------------


def test_s_bahn_berlin_w_obrebie_berlina_to_taryfa_berlinska_nie_vrr():
    leg = _leg(
        LegMode.RAIL,
        "S Alexanderplatz",
        "S Ostkreuz",
        carrier="S-Bahn Berlin GmbH",
        origin_xy=BERLIN_ALEXANDERPLATZ,
        destination_xy=BERLIN_OSTKREUZ,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.BVG_BERLIN


def test_s_bahn_berlin_poza_berlinem_to_niepotwierdzony_szacunek():
    leg = _leg(
        LegMode.RAIL,
        "Berlin Alexanderplatz",
        "Potsdam Hbf",
        carrier="S-Bahn Berlin GmbH",
        origin_xy=BERLIN_ALEXANDERPLATZ,
        destination_xy=POTSDAM_HBF,
        minutes=45,
    )
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_polregio_nie_dostaje_taryfy_vrr():
    leg = _leg(
        LegMode.RAIL,
        "Lublin Główny",
        "Dęblin",
        carrier="POLREGIO",
        origin_xy=LUBLIN_GLOWNY,
        destination_xy=DEBLIN,
        minutes=70,
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    # POLREGIO w Polsce ma teraz własną tabelę (fares/polregio.py): potwierdzona kwota pasma,
    # ale pasmo z linii prostej, więc cena zostaje szacunkiem; w żadnym razie nie eezy.nrw/VRR.
    assert priced.carrier is Carrier.POLREGIO_PODSTAWOWA
    assert priced.carrier is not Carrier.VRR
    assert priced.price_type == "szacunek"
    assert priced.currency == "PLN"


def test_db_regio_w_bawarii_nie_dostaje_taryfy_vrr():
    leg = _leg(
        LegMode.RAIL,
        "Nürnberg Hbf",
        "Regensburg Hbf",
        carrier="DB Regio AG Bayern",
        origin_xy=NUERNBERG_HBF,
        destination_xy=REGENSBURG_HBF,
        minutes=60,
    )
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_db_regio_nrw_bez_wspolrzednych_nie_zaklada_nrw():
    leg = _leg(LegMode.RAIL, "Essen Hbf", "Dortmund Hbf", carrier="DB Regio AG NRW", distance_km=33)
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_flixtrain_w_nrw_nie_dostaje_eezy_nrw():
    leg = _leg(
        LegMode.RAIL,
        "Essen Hbf",
        "Essen Süd",
        carrier="FlixTrain",
        origin_xy=ESSEN_HBF,
        destination_xy=ESSEN_RUETTENSCHEID,
    )
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_nierozpoznany_autobus_poza_nrw_dostaje_jawny_ryczalt_nie_vrr():
    leg = _leg(
        LegMode.BUS,
        "Dresden Hbf",
        "Dresden-Neustadt",
        carrier="DVB",
        origin_xy=DRESDEN_HBF,
        destination_xy=DRESDEN_NEUSTADT,
        extra={"motis_mode": "TRAM"},
    )
    priced = pricing.price_bus_leg(leg)
    _assert_unverified_estimate(priced)
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN


def test_ryczalt_osiagalny_dla_legu_z_motis_mimo_ustawionego_dystansu():
    # motis_client.itinerary_to_legs ZAWSZE liczy distance_km — wcześniej to kierowało każdy
    # nierozpoznany autobus do VRR, a ryczałt był martwym kodem.
    raw = {
        "legs": [
            {
                "mode": "BUS",
                "from": {"name": "Dresden Hbf", "lat": DRESDEN_HBF[0], "lon": DRESDEN_HBF[1]},
                "to": {
                    "name": "Albertplatz",
                    "lat": DRESDEN_NEUSTADT[0],
                    "lon": DRESDEN_NEUSTADT[1],
                },
                "startTime": "2026-10-20T08:00:00Z",
                "endTime": "2026-10-20T08:12:00Z",
                "agencyName": "Dresdner Verkehrsbetriebe",
            }
        ]
    }
    (leg,) = motis_client.itinerary_to_legs(raw)
    assert leg.distance_km is not None
    priced = pricing.price_bus_leg(leg)
    assert priced.amount == pricing.LOCAL_BUS_FLAT_PLN
    assert priced.breakdown["price_verified"] is False


def test_autobus_w_nrw_nadal_eezy_nrw():
    leg = _leg(
        LegMode.BUS,
        "Essen Hbf",
        "Rüttenscheider Stern",
        carrier="Ruhrbahn",
        origin_xy=ESSEN_HBF,
        destination_xy=ESSEN_RUETTENSCHEID,
        extra={"motis_mode": "BUS"},
    )
    priced = pricing.price_bus_leg(leg)
    assert priced.carrier is Carrier.VRR
    assert priced.currency == "EUR"
    assert priced.price_type == "oficjalna_taryfa"


def test_fallback_km_jest_oznaczony_jako_niepotwierdzony():
    leg = _leg(LegMode.RAIL, "A", "B", carrier="Coś Nieznanego", distance_km=100)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.breakdown["price_verified"] is False
    assert "niepotwierdzona" in priced.notes


# --- S2: EIC/EIP to nie cennik TLK/IC --------------------------------------------------------


@pytest.mark.parametrize("route", ["EIC", "EIP", "EIC 1600", "EIP 5100"])
def test_eic_eip_jest_niepotwierdzonym_szacunkiem(route):
    leg = _leg(
        LegMode.RAIL,
        "Warszawa Centralna",
        "Kraków Główny",
        carrier="PKP Intercity",
        distance_km=250,
        minutes=150,
        extra={"route_short_name": route},
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.PKP_INTERCITY
    assert priced.price_type == "szacunek"
    assert priced.breakdown["price_verified"] is False
    assert "EIC/EIP" in priced.notes


def test_ic_i_tlk_nadal_oficjalna_taryfa():
    for route in ("IC", "TLK", "IC 3510"):
        leg = _leg(
            LegMode.RAIL,
            "Lublin Główny",
            "Warszawa Wschodnia",
            carrier="PKP Intercity",
            distance_km=170,
            extra={"route_short_name": route},
        )
        priced = pricing.price_rail_leg(leg, DiscountProfile())
        assert priced.price_type == "oficjalna_taryfa", route
        assert "price_verified" not in priced.breakdown


def test_eic_ma_te_sama_kwote_co_pasmo_tlk_ic_ale_inny_status():
    ic = _leg(
        LegMode.RAIL,
        "A",
        "B",
        carrier="PKP Intercity",
        distance_km=250,
        extra={"route_short_name": "IC"},
    )
    eic = _leg(
        LegMode.RAIL,
        "A",
        "B",
        carrier="PKP Intercity",
        distance_km=250,
        extra={"route_short_name": "EIC"},
    )
    assert (
        pricing.price_rail_leg(ic, DiscountProfile()).amount
        == pricing.price_rail_leg(eic, DiscountProfile()).amount
    )


def _wwa_gdansk(route, hour=8, carrier="PKP Intercity"):
    leg = _leg(
        LegMode.RAIL,
        "Warszawa Wschodnia",
        "Gdańsk Główny",
        carrier=carrier,
        distance_km=285,
        minutes=180,
        extra={"route_short_name": route},
    )
    leg.depart = leg.depart.replace(hour=hour)
    leg.arrive = leg.depart + timedelta(minutes=180)
    return pricing.price_rail_leg(leg, DiscountProfile())


@pytest.mark.parametrize("hour", [6, 8, 14, 20])
def test_warszawa_wschodnia_gdansk_67_pln_status_zalezy_tylko_od_kategorii_pociagu(hour):
    # Ta sama kwota 67,00 PLN (pasmo 280-290 km); o statusie decyduje wyłącznie kategoria
    # pociągu z routeShortName/nazwy przewoźnika — nie godzina ani ścieżka wyceny.
    for route in ("IC", "TLK", ""):
        priced = _wwa_gdansk(route, hour)
        assert (priced.amount, priced.price_type) == (67.0, "oficjalna_taryfa"), route
        assert priced.price_verified is True
    for route, carrier in (
        ("EIC", "PKP Intercity"),
        ("EIP", "PKP Intercity"),
        ("", "PKP Intercity Express InterCity"),
    ):
        priced = _wwa_gdansk(route, hour, carrier)
        assert (priced.amount, priced.price_type) == (67.0, "szacunek"), route
        assert priced.price_verified is False


# --- S3: granica PL/DE -----------------------------------------------------------------------


def test_kraj_przy_granicy():
    assert (
        pricing._country_from_latlon(*GOERLITZ) == "DE"
    )  # wcześniej "PL" (DE bbox kończył się na 14.9°E)
    assert pricing._country_from_latlon(*ZGORZELEC) == "PL"
    assert (
        pricing._country_from_latlon(*SZCZECIN_GLOWNY) == "PL"
    )  # wcześniej None (pas 14.0-14.9°E)
    assert pricing._country_from_latlon(53.27, 14.35) == "DE"  # Tantow
    # tuż przy łamanej granicy nie zgadujemy
    assert pricing._country_from_latlon(51.15, 14.995) is None
    # Czechy (na południe od trójstyku) — nie PL i nie DE
    assert pricing._country_from_latlon(50.08, 14.42) is None


def test_szczecin_berlin_db_regio_to_niepotwierdzony_szacunek_nie_vrr():
    leg = _leg(
        LegMode.RAIL,
        "Szczecin Główny",
        "Berlin Gesundbrunnen",
        carrier="DB Regio AG Nordost",
        origin_xy=SZCZECIN_GLOWNY,
        destination_xy=BERLIN_GESUNDBRUNNEN,
        minutes=120,
    )
    assert pricing.is_cross_border_pl_de(leg) is True
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_wroclaw_gorlitz_przewoznik_regionalny_to_niepotwierdzony_szacunek():
    # Odcinek z trasy Kraków -> Görlitz: Görlitz był wcześniej uznawany za Polskę, więc taki
    # odcinek szedł krajową ścieżką wyceny.
    leg = _leg(
        LegMode.RAIL,
        "Wrocław Główny",
        "Görlitz",
        carrier="Koleje Dolnośląskie",
        origin_xy=WROCLAW_GLOWNY,
        destination_xy=GOERLITZ,
        minutes=150,
    )
    assert pricing.is_cross_border_pl_de(leg) is True
    _assert_unverified_estimate(pricing.price_rail_leg(leg, DiscountProfile()))


def test_szczecin_berlin_pkp_intercity_nadal_taryfa_miedzynarodowa():
    leg = _leg(
        LegMode.RAIL,
        "Szczecin Główny",
        "Berlin Gesundbrunnen",
        carrier="PKP Intercity",
        origin_xy=SZCZECIN_GLOWNY,
        destination_xy=BERLIN_GESUNDBRUNNEN,
        minutes=120,
    )
    assert pricing.price_rail_leg(leg, DiscountProfile()).carrier is Carrier.INTERNATIONAL_PL_DE


def test_udzial_niemiecki_szczecin_berlin_liczony_przez_przejscie_kolo_szczecina():
    leg = _leg(
        LegMode.RAIL,
        "Szczecin Główny",
        "Berlin Gesundbrunnen",
        carrier="PKP Intercity",
        origin_xy=SZCZECIN_GLOWNY,
        destination_xy=BERLIN_GESUNDBRUNNEN,
    )
    # przez Frankfurt (Oder) wychodziło ok. 0,4; granica jest kilkanaście km od Szczecina
    assert pricing.german_portion_fraction(leg) > 0.8


# --- S4: miasto po geografii / całych słowach, nie fragmentach -------------------------------


def test_krakowskie_przedmiescie_w_warszawie_to_ztm_warszawa():
    leg = _leg(
        LegMode.BUS,
        "Krakowskie Przedmieście",
        "Plac Zamkowy",
        carrier="ZTM Warszawa",
        origin_xy=WARSZAWA_KRAKOWSKIE_PRZEDMIESCIE,
        destination_xy=WARSZAWA_PLAC_ZAMKOWY,
        extra={"motis_mode": "BUS"},
    )
    assert pricing.price_bus_leg(leg).carrier is Carrier.ZTM_WARSZAWA


def test_krakowskie_przedmiescie_w_lublinie_to_ztm_lublin():
    leg = _leg(
        LegMode.BUS,
        "Krakowskie Przedmieście",
        "Plac Litewski",
        carrier="ZTM",
        origin_xy=LUBLIN_KRAKOWSKIE_PRZEDMIESCIE,
        destination_xy=LUBLIN_PLAC_LITEWSKI,
        extra={"motis_mode": "BUS"},
    )
    assert pricing.price_bus_leg(leg).carrier is Carrier.ZTM_LUBLIN


def test_bez_wspolrzednych_fragment_nazwy_nie_wybiera_miasta():
    for origin, destination in (
        ("Krakowskie Przedmieście", "Plac Zamkowy"),
        ("Berliner Straße", "Markt"),
        ("Poznańska", "Rondo"),
        ("Kölner Straße", "Rathaus"),
    ):
        leg = _leg(LegMode.BUS, origin, destination, extra={"motis_mode": "BUS"})
        priced = pricing.price_bus_leg(leg)
        assert priced.carrier is None, origin
        assert priced.breakdown["price_verified"] is False


def test_bez_wspolrzednych_cale_slowo_nadal_dziala():
    leg = _leg(LegMode.BUS, "Kraków Główny", "Rondo Mogilskie", carrier="MPK S.A. w Krakowie")
    assert pricing.price_bus_leg(leg).carrier is Carrier.MPK_KRAKOW


def test_wspolrzedne_wygrywaja_z_nazwa():
    # Nazwa "Berlin" w przystanku, ale oba końce w Dreźnie -> to nie BVG.
    leg = _leg(
        LegMode.BUS,
        "Berliner Platz",
        "Berlin-Str.",
        carrier="DVB",
        origin_xy=DRESDEN_HBF,
        destination_xy=DRESDEN_NEUSTADT,
    )
    assert pricing.price_bus_leg(leg).carrier is None


def test_vbb_w_nazwie_nie_oznacza_berlina():
    leg = _leg(LegMode.BUS, "Cottbus Hbf", "Stadtmitte", carrier="VBB")
    assert pricing.price_bus_leg(leg).carrier is not Carrier.BVG_BERLIN
