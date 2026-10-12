"""Szacowanie ceny biletu jednorazowego POLREGIO / Koleje Dolnośląskie / Koleje Śląskie wg
degresywnej tabeli odległościowej (Taryfa Podstawowa) zamiast sztywnego PLN/km.

Dane: fares/data/polregio_taryfa_podstawowa.json. KAŻDE pasmo ma pole "potwierdzone": null albo
{"zrodlo_url": ..., "data": "YYYY-MM-DD"}. Tylko pasmo z takim obiektem daje wynik
breakdown["price_verified"]=True (bez ulgi) i zrodlo_url/data_weryfikacji w breakdown. Typ
wyniku to PriceType.OFFICIAL tylko, gdy Segment.distance_along_track (km po torach, ze źródłem w
Segment.distance_source); przy linii prostej z MOTIS zostaje PriceType.ESTIMATE z opisem
przybliżenia. Stan: wszystkie 30 pasm
potwierdzone przez Gemini 2026-10-12 (TPR POLREGIO od 1.09.2026; patrz _zrodlo_raportu w pliku
danych i verification/taryfy-skm-rb-weryfikacja-2026-10-12.md).
"""

import math

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("polregio_taryfa_podstawowa.json")
_ULGI = load("pkp_intercity.json")["ulgi_procent"]


def _band(table: dict, distance_km: float) -> dict:
    """Pasmo dla odległości; taryfowe km są całkowite, więc ułamek zaokrąglamy w górę
    (5,4 km to już pasmo 6-10)."""
    tariff_km = math.ceil(distance_km)
    for band in table["pasma_odleglosci_km"]:
        if tariff_km <= band["do_km"]:
            return band
    raise ValueError(f"brak pasma taryfy podstawowej dla {distance_km:.0f} km")


def _confirmation(band: dict) -> dict | None:
    """Potwierdzenie pasma, tylko gdy ma źródło (URL) i datę; inaczej None."""
    c = band.get("potwierdzone")
    if c and str(c.get("zrodlo_url", "")).startswith("http") and c.get("data"):
        return c
    return None


def estimate(segment: Segment, table: dict | None = None) -> PriceEstimate:
    if segment.carrier is not Carrier.POLREGIO_PODSTAWOWA:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora POLREGIO: {segment.carrier}")
    if segment.distance_km is None:
        raise ValueError("POLREGIO: distance_km jest wymagane")
    table = table or _TABLE

    ulga_kod = segment.discounts.pkp_ulga_kod
    if ulga_kod not in _ULGI:
        raise ValueError(f"nieznany kod ulgi: {ulga_kod!r}, dostępne: {list(_ULGI)}")

    band = _band(table, segment.distance_km)
    base = band["cena"]
    ulga_procent = _ULGI[ulga_kod]
    amount = round(base * (1 - ulga_procent / 100), 2)

    confirmation = _confirmation(band)
    # Ulgę liczymy procentem od ceny bazowej (tabele ulg POLREGIO nie są w danych), więc cena z
    # ulgą nie jest odczytem z cennika nawet przy potwierdzonym paśmie.
    verified = confirmation is not None and ulga_procent == 0
    # Potwierdzona jest KWOTA pasma; czy pasmo jest właściwe, zależy od odległości taryfowej
    # (km po torach). Z linii prostej (leg.distance_km) dobieramy pasmo z przybliżeniem
    # (z reguły zaniżonym), więc wynik to szacunek, dopóki distance_along_track nie jest True.
    official = verified and segment.distance_along_track
    breakdown = {
        "cena_bazowa": base,
        "pasmo_do_km": band["do_km"],
        "ulga_kod": ulga_kod,
        "ulga_procent": ulga_procent,
        "klasa": table["klasa"],
        "price_verified": verified,
        "odleglosc_taryfowa": "po torach" if segment.distance_along_track else "linia prosta",
    }
    if segment.distance_along_track and segment.distance_source:
        breakdown["zrodlo_km"] = segment.distance_source
    if confirmation is not None:
        breakdown["zrodlo_url"] = confirmation["zrodlo_url"]
        breakdown["data_weryfikacji"] = confirmation["data"]
        notes = (
            "Cena z tabeli odległościowej Taryfy Podstawowej POLREGIO/KD/KŚ (pociągi REGIO, "
            f"2. klasa), kwota pasma do {band['do_km']} km potwierdzona: "
            f"{confirmation['zrodlo_url']} ({confirmation['data']})."
        )
        if segment.distance_along_track and segment.distance_source:
            notes += f" Kilometry po torach: {segment.distance_source}."
        if not segment.distance_along_track:
            notes += (
                " Pasmo dobrane z odległości w linii prostej, nie z km po torach — cena "
                "przybliżona (rzeczywiste pasmo może być wyższe)."
            )
    else:
        notes = (
            "Szacunek wg degresywnej tabeli Taryfy Podstawowej POLREGIO/KD/KŚ (pociągi REGIO, "
            f"2. klasa, pasmo do {band['do_km']} km) — cena NIEPOTWIERDZONA: pasmo bez źródła "
            "w pliku danych. POLREGIO w części województw stosuje własne taryfy regionalne "
            "(m.in. Pomorska, Podlaska, Małopolska), a odległość to linia prosta, nie km po torach."
        )
    if ulga_procent:
        notes += f" Ulga {ulga_procent}% policzona procentem od ceny bazowej."
    if not verified:
        breakdown["powod_szacunku"] = (
            "ulga policzona procentem, nie z tabeli ulg"
            if confirmation is not None
            else "pasmo niepotwierdzone w źródle pierwotnym"
        )

    return PriceEstimate(
        carrier=Carrier.POLREGIO_PODSTAWOWA,
        amount=amount,
        currency=table["waluta"],
        price_type=PriceType.OFFICIAL if official else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
