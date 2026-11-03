from datetime import datetime, timedelta

import pytest

from fares.international import estimate as international_estimate
from fares.international_pkp import estimate_pkp_offer
from fares.model import Carrier, DiscountProfile, Segment
from routing.model import Leg, LegMode
from routing.pricing import is_cross_border_pl_de, price_rail_leg

WARSZAWA = {"lat": 52.2288, "lon": 21.0034}
BERLIN = {"lat": 52.5251, "lon": 13.3694}
LUBLIN = {"lat": 51.2465, "lon": 22.5684}
GELSENKIRCHEN = {"lat": 51.5177, "lon": 7.0857}


def _leg(
    origin_stop_id,
    destination_stop_id,
    distance_km=500.0,
    carrier_name="PKP Intercity",
    origin_latlon=None,
    destination_latlon=None,
):
    depart = datetime(2026, 10, 1, 8, 0)
    extra = {"origin_stop_id": origin_stop_id, "destination_stop_id": destination_stop_id}
    if origin_latlon:
        extra["origin_lat"], extra["origin_lon"] = origin_latlon["lat"], origin_latlon["lon"]
    if destination_latlon:
        extra["destination_lat"], extra["destination_lon"] = (
            destination_latlon["lat"],
            destination_latlon["lon"],
        )
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


# Bez german_portion_fraction (brak współrzędnych) -> fallback: rabat 25% od CAŁEJ ceny.
# To zawyża realny rabat (oficjalnie dotyczy tylko niemieckiego odcinka trasy) — patrz testy
# "..._proporcjonalnie_do_niemieckiego_odcinka" niżej dla poprawnego, geografia-aware liczenia.


def test_bahncard_25_bez_wspolrzednych_daje_25_procent_od_calej_ceny_fallback():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(bahncard="25"),
    )
    assert international_estimate(seg).amount == pytest.approx(29.99 * 0.75, abs=0.01)


def test_bahncard_50_bez_wspolrzednych_daje_25_procent_od_calej_ceny_fallback():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(bahncard="50"),
    )
    assert international_estimate(seg).amount == pytest.approx(29.99 * 0.75, abs=0.01)


def test_bahncard_100_bez_wspolrzednych_daje_25_procent_nie_100_procent_fallback():
    # ZGŁOSZONY BUG (2026-09-29): BahnCard 100 zerowała całą cenę biletu (0.00 EUR) bo
    # traktowaliśmy ją jako 100% rabatu, analogicznie do krajowych biletów Sparpreis. Dla
    # Super Sparpreis Europa (bahn.de FAQ + bahnpedia.de) WSZYSTKIE poziomy BahnCard dają
    # nominalnie tę samą zniżkę 25% — BahnCard 100 nie daje tu przejazdu za darmo.
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(bahncard="100"),
    )
    assert international_estimate(seg).amount == pytest.approx(29.99 * 0.75, abs=0.01)


def test_bahncard_z_udzialem_niemieckiego_odcinka_liczy_rabat_tylko_od_tej_czesci():
    # ZGŁOSZONE DOPRECYZOWANIE (2026-09-29, źródło int.bahn.de/pl): BahnCard oficjalnie daje
    # rabat TYLKO na niemiecki odcinek trasy, nie na całą cenę. Gdy znamy geograficzny udział
    # tego odcinka (patrz routing/pricing.py::german_portion_fraction), efektywny rabat na
    # całą cenę biletu to rabat_nominalny * udział, NIE cały rabat_nominalny.
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(bahncard="50"),
        german_portion_fraction=0.2,
    )
    result = international_estimate(seg)
    # 25% nominalnego rabatu * 20% udziału niemieckiego odcinka = 5% efektywnego rabatu na całość
    assert result.amount == pytest.approx(29.99 * 0.95, abs=0.01)
    assert result.breakdown["rabat_procent_efektywny"] == pytest.approx(5.0, abs=0.1)


def test_brak_bahncard_ignoruje_udzial_niemieckiego_odcinka():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        german_portion_fraction=0.2,
    )
    assert international_estimate(seg).amount == 29.99


def test_bledny_przewoznik_podnosi_blad():
    with pytest.raises(ValueError):
        international_estimate(Segment(Carrier.DB, "Berlin", "Warszawa", distance_km=519))


