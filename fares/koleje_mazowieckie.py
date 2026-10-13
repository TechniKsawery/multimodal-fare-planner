"""Cena biletu jednorazowego Kolei Mazowieckich (KM) wg Tabeli nr 1 taryfy przewozowej TP-KM.

Dane: fares/data/koleje_mazowieckie.json (27 pasm: bilet jednorazowy wg taryfy normalnej, 2. klasa,
kwoty brutto; od 1.07.2022 uchwała 268/Z/2022, zmiana nr 6 od 1.01.2025 tabeli cen nie zmienia).
Źródło: oficjalny PDF TP-KM ze zmianami 1–6, s. 13 (URL w danych). Właściciel projektu potwierdził
tabelę w PDF 2026-10-13, więc pasma mają price_verified=True; nic spoza Tabeli nr 1 nie jest tu
zgadywane. Powyżej 520 km brak pasma: ValueError, routing daje wtedy niepotwierdzony szacunek PLN/km.

PriceType.OFFICIAL wymaga Segment.distance_along_track (km po torach); przy linii prostej z MOTIS
pasmo bywa zaniżone, więc wynik to PriceType.ESTIMATE z opisem przybliżenia (jak
fares/koleje_malopolskie.py, fares/polregio.py). Ulgi, bilety okresowe i czasowe nie są
modelowane: pasażer z ulgą dostaje cenę normalną jako górną granicę, niepotwierdzoną dla ulgi."""

import math

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("koleje_mazowieckie.json")
_ULGI = load("pkp_intercity.json")["ulgi_procent"]


def _band(table: dict, distance_km: float) -> dict:
    """Pasmo dla odległości; km taryfowe są całkowite, więc ułamek zaokrąglamy w górę."""
    tariff_km = math.ceil(distance_km)
    for band in table["pasma_odleglosci_km"]:
        if tariff_km <= band["do_km"]:
            return band
    raise ValueError(
        f"brak pasma taryfy Kolei Mazowieckich dla {distance_km:.0f} km (tabela do 520)"
    )


def _confirmation(band: dict) -> dict | None:
    """Potwierdzenie pasma, tylko gdy ma źródło (URL) i datę; inaczej None."""
    c = band.get("potwierdzone")
    if c and str(c.get("zrodlo_url", "")).startswith("http") and c.get("data"):
        return c
    return None


def estimate(segment: Segment, table: dict | None = None) -> PriceEstimate:
    if segment.carrier is not Carrier.KOLEJE_MAZOWIECKIE:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora Kolei Mazowieckich: {segment.carrier}"
        )
    if segment.distance_km is None:
        raise ValueError("Koleje Mazowieckie: distance_km jest wymagane")
    table = table or _TABLE

    ulga_kod = segment.discounts.pkp_ulga_kod
    if ulga_kod not in _ULGI:
        raise ValueError(f"nieznany kod ulgi: {ulga_kod!r}, dostępne: {list(_ULGI)}")
    ulga_wnioskowana = ulga_kod != "brak"

    band = _band(table, segment.distance_km)
    amount = band["cena"]
    confirmation = _confirmation(band)
    # Ulg KM nie modelujemy: pasażer z ulgą dostaje cenę normalną, więc to nie odczyt z cennika
    # dla jego biletu.
    verified = confirmation is not None and not ulga_wnioskowana
    official = verified and segment.distance_along_track
    breakdown = {
        "cena_bazowa": amount,
        "cena_netto": band.get("netto"),
        "ptu": band.get("ptu"),
        "pasmo_do_km": band["do_km"],
        "pasmo": band.get("zakres"),
        "ulga_kod": ulga_kod,
        "klasa": table["klasa"],
        "price_verified": verified,
        "odleglosc_taryfowa": "po torach" if segment.distance_along_track else "linia prosta",
        "obowiazuje_od": table.get("obowiazuje_od"),
    }
    if segment.distance_along_track and segment.distance_source:
        breakdown["zrodlo_km"] = segment.distance_source
    notes = (
        "Bilet jednorazowy Kolei Mazowieckich wg Tabeli nr 1 taryfy TP-KM (taryfa normalna, "
        f"2. klasa, brutto), pasmo do {band['do_km']} km."
    )
    if confirmation is not None:
        breakdown["zrodlo_url"] = confirmation["zrodlo_url"]
        breakdown["data_weryfikacji"] = confirmation["data"]
        notes += (
            f" Kwota pasma: {confirmation['zrodlo_url']} (zweryfikowano {confirmation['data']})."
        )
    else:
        notes += " Cena NIEPOTWIERDZONA: pasmo bez źródła w pliku danych."
    if segment.distance_along_track and segment.distance_source:
        notes += f" Kilometry po torach: {segment.distance_source}."
    if not segment.distance_along_track:
        notes += (
            " Pasmo dobrane z odległości w linii prostej, nie z km po torach — cena przybliżona "
            "(rzeczywiste pasmo może być wyższe)."
        )
    if ulga_wnioskowana:
        notes += " Ulgi KM nie są modelowane: pokazana cena normalna, niepotwierdzona dla ulgi."
    if not verified:
        breakdown["powod_szacunku"] = (
            "ulgi KM nie są modelowane (cena normalna)"
            if ulga_wnioskowana
            else "pasmo niepotwierdzone w źródle pierwotnym"
        )

    return PriceEstimate(
        carrier=Carrier.KOLEJE_MAZOWIECKIE,
        amount=amount,
        currency=table["waluta"],
        price_type=PriceType.OFFICIAL if official else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
