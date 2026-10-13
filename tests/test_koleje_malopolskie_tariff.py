"""Koleje Małopolskie: Tabela nr 1 taryfy TP-KMŁ (30 pasm, bilet jednorazowy normalny, 2. klasa,
pociąg osobowy; Załącznik nr 2 do Uchwały Zarządu nr 43/2026 z 17.03.2026).

Wszystkie kwoty pochodzą z raportu Gemini z 2026-10-12 (research/km-malopolskie.md, gałąź
gemini/km-malopolskie) i mają status "wg Gemini, niezweryfikowane niezależnie" — domeny przewoźników
są z chmury zablokowane. Raport nie podaje daty wejścia w życie (w danych: null). Dlatego
price_verified=False i PriceType.ESTIMATE, dopóki w danych nie zmieni się status pasma na inny.

Koleje Mazowieckie mają osobny moduł i testy (tests/test_koleje_mazowieckie_tariff.py); tu tylko brak konfliktu.
"""

import json
from datetime import datetime, timedelta

import pytest

from fares import koleje_malopolskie
from fares._data_loading import load
from fares.calculator import estimate_price
from fares.model import Carrier, DiscountProfile, PriceType, Segment
from routing import motis_client, pricing
from routing.model import Leg, LegMode

STATUS = "wg Gemini, niezweryfikowane niezależnie"
URL = "https://kolejemalopolskie.com.pl/brepo/panel_repo/2026/03/19/cpt2dx/taryfa-przewozowa-kml-zm8-ost.pdf"

KRAKOW_GLOWNY = (50.0680, 19.9475)
TARNOW = (50.0120, 20.9860)
WARSZAWA_ZACHODNIA = (52.2194, 20.9657)
RADOM = (51.4027, 21.1471)
LUBLIN_GLOWNY = (51.2297, 22.5745)
DEBLIN = (51.5640, 21.8473)

# 30 pasm Tabeli nr 1 przepisanych z raportu: (górna granica km, cena brutto w zł).
KML_PASMA = [
    (5, 8.00), (10, 8.60), (15, 9.80), (20, 11.70), (25, 13.60), (30, 14.50), (35, 16.50),
    (40, 18.00), (47, 20.00), (53, 22.20), (59, 23.70), (67, 24.70), (73, 25.60), (80, 27.60),
    (90, 29.50), (100, 31.30), (120, 35.30), (140, 37.60), (160, 40.20), (180, 42.00),
    (200, 43.70), (240, 45.60), (280, 47.70), (320, 49.60), (360, 50.50), (400, 52.30),
    (500, 54.50), (600, 57.00), (700, 59.40), (800, 62.40),
]  # fmt: skip

KML = load("koleje_malopolskie.json")


def _segment(km, ulga="brak", *, po_torach=False, source=None):
    return Segment(
        carrier=Carrier.KOLEJE_MALOPOLSKIE,
        origin="A",
        destination="B",
        distance_km=km,
        discounts=DiscountProfile(pkp_ulga_kod=ulga),
        distance_along_track=po_torach,
        distance_source=source,
    )


def _leg(
    carrier,
    origin="Kraków Główny",
    destination="Tarnów",
    origin_xy=KRAKOW_GLOWNY,
    destination_xy=TARNOW,
    *,
    mode=LegMode.RAIL,
    distance_km="prosta",
    extra=None,
):
    depart = datetime(2026, 10, 20, 8, 0)
    leg_extra = {}
    if origin_xy and destination_xy:
        leg_extra.update(
            origin_lat=origin_xy[0],
            origin_lon=origin_xy[1],
            destination_lat=destination_xy[0],
            destination_lon=destination_xy[1],
        )
    leg_extra.update(extra or {})
    if distance_km == "prosta":
        distance_km = motis_client.haversine_km(*origin_xy, *destination_xy)
    return Leg(
        mode=mode,
        origin_name=origin,
        destination_name=destination,
        depart=depart,
        arrive=depart + timedelta(minutes=45),
        carrier_name=carrier,
        distance_km=distance_km,
        extra=leg_extra,
    )


# --- dane ----------------------------------------------------------------------------------