# --- taryfa "Super Sparpreis Europa Young" (15-26 lat, bahn.de) ---------------------------
#
# ZNALEZIONA DZIURA (audyt zniżek, 2026-10-07): DiscountProfile.age istniał wcześniej TYLKO
# jako parametr sugestii zakupu BahnCard (routing/card_suggestions.py) — nigdy nie wpływał na
# cenę biletu. Dla 15-26 lat bahn.de sprzedaje odrębną, dużo tańszą taryfę "Super Sparpreis
# Europa Young" z JEDNĄ ceną "od" (18.99 EUR) dla WSZYSTKICH relacji — w przeciwieństwie do
# wersji dla dorosłych, która ma 3 progi zależne od odległości. Testy niżej sprawdzają granice
# przedziału wiekowego (14/15/25/26/27) i współdziałanie z BahnCard.


@pytest.mark.parametrize("age", [15, 20, 26])
def test_wiek_w_przedziale_young_dostaje_cene_young_niezaleznie_od_dystansu(age):
    for distance_km in (240, 519, 532):  # krótka / średnia / długa relacja dla dorosłych
        seg = Segment(
            Carrier.INTERNATIONAL_PL_DE,
            "Berlin",
            "X",
            distance_km=distance_km,
            discounts=DiscountProfile(age=age),
        )
        result = international_estimate(seg)
        assert result.amount == 18.99
        assert result.breakdown["kategoria_relacji"] == "young"


@pytest.mark.parametrize("age", [27, 60])
def test_wiek_poza_przedzialem_dziecko_young_dostaje_normalna_taryfe_wg_progu_km(age):
    # 60 lat: brak osobnej taryfy seniora na TEJ ofercie (zweryfikowane 2026-10-09 — "Super
    # Sparpreis Senioren" 65+ to inny, wyłącznie krajowy produkt DB) — normalna taryfa jak każdy dorosły.
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=age),
    )
    result = international_estimate(seg)
    assert result.amount == 29.99
    assert result.breakdown["kategoria_relacji"] == "srednia"


def test_brak_wieku_dostaje_normalna_taryfe():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin", "Warszawa", distance_km=519)
    result = international_estimate(seg)
    assert result.amount == 29.99


# --- rabat dziecięcy DB (bahn.de, zweryfikowane NA ŻYWO 2026-10-09) -----------------------
#
# ROZSTRZYGNIĘCIE 2026-10-09: ta sama strona co źródło BahnCard/Young (super-sparpreis-europa-
# polen) ma TEŻ zasady dla dzieci, których wcześniej nie modelowaliśmy: do 5 lat zawsze gratis,
# 6-14 lat gratis Z opiekunem (zgłoszonym przy rezerwacji), 6-14 lat SAMODZIELNIE -50% ale TYLKO
# na niemiecki odcinek trasy (jak BahnCard).


@pytest.mark.parametrize("age", [0, 3, 5])
def test_dziecko_do_5_lat_zawsze_gratis(age):
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=age),
    )
    result = international_estimate(seg)
    assert result.amount == 0.0
    assert result.breakdown["kategoria_relacji"] == "niemowle"


@pytest.mark.parametrize("age", [6, 10, 14])
def test_dziecko_6_14_lat_z_opiekunem_gratis(age):
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=age, child_with_guardian=True),
    )
    result = international_estimate(seg)
    assert result.amount == 0.0
    assert result.breakdown["kategoria_relacji"] == "dziecko_z_opiekunem"


def test_dziecko_6_14_lat_samodzielnie_bez_wspolrzednych_50_procent_fallback():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=10),
    )
    result = international_estimate(seg)
    assert result.amount == pytest.approx(29.99 * 0.5, abs=0.01)
    assert result.breakdown["kategoria_relacji"] == "dziecko_samodzielnie"


def test_dziecko_6_14_lat_samodzielnie_domyslnie_bez_opiekuna():
    # child_with_guardian domyślnie False — dziecko bez jawnie zgłoszonego opiekuna liczone jako
    # podróżujące samodzielnie (bezpieczniejszy domyślny wybór, nie zakłada opiekuna na wyrost).
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=10),
    )
    assert DiscountProfile().child_with_guardian is False
    result = international_estimate(seg)
    assert result.breakdown["kategoria_relacji"] == "dziecko_samodzielnie"


