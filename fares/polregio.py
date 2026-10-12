"""Szacowanie ceny biletu jednorazowego POLREGIO / Koleje Dolnośląskie / Koleje Śląskie wg
degresywnej tabeli odległościowej (Taryfa Podstawowa) zamiast sztywnego PLN/km.

Dane: fares/data/polregio_taryfa_podstawowa.json. KAŻDE pasmo ma pole "potwierdzone": null albo
{"zrodlo_url": ..., "data": "YYYY-MM-DD"}. Tylko pasmo z takim obiektem daje wynik
PriceType.OFFICIAL i breakdown["price_verified"]=True; reszta to PriceType.ESTIMATE i
price_verified=False — stan na dziś: żadne pasmo nie jest potwierdzone (patrz _zrodlo_raportu
i _uwaga w pliku danych oraz verification/taryfy-skm-rb-weryfikacja-2026-10-12.md).
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
    breakdown = {
        "cena_bazowa": base,
        "pasmo_do_km": band["do_km"],
        "ulga_kod": ulga_kod,
        "ulga_procent": ulga_procent,
        "klasa": table["klasa"],
        "price_verified": verified,
    }
    if confirmation is not None:
        breakdown["zrodlo_url"] = confirmation["zrodlo_url"]
        breakdown["data_weryfikacji"] = confirmation["data"]
        notes = (
            "Cena z tabeli odległościowej Taryfy Podstawowej POLREGIO/KD/KŚ (pociągi REGIO, "
            f"2. klasa), pasmo do {band['do_km']} km potwierdzone: {confirmation['zrodlo_url']} "
            f"({confirmation['data']})."
        )
    else:
        notes = (
            "Szacunek wg degresywnej tabeli Taryfy Podstawowej POLREGIO/KD/KŚ (pociągi REGIO, "
            f"2. klasa, pasmo do {band['do_km']} km) — cena NIEPOTWIERDZONA: kwoty z raportu "
            "researchera, nie zweryfikowane w cenniku przewoźnika. POLREGIO w części województw "
            "stosuje własne taryfy regionalne (m.in. Pomorska, Podlaska, Małopolska), "
            "a odległość to linia prosta, nie km po torach."
        )
    if ulga_procent:
        notes += f" Ulga {ulga_procent}% policzona procentem od ceny bazowej."
    if not verified:
        breakdown["powod_szacunku"] = "tabela taryfowa niepotwierdzona w źródle pierwotnym"

    return PriceEstimate(
        carrier=Carrier.POLREGIO_PODSTAWOWA,
        amount=amount,
        currency=table["waluta"],
        price_type=PriceType.OFFICIAL if verified else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