def test_dane_30_pasm_zgodne_z_raportem():
    assert len(KML["pasma_odleglosci_km"]) == 30
    assert [(b["do_km"], b["cena"]) for b in KML["pasma_odleglosci_km"]] == KML_PASMA


def test_dane_tabela_rosnaca_i_bez_dziur():
    do = [b["do_km"] for b in KML["pasma_odleglosci_km"]]
    ceny = [b["cena"] for b in KML["pasma_odleglosci_km"]]
    assert do == sorted(do) and len(set(do)) == len(do)
    assert ceny == sorted(ceny) and len(set(ceny)) == len(ceny)


def test_dane_zrodlo_cytat_data_i_status_gemini():
    z = KML["zrodlo"]
    assert z["url"] == URL
    assert "Uchwały Zarządu" in z["dokument"] and "43/2026" in z["dokument"]
    assert "17 marca 2026" in z["dokument"]
    assert "taryfy normalnej" in z["cytat"] and "8% VAT" in z["cytat"]
    assert z["data_weryfikacji"] == "2026-10-12"
    assert z["status"] == STATUS
    assert KML["weryfikacja"]["status"] == STATUS
    assert STATUS in KML["_status_weryfikacji"]
    assert URL in KML["_zrodlo"]


def test_dane_kazde_pasmo_ma_zrodlo_date_i_status_gemini():
    for b in KML["pasma_odleglosci_km"]:
        c = b["potwierdzone"]
        assert c["zrodlo_url"] == URL
        assert c["data"] == "2026-10-12"
        assert c["status"] == STATUS


def test_dane_brak_daty_wejscia_w_zycie_zapisany_jawnie_jako_brak():
    assert "obowiazuje_od" in KML and KML["obowiazuje_od"] is None
    assert "brak" in KML["obowiazuje_od_status"]
    assert "NIEZWERYFIKOWANE" in KML["obowiazuje_od_status"]


def test_dane_zakres_i_granica_pasma_sa_spojne():
    # "zakres" to napis z raportu ("do 5", "6-10", ...): jego górna liczba = do_km.
    for b in KML["pasma_odleglosci_km"]:
        assert int(b["zakres"].replace("do ", "").split("-")[-1]) == b["do_km"], b


def test_dane_zapisane_jako_tabela_nr_1_klasa_2_z_vat():
    assert KML["klasa"] == 2 and KML["waluta"] == "PLN"
    assert "Tabela nr 1" in KML["_zrodlo"]
    assert "Kraków Lotnisko" in KML["_uwaga"]
    assert "8% VAT" in KML["_uwaga"]


# --- kalkulator: pasma ---------------------------------------------------------------------


@pytest.mark.parametrize("do_km, cena", KML_PASMA)
def test_gorna_granica_kazdego_pasma(do_km, cena):
    assert koleje_malopolskie.estimate(_segment(do_km)).amount == cena


@pytest.mark.parametrize(
    "km, oczekiwana",
    [
        (0.1, 8.00),
        (5, 8.00),  # granica: do 5 km włącznie
        (5.1, 8.60),  # km taryfowe zaokrąglamy w górę -> 6 km
        (6, 8.60),
        (10, 8.60),
        (11, 9.80),
        (47, 20.00),
        (47.2, 22.20),  # 48 km: pasmo 48-53
        (48, 22.20),
        (53, 22.20),
        (54, 23.70),
        (60, 24.70),  # pasmo 60-67 zaczyna się tuż po 54-59
        (67, 24.70),
        (68, 25.60),
        (73, 25.60),
        (74, 27.60),
        (80, 27.60),
        (81, 29.50),
        (90, 29.50),
        (91, 31.30),
        (100, 31.30),
        (100.4, 35.30),  # 101 km: pasmo 101-120
        (101, 35.30),
        (200, 43.70),
        (201, 45.60),
        (400, 52.30),
        (401, 54.50),
        (800, 62.40),
    ],
)
def test_pasma_graniczne(km, oczekiwana):
    assert koleje_malopolskie.estimate(_segment(km)).amount == oczekiwana


def test_do_5_km_kosztuje_8_zl():
    est = koleje_malopolskie.estimate(_segment(4.2))
    assert est.amount == 8.00
    assert est.currency == "PLN"
    assert est.breakdown["pasmo_do_km"] == 5