def test_dziecko_6_14_lat_samodzielnie_z_wspolrzednymi_liczy_proporcjonalnie():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=10),
        german_portion_fraction=0.2,
    )
    result = international_estimate(seg)
    # 50% nominalnego rabatu * 20% udziału niemieckiego odcinka = 10% efektywnego rabatu na całość
    assert result.amount == pytest.approx(29.99 * 0.9, abs=0.01)
    assert result.breakdown["rabat_procent_efektywny"] == pytest.approx(10.0, abs=0.1)


def test_young_z_bahncard_25_bez_wspolrzednych_daje_25_procent_od_calej_ceny_fallback():
    # Ta sama zasada "BahnCard = 25% nominalnie, niezależnie od poziomu karty" dotyczy Young
    # (bahn.de, dosłowny cytat identyczny jak dla dorosłych — zob. _zrodlo_young w danych).
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=16, bahncard="25"),
    )
    result = international_estimate(seg)
    assert result.amount == pytest.approx(18.99 * 0.75, abs=0.01)


def test_young_z_bahncard_i_wspolrzednymi_liczy_rabat_proporcjonalnie_do_niemieckiego_odcinka():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=16, bahncard="50"),
        german_portion_fraction=0.2,
    )
    result = international_estimate(seg)
    # 25% nominalnego rabatu * 20% udziału niemieckiego odcinka = 5% efektywnego rabatu
    assert result.amount == pytest.approx(18.99 * 0.95, abs=0.01)
    assert result.breakdown["rabat_procent_efektywny"] == pytest.approx(5.0, abs=0.1)


def test_young_bez_bahncard_ignoruje_udzial_niemieckiego_odcinka():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Berlin",
        "Warszawa",
        distance_km=519,
        discounts=DiscountProfile(age=16),
        german_portion_fraction=0.2,
    )
    assert international_estimate(seg).amount == 18.99


# --- routing/pricing.py::price_rail_leg — międzynarodowy leg wymusza Carrier.INTERNATIONAL_PL_DE


def test_price_rail_leg_wymusza_taryfe_miedzynarodowa_dla_odcinka_z_niemiecka_stacja_w_polskim_feedzie():
    # replika zgłoszonego bugu: oba stopId z prefiksem 'pl_' (Berlin-Lichtenberg opublikowany w
    # polskim feedzie GTFS dla kursu PKP Intercity), rozstrzyga geografia.
    leg = _leg(
        "pl_50500",
        "pl_999999",
        distance_km=519,
        carrier_name="PKP Intercity",
        origin_latlon=WARSZAWA,
        destination_latlon=BERLIN,
    )
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.amount == 29.99


def test_price_rail_leg_wymusza_taryfe_miedzynarodowa_dla_odcinka_przez_granice():
    leg = _leg("pl_50500", "defv_344028", distance_km=519, carrier_name="PKP Intercity")
    priced = price_rail_leg(leg, DiscountProfile())
    # 29.99 EUR (kategoria 'srednia'), NIE krajowa cena PKP wg pasma 519km (byłoby dużo więcej PLN)
    assert priced.currency == "EUR"
    assert priced.amount == 29.99


def test_price_rail_leg_z_bahncard_i_wspolrzednymi_liczy_rabat_proporcjonalnie_nie_flat_25_procent():
    # ZGŁOSZONE DOPRECYZOWANIE (2026-09-29): mając realne współrzędne (Warszawa/Berlin), rabat
    # BahnCard musi być dużo mniejszy niż flat 25% na całą cenę, bo Berlin leży blisko granicy —
    # niemiecki odcinek to tylko ok. 16% dystansu w linii prostej. Efektywny rabat: 25% * ~16% ≈ 4%.
    leg = _leg(
        "pl_50500",
        "pl_999999",
        distance_km=519,
        carrier_name="PKP Intercity",
        origin_latlon=WARSZAWA,
        destination_latlon=BERLIN,
    )
    priced = price_rail_leg(leg, DiscountProfile(bahncard="50"))
    assert priced.currency == "EUR"
    assert 28.0 < priced.amount < 29.99  # rabat realny, ale dużo mniejszy niż 29.99*0.75=22.49


def test_price_rail_leg_krajowy_pkp_dziala_jak_wczesniej():
    leg = _leg("pl_50500", "pl_38653", distance_km=170, carrier_name="PKP Intercity")
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "PLN"
    assert priced.amount == 50  # krajowa tabela pasm PKP, jak w tests/test_fares.py


# --- fares/international_pkp.py: własna oferta PKP Intercity "Polska-Niemcy" -------------------
#
# ROZSTRZYGNIĘCIE 2026-10-09 (user, po pytaniu koordynatora): silnik ma liczyć OBIE oferty na
# bilet PL-DE — pulę DB (Super Sparpreis Europa, powyżej) i własną ofertę PKP Intercity (cennik
# regularny "Oferta Polska-Niemcy", od 19.08.2026) — i pokazywać TAŃSZĄ jako cenę główną, drugą
# jako alternatywę. Patrz fares/data/international_pl_de_pkp.json dla źródeł.


def test_relacja_warszawa_berlin_rozpoznana_cena_69():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Warszawa Centralna", "Berlin Hauptbahnhof")
    result = estimate_pkp_offer(seg)
    assert result is not None
    assert result.amount == 69
    assert result.currency == "EUR"


def test_relacja_dziala_w_obie_strony():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin Hauptbahnhof", "Warszawa Centralna")
    result = estimate_pkp_offer(seg)
    assert result is not None
    assert result.amount == 69


@pytest.mark.parametrize(
    "polskie_miasto,oczekiwana_cena",
    [
        ("Kraków Główny", 69),
        ("Gdynia Główna", 69),
        ("Gdańsk Główny", 69),
        ("Lublin", 79),
        ("Przemyśl Główny", 79),
        ("Poznań Główny", 47),
    ],
)
def test_wszystkie_relacje_z_cennika_rozpoznane(polskie_miasto, oczekiwana_cena):
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, polskie_miasto, "Berlin Hauptbahnhof")
    result = estimate_pkp_offer(seg)
    assert result is not None
    assert result.amount == oczekiwana_cena


def test_relacja_spoza_tabeli_zwraca_none():
    # Szczecin nie jest w tabeli "Oferta Polska-Niemcy" -> brak oferty PKP dla tej relacji.
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Szczecin Główny", "Berlin Hauptbahnhof")
    assert estimate_pkp_offer(seg) is None


def test_oba_konce_berlin_zwraca_none():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Berlin Hauptbahnhof", "Berlin Ostbahnhof")
    assert estimate_pkp_offer(seg) is None


def test_oba_konce_nie_berlin_zwraca_none():
    seg = Segment(Carrier.INTERNATIONAL_PL_DE, "Warszawa Centralna", "Kraków Główny")
    assert estimate_pkp_offer(seg) is None


def test_dziecko_6_14_lat_dostaje_50_procent_rabatu():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Warszawa Centralna",
        "Berlin Hauptbahnhof",
        discounts=DiscountProfile(age=10),
    )
    result = estimate_pkp_offer(seg)
    assert result.amount == pytest.approx(69 * 0.5)
    assert result.breakdown["kategoria_wieku"] == "dziecko"


def test_ponizej_6_lat_przejazd_bezplatny():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Warszawa Centralna",
        "Berlin Hauptbahnhof",
        discounts=DiscountProfile(age=3),
    )
    result = estimate_pkp_offer(seg)
    assert result.amount == 0


def test_dorosly_bez_ulgi_pelna_cena():
    seg = Segment(
        Carrier.INTERNATIONAL_PL_DE,
        "Warszawa Centralna",
        "Berlin Hauptbahnhof",
        discounts=DiscountProfile(age=40),
    )
    result = estimate_pkp_offer(seg)
    assert result.amount == 69
    assert result.breakdown["kategoria_wieku"] == "normalny"


def test_bledny_przewoznik_w_estimate_pkp_offer_podnosi_blad():
    with pytest.raises(ValueError):
        estimate_pkp_offer(Segment(Carrier.DB, "Warszawa Centralna", "Berlin Hauptbahnhof"))


# --- routing/pricing.py::price_rail_leg łączy obie oferty (DB + PKP) i pokazuje tańszą ---------