def test_91_100_km_kosztuje_31_30_zl():
    for km in (91, 95.5, 100):
        est = koleje_malopolskie.estimate(_segment(km))
        assert est.amount == 31.30
        assert est.breakdown["pasmo_do_km"] == 100


def test_powyzej_800_km_blad():
    with pytest.raises(ValueError, match="brak pasma"):
        koleje_malopolskie.estimate(_segment(801))


def test_brak_dystansu_to_blad():
    with pytest.raises(ValueError, match="distance_km"):
        koleje_malopolskie.estimate(_segment(None))


def test_nie_przyjmuje_innego_przewoznika():
    seg = _segment(10)
    seg.carrier = Carrier.POLREGIO_PODSTAWOWA
    with pytest.raises(ValueError, match="przewoźnik"):
        koleje_malopolskie.estimate(seg)


def test_nieznany_kod_ulgi_to_blad():
    with pytest.raises(ValueError, match="nieznany kod ulgi"):
        koleje_malopolskie.estimate(_segment(10, "nie_ma_takiej_ulgi"))


def test_calculator_dispatch_po_carrierze():
    assert estimate_price(_segment(13)).amount == 9.80


# --- kalkulator: status, szacunek, przełącznik ----------------------------------------------


def test_linia_prosta_to_szacunek_niepotwierdzony_z_opisem_i_zrodlem():
    est = koleje_malopolskie.estimate(_segment(20))
    assert est.price_type is PriceType.ESTIMATE
    b = est.breakdown
    assert b["price_verified"] is False
    assert b["odleglosc_taryfowa"] == "linia prosta"
    assert b["status_weryfikacji"] == STATUS
    assert "Gemini" in b["powod_szacunku"]
    assert b["zrodlo_url"] == URL
    assert b["data_weryfikacji"] == "2026-10-12"
    assert b["obowiazuje_od"] is None
    assert "linii prostej" in est.notes
    assert STATUS in est.notes
    assert URL in est.notes
    assert "brak w raporcie" in est.notes  # data wejścia w życie
    assert "Kraków Lotnisko" in est.notes


def test_km_po_torach_bez_drugiego_zrodla_to_nadal_szacunek_niepotwierdzony():
    est = koleje_malopolskie.estimate(_segment(20, po_torach=True, source="legGeometry MOTIS"))
    assert est.amount == 11.70
    assert est.price_type is PriceType.ESTIMATE
    assert est.breakdown["price_verified"] is False
    assert est.breakdown["odleglosc_taryfowa"] == "po torach"
    assert est.breakdown["zrodlo_km"] == "legGeometry MOTIS"
    assert "linii prostej" not in est.notes
    assert "legGeometry MOTIS" in est.notes


def _tabela_z_drugim_zrodlem():
    """Kopia tabeli KMŁ, w której każde pasmo ma status inny niż „wg Gemini, niezweryfikowane”."""
    tabela = json.loads(json.dumps(KML))
    for b in tabela["pasma_odleglosci_km"]:
        b["potwierdzone"]["status"] = "potwierdzone w drugim niezależnym źródle"
    return tabela


def test_przelacznik_w_danych_status_inny_niz_gemini_przywraca_official():
    tabela = _tabela_z_drugim_zrodlem()
    po_torach = koleje_malopolskie.estimate(_segment(20, po_torach=True), tabela)
    assert po_torach.amount == 11.70
    assert po_torach.breakdown["price_verified"] is True
    assert "powod_szacunku" not in po_torach.breakdown
    assert po_torach.price_type is PriceType.OFFICIAL
    prosta = koleje_malopolskie.estimate(_segment(20), tabela)
    assert prosta.breakdown["price_verified"] is True
    assert prosta.price_type is PriceType.ESTIMATE  # linia prosta zawsze szacunek


def test_przelacznik_dziala_per_pasmo():
    tabela = json.loads(json.dumps(KML))
    tabela["pasma_odleglosci_km"][3]["potwierdzone"]["status"] = "potwierdzone w PDF"  # 16-20 km
    zweryfikowane = koleje_malopolskie.estimate(_segment(18, po_torach=True), tabela)
    assert zweryfikowane.price_type is PriceType.OFFICIAL
    inne = koleje_malopolskie.estimate(_segment(30, po_torach=True), tabela)
    assert inne.price_type is PriceType.ESTIMATE and inne.breakdown["price_verified"] is False