def _international_leg(origin_name: str, destination_name: str, distance_km: float) -> Leg:
    depart = datetime(2026, 10, 1, 8, 0)
    return Leg(
        mode=LegMode.RAIL,
        origin_name=origin_name,
        destination_name=destination_name,
        depart=depart,
        arrive=depart + timedelta(hours=5),
        carrier_name="PKP Intercity",
        distance_km=distance_km,
        extra={"origin_stop_id": "pl_1", "destination_stop_id": "defv_1"},
    )


def test_price_rail_leg_dziecko_ponizej_6_lat_oba_kanaly_gratis_remis_na_rzecz_pkp():
    # Dziecko poniżej 6 lat jedzie za darmo w OBU kanałach (DB: bahn.de "Kinder bis 5 Jahre fahren
    # immer kostenfrei"; PKP: cennik "Polska-Niemcy" -100%) — remis 0 EUR vs 0 EUR, kod rozstrzyga
    # remisy na rzecz PKP (`<=` w _with_pkp_alternative), ale obie ceny są identyczne.
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    priced = price_rail_leg(leg, DiscountProfile(age=3))
    assert priced.currency == "EUR"
    assert priced.amount == 0
    alt = priced.breakdown.get("alternatywna_oferta")
    assert alt is not None
    assert alt["zrodlo"] == "db"
    assert alt["cena"] == 0


def test_price_rail_leg_pokazuje_tansza_oferte_db_gdy_pkp_drozsza():
    # Warszawa-Berlin, dorosły bez ulg: PKP 69 EUR (cennik regularny) vs DB "średnia" 29.99 EUR
    # -> DB jest wyraźnie tańszy, ma zostać ceną główną, z PKP jako alternatywa w breakdown.
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert priced.amount == 29.99
    alt = priced.breakdown.get("alternatywna_oferta")
    assert alt is not None
    assert alt["zrodlo"] == "pkp_oferta_polska_niemcy"
    assert alt["cena"] == 69


def test_price_rail_leg_relacja_spoza_tabeli_pkp_pokazuje_tylko_db():
    leg = _international_leg("Szczecin Główny", "Berlin Hauptbahnhof", distance_km=150)
    priced = price_rail_leg(leg, DiscountProfile())
    assert priced.currency == "EUR"
    assert "alternatywna_oferta" not in priced.breakdown


# --- PKP Super Promo International: przedział cen (cennik od 19.08.2026) -----------------------
# Wartości przepisane z oryginalny PDF PKP IC (link w źródłach)
# (relacja Berlin, 2. klasa, poziomy I-V). Dane: fares/data/pkp_spi_pl_de.json.

from fares.international_pkp import spi_range  # noqa: E402
from routing.currency import PLACEHOLDER_RATES_TO_PLN  # noqa: E402
from routing.scoring import build_itinerary  # noqa: E402


@pytest.mark.parametrize(
    "miasto,od,do",
    [
        ("Warszawa Centralna", 34.90, 59.90),
        ("Poznań Główny", 24.90, 44.90),
        ("Konin", 27.90, 44.90),
        ("Rzepin", 19.90, 27.90),
        ("Lublin Główny", 34.90, 69.90),  # tylko Ursa 440/441, strefa VI
        ("Kraków Główny", 34.90, 59.90),
    ],
)
def test_spi_range_wartosci_z_pdf(miasto, od, do):
    r = spi_range(miasto, "Berlin Hauptbahnhof")
    assert (r["od"], r["do"]) == (od, do)
    assert r["waluta"] == "EUR"


def test_spi_range_w_obie_strony_i_poza_cennikiem():
    assert spi_range("Berlin Hauptbahnhof", "Warszawa Centralna")["do"] == 59.90
    assert spi_range("Szczecin Główny", "Berlin Hauptbahnhof") is None
    assert spi_range("Berlin Hauptbahnhof", "Hamburg Hbf") is None


def test_price_rail_leg_warszawa_berlin_ma_zakres_spi_i_gorna_regularna_69():
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    priced = price_rail_leg(leg, DiscountProfile())
    z = priced.breakdown["zakres_cen"]
    assert (z["spi_od"], z["spi_do"]) == (34.90, 59.90)
    assert z["pkp_cena_regularna"] == 69
    assert z["do"] <= 69
    assert "Przedział PKP Super Promo International" in priced.notes
    assert priced.price_type == "szacunek"


def test_price_rail_leg_lublin_berlin_zakres_nie_przekracza_regularnego_pkp():
    leg = _international_leg("Lublin Główny", "Berlin Hauptbahnhof", distance_km=800)
    z = price_rail_leg(leg, DiscountProfile(age=25)).breakdown["zakres_cen"]
    assert z["do"] == 69.90 and z["do"] <= z["pkp_cena_regularna"] == 79
    assert z["spi_od"] == 34.90 <= z["do"]


def test_price_rail_leg_bez_spi_dla_dziecka_i_poza_cennikiem():
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    assert "zakres_cen" not in price_rail_leg(leg, DiscountProfile(age=10)).breakdown
    leg = _international_leg("Szczecin Główny", "Berlin Hauptbahnhof", distance_km=150)
    assert "zakres_cen" not in price_rail_leg(leg, DiscountProfile()).breakdown


def test_zmiana_kursu_przelicza_oba_konce_przedzialu(monkeypatch):
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    priced = price_rail_leg(leg, DiscountProfile())
    z = priced.breakdown["zakres_cen"]
    monkeypatch.setitem(PLACEHOLDER_RATES_TO_PLN, "EUR", 5.0)
    it = build_itinerary("test", [priced])
    assert it.total_price_pln == round(priced.amount * 5.0, 2)
    assert it.total_price_pln_high == round(z["do"] * 5.0, 2)
    assert it.total_price_pln < it.total_price_pln_high


def test_dane_spi_zgodne_z_tekstem_cennika_pdf():
    # JSON ma być odtwarzalny z tekstu PDF (scripts/build_spi_data.py) - ceny nie są wpisywane z głowy.
    import json
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    from parse_spi_pdf import parse_text

    pdf = {t["numer"]: t for t in parse_text((root / "verification/zrodla-pdf/cennik_spi.txt").read_text(encoding="utf-8"))}
    dane = json.loads((root / "fares/data/pkp_spi_pl_de.json").read_text(encoding="utf-8"))
    assert len(dane["pociagi"]) == 13
    for p in dane["pociagi"]:
        for rel, poziomy in p["ceny_eur"].items():
            for poziom, strefy in poziomy.items():
                for i, (strefa, v) in enumerate(strefy.items()):
                    assert [v["klasa_2"], v["klasa_1"]] == pdf[p["numer"]]["tabela"][rel][poziom][i]


def test_zakres_cen_podaje_zrodla_obu_koncow():
    leg = _international_leg("Warszawa Centralna", "Berlin Hauptbahnhof", distance_km=519)
    z = price_rail_leg(leg, DiscountProfile()).breakdown["zakres_cen"]
    assert z["od_zrodlo"].startswith("DB")  # 29.99 < SPI poziom I 34.90
    assert z["do_zrodlo"] == "SPI poziom V"
    leg = _international_leg("Lublin Główny", "Berlin Hauptbahnhof", distance_km=800)
    assert price_rail_leg(leg, DiscountProfile(age=25)).breakdown["zakres_cen"]["do_zrodlo"] == "SPI poziom V"


def test_pkp_mlodziez_15_26_minus_25_procent_i_dodatkowe_relacje():
    """Ulga Młodzież PKP (15-26 lat, 2 klasa, -25%) — granice potwierdzone 2026-11-03."""
    def cena(origin, age):
        seg = Segment(
            Carrier.INTERNATIONAL_PL_DE, origin, "Berlin", distance_km=500,
            discounts=DiscountProfile(age=age),
        )
        return estimate_pkp_offer(seg)

    assert cena("Warszawa", 30).amount == 69.0
    assert cena("Warszawa", 15).amount == 51.75
    assert cena("Warszawa", 26).amount == 51.75
    assert cena("Warszawa", 27).amount == 69.0
    assert cena("Warszawa", 14).amount == 34.5  # dziecko -50% wygrywa dla 14 lat
    assert cena("Warszawa", 20).breakdown["kategoria_wieku"] == "mlodziez"
    assert cena("Wrocław Główny", 40).amount == 48.0
    assert cena("Katowice", 40).amount == 64.0