def test_pasmo_bez_zrodla_w_danych_jest_niepotwierdzone_nawet_przy_innym_statusie():
    tabela = _tabela_z_drugim_zrodlem()
    tabela["pasma_odleglosci_km"][0]["potwierdzone"] = None
    est = koleje_malopolskie.estimate(_segment(3, po_torach=True), tabela)
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE
    assert "pasmo niepotwierdzone" in est.breakdown["powod_szacunku"]
    assert "NIEPOTWIERDZONA" in est.notes


def test_ulgi_nie_sa_modelowane_cena_normalna_i_niepotwierdzona():
    est = koleje_malopolskie.estimate(
        _segment(20, "student_do_26_lat_doktorant_do_35_lat", po_torach=True)
    )
    assert est.amount == 11.70  # cena normalna, bez procentu "z głowy"
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE
    assert "Ulgi KMŁ nie są modelowane" in est.notes


def test_ulgi_nie_sa_potwierdzone_nawet_po_drugim_zrodle_kwot_normalnych():
    est = koleje_malopolskie.estimate(
        _segment(20, "student_do_26_lat_doktorant_do_35_lat", po_torach=True),
        _tabela_z_drugim_zrodlem(),
    )
    assert est.amount == 11.70
    assert est.breakdown["price_verified"] is False
    assert est.price_type is PriceType.ESTIMATE
    assert "ulgi KMŁ nie są modelowane" in est.breakdown["powod_szacunku"]


def test_data_wejscia_w_zycie_gdy_znana_trafia_do_opisu():
    tabela = json.loads(json.dumps(KML))
    tabela["obowiazuje_od"] = "2026-04-01"  # tylko fixture testowa, nie dane cenowe
    est = koleje_malopolskie.estimate(_segment(20), tabela)
    assert est.breakdown["obowiazuje_od"] == "2026-04-01"
    assert "od 2026-04-01" in est.notes
    assert "brak w raporcie" not in est.notes


# --- rozpoznawanie przewoźnika ---------------------------------------------------------------


@pytest.mark.parametrize(
    "nazwa",
    [
        "Koleje Małopolskie",
        "KOLEJE MAŁOPOLSKIE",
        "koleje małopolskie",
        "Koleje Małopolskie sp. z o.o.",
        "Koleje  Małopolskie",  # podwójna spacja
        " Koleje Małopolskie ",
        "Koleje Malopolskie",  # bez polskich znaków
        "Koleje Małopolskie (KMŁ)",
        "KMŁ",
        "KML",
    ],
)
def test_rozpoznaje_koleje_malopolskie_po_nazwie_z_motis(nazwa):
    leg = _leg(nazwa)
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.KOLEJE_MALOPOLSKIE
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MALOPOLSKIE
    assert priced.price_type == "szacunek"
    assert priced.price_verified is False


@pytest.mark.parametrize(
    "nazwa",
    [
        "Koleje Mazowieckie",
        "KM",  # Koleje Mazowieckie
        "WKD",
        "Koleje Śląskie",
        "Koleje Dolnośląskie",
        "POLREGIO",
        "PKP Intercity",
        "Łódzka Kolej Aglomeracyjna",
        "SKM",
        "Koleje Wielkopolskie",
        "Małopolska Agencja Rozwoju",  # samo "małopolska" nie wystarcza
        "KMK",  # komunikacja miejska w Krakowie, nie KMŁ
        "KMŁx",
    ],
)
def test_inni_przewoznicy_nie_sa_rozpoznawani_jako_kml(nazwa):
    leg = _leg(nazwa)
    assert pricing.infer_pl_local_rail_carrier(leg) is not Carrier.KOLEJE_MALOPOLSKIE


def test_km_koleje_mazowieckie_nie_jest_mylone_z_kml_ani_odwrotnie():
    kml = _leg("Koleje Małopolskie")
    km = _leg("Koleje Mazowieckie", "Warszawa Zachodnia", "Radom", WARSZAWA_ZACHODNIA, RADOM)
    assert not pricing._is_km_or_wkd(kml)
    assert pricing._is_koleje_malopolskie(kml)
    assert pricing._is_km_or_wkd(km)
    assert not pricing._is_koleje_malopolskie(km)


def test_koleje_mazowieckie_nie_dostaja_tabeli_kml():
    leg = _leg("Koleje Mazowieckie", "Warszawa Zachodnia", "Radom", WARSZAWA_ZACHODNIA, RADOM)
    assert pricing.infer_pl_local_rail_carrier(leg) is Carrier.KOLEJE_MAZOWIECKIE


def test_kml_w_trybie_suburban_dostaje_tabele_a_autobus_kml_nie():
    pociag = _leg("Koleje Małopolskie", mode=LegMode.BUS, extra={"motis_mode": "SUBURBAN"})
    assert pricing.infer_pl_local_rail_carrier(pociag) is Carrier.KOLEJE_MALOPOLSKIE
    assert pricing.price_leg(pociag, DiscountProfile()).carrier is Carrier.KOLEJE_MALOPOLSKIE
    autobus = _leg("Koleje Małopolskie", mode=LegMode.BUS, extra={"motis_mode": "BUS"})
    assert pricing.infer_pl_local_rail_carrier(autobus) is None


@pytest.mark.parametrize(
    "origin, destination",
    [("Kraków Główny", "Kraków Lotnisko"), ("Kraków Lotnisko", "Kraków Główny")],
)
def test_odcinek_do_z_krakow_lotnisko_nie_dostaje_tabeli(origin, destination):
    # Tabela nr 1 nie obowiązuje do/z Kraków Lotnisko (raport Gemini) -> niepotwierdzony szacunek.
    leg = _leg("Koleje Małopolskie", origin, destination, distance_km=12.0)
    assert pricing.infer_pl_local_rail_carrier(leg) is None
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.price_verified is False
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * 12.0, 2)


# --- brak konfliktu z POLREGIO ---------------------------------------------------------------


def test_polregio_w_malopolsce_dalej_taryfa_podstawowa_nie_kml():
    leg = _leg("POLREGIO")
    assert pricing.infer_pl_regional_carrier(leg) is Carrier.POLREGIO_PODSTAWOWA
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.POLREGIO_PODSTAWOWA
    assert priced.carrier is not Carrier.KOLEJE_MALOPOLSKIE


def test_ta_sama_trasa_dwoch_przewoznikow_dwie_rozne_tabele():
    # Kraków Główny - Tarnów (linia prosta ok. 74,5 km -> 75 km): KMŁ pasmo 74-80 = 27,60 zł.
    kml = pricing.price_rail_leg(_leg("Koleje Małopolskie"), DiscountProfile())
    pol = pricing.price_rail_leg(_leg("POLREGIO"), DiscountProfile())
    assert (kml.carrier, kml.amount) == (Carrier.KOLEJE_MALOPOLSKIE, 27.60)
    assert pol.carrier is Carrier.POLREGIO_PODSTAWOWA
    assert pol.breakdown.get("pasmo_do_km") is not None
    assert "TP-KMŁ" in kml.notes and "TP-KMŁ" not in pol.notes


def test_kml_nie_trafia_do_regionalnych_slow_kluczowych_polregio():
    assert not any("małopolsk" in k or "malopolsk" in k for k in pricing.PL_REGIONAL_RAIL_KEYWORDS)
    assert pricing.infer_pl_regional_carrier(_leg("Koleje Małopolskie")) is None


def test_polregio_nie_zmienilo_wynikow_dla_danych_polregio():
    polregio = load("polregio_taryfa_podstawowa.json")
    assert len(polregio["pasma_odleglosci_km"]) == 30
    assert polregio["pasma_odleglosci_km"][0]["cena"] != KML["pasma_odleglosci_km"][0]["cena"]


# --- routing: km po torach i linia prosta -----------------------------------------------------


def test_routing_linia_prosta_gdy_brak_km_po_torach():
    leg = _leg("Koleje Małopolskie", distance_km=13.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MALOPOLSKIE
    assert priced.breakdown["odleglosc_taryfowa"] == "linia prosta"
    assert priced.price_type == "szacunek"
    assert "linii prostej" in priced.notes


def test_routing_uzywa_km_po_torach_z_extra_gdy_sa_dostepne():
    # Linia prosta 17,4 km -> pasmo 16-20 (11,70 zł); po torach 21,3 km -> pasmo 21-25 (13,60 zł).
    wspolne = dict(distance_km=17.4)
    prosta = _leg("Koleje Małopolskie", **wspolne)
    po_torach = _leg(
        "Koleje Małopolskie",
        extra={
            "distance_along_track_km": 21.3,
            "distance_along_track_source": "legGeometry MOTIS",
        },
        **wspolne,
    )
    a = pricing.price_rail_leg(prosta, DiscountProfile())
    b = pricing.price_rail_leg(po_torach, DiscountProfile())
    assert (a.amount, a.price_type) == (11.70, "szacunek")
    assert (b.amount, b.price_type) == (13.60, "szacunek")  # Gemini, bez drugiego źródła
    assert b.price_verified is False
    assert b.breakdown["odleglosc_taryfowa"] == "po torach"
    assert b.breakdown["zrodlo_km"] == "legGeometry MOTIS"
    assert "legGeometry MOTIS" in b.notes


@pytest.mark.parametrize("zla_wartosc", [0, -3.0, True, None, "21"])
def test_routing_ignoruje_niepoprawne_km_po_torach(zla_wartosc):
    leg = _leg(
        "Koleje Małopolskie",
        distance_km=17.4,
        extra={"distance_along_track_km": zla_wartosc},
    )
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.amount == 11.70
    assert priced.breakdown["odleglosc_taryfowa"] == "linia prosta"


def test_routing_bez_dystansu_to_niepotwierdzony_fallback():
    leg = _leg("Koleje Małopolskie", distance_km=None)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_verified is False
    assert priced.price_type == "szacunek"
    assert "distance_km jest wymagane" in priced.breakdown["powod_szacunku"]


def test_routing_odcinek_dluzszy_niz_800_km_to_fallback():
    leg = _leg("Koleje Małopolskie", distance_km=850.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.price_verified is False
    assert priced.amount == round(pricing.GENERIC_FALLBACK_PLN_PER_KM * 850.0, 2)


def test_odcinek_transgraniczny_kml_nie_dostaje_polskiej_tabeli():
    berlin = (52.5251, 13.3694)
    leg = _leg("Koleje Małopolskie", "Kraków Główny", "Berlin Hbf", KRAKOW_GLOWNY, berlin)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is None
    assert priced.price_verified is False


# --- przykład: Stróże -> Gorlice ---------------------------------------------------------------


def test_przyklad_struze_gorlice_okolo_13_km():
    # Odległość ok. 13 km podana w zadaniu (NIE z raportu, raport jej nie zawiera): pasmo 11-15 km.
    # Raport potwierdza, że KMŁ obsługują Gorlice w relacji Kraków - Jasło (K7/K71).
    leg = _leg("Koleje Małopolskie", "Stróże", "Gorlice", None, None, distance_km=13.0)
    priced = pricing.price_rail_leg(leg, DiscountProfile())
    assert priced.carrier is Carrier.KOLEJE_MALOPOLSKIE
    assert (priced.amount, priced.currency) == (9.80, "PLN")
    assert priced.breakdown["pasmo_do_km"] == 15
    assert priced.breakdown["pasmo"] == "11-15"
    assert priced.price_type == "szacunek"
    assert priced.price_verified is False
    assert priced.breakdown["status_weryfikacji"] == STATUS
    assert STATUS in priced.notes


def test_przyklad_struze_gorlice_pasmo_zalezy_od_km_po_torach():
    # Ta sama relacja z km po torach 15,4 (hipotetyczne, test mechanizmu) wypada już w pasmie 16-20.
    leg = _leg(
        "Koleje Małopolskie",
        "Stróże",
        "Gorlice",
        None,
        None,
        distance_km=13.0,
        extra={"distance_along_track_km": 15.4, "distance_along_track_source": "test"},
    )
    assert pricing.price_rail_leg(leg, DiscountProfile()).amount == 11.70
