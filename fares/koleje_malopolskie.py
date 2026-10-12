"""Cena biletu jednorazowego Kolei Małopolskich (KMŁ) wg Tabeli nr 1 taryfy przewozowej TP-KMŁ.

Dane: fares/data/koleje_malopolskie.json (30 pasm: bilet jednorazowy wg taryfy normalnej, 2. klasa,
pociąg osobowy, Załącznik nr 2 do Uchwały Zarządu nr 43/2026 z 17.03.2026). Źródło i status są przy
KAŻDYM paśmie: "wg Gemini, niezweryfikowane niezależnie" (domeny przewoźników są z chmury
zablokowane, raport Gemini z 2026-10-12, research/km-malopolskie.md). Raport nie podaje daty wejścia
w życie taryfy: w danych jest to jawnie "obowiazuje_od": null (brak), nie zgadujemy jej.

Wszystkie kwoty pochodzą z raportu Gemini i mają breakdown["price_verified"]=False (CONTRIBUTING.md,
„Dane z zewnętrznych AI”) do czasu drugiego niezależnego źródła: wynik to zawsze PriceType.ESTIMATE.
Po weryfikacji w źródle pierwotnym wystarczy zmienić "status" w "potwierdzone" danego pasma na inny
niż STATUS_WERYFIKACJI — wtedy pasmo wraca do price_verified=True (jak w fares/skm_trojmiasto.py).
PriceType.OFFICIAL wymaga zarazem niezależnie zweryfikowanej kwoty i Segment.distance_along_track
(km po torach); przy linii prostej z MOTIS pasmo bywa zaniżone, więc zostaje PriceType.ESTIMATE
z opisem przybliżenia (jak fares/polregio.py).

Ulgi, bilety okresowe i łączone (np. WSPÓLNY KMK+KMŁ) nie są modelowane: raport podaje tylko cenę
normalną, więc pasażer z ulgą dostaje cenę normalną jako górną granicę, oznaczoną jako
niepotwierdzoną (jak fares/lka_lodz.py). Tabela nie obowiązuje do/z Kraków Lotnisko — odcinków
z tą stacją routing do tego kalkulatora nie kieruje."""

import math

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("koleje_malopolskie.json")
_ULGI = load("pkp_intercity.json")["ulgi_procent"]

STATUS_WERYFIKACJI = "wg Gemini, niezweryfikowane niezależnie"


def _band(table: dict, distance_km: float) -> dict:
    """Pasmo dla odległości; km taryfowe są całkowite, więc ułamek zaokrąglamy w górę."""
    tariff_km = math.ceil(distance_km)
    for band in table["pasma_odleglosci_km"]:
        if tariff_km <= band["do_km"]:
            return band
    raise ValueError(f"brak pasma taryfy Kolei Małopolskich dla {distance_km:.0f} km")


def _confirmation(band: dict) -> dict | None:
    """Potwierdzenie pasma, tylko gdy ma źródło (URL) i datę; inaczej None."""
    c = band.get("potwierdzone")
    if c and str(c.get("zrodlo_url", "")).startswith("http") and c.get("data"):
        return c
    return None


def _independently_verified(confirmation: dict | None) -> bool:
    """Czy kwota ma drugie, niezależne źródło. Status "wg Gemini, niezweryfikowane niezależnie"
    oznacza, że jest tylko raport zewnętrznego AI, więc price_verified zostaje False."""
    return confirmation is not None and confirmation.get("status") != STATUS_WERYFIKACJI


def estimate(segment: Segment, table: dict | None = None) -> PriceEstimate:
    if segment.carrier is not Carrier.KOLEJE_MALOPOLSKIE:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora Kolei Małopolskich: {segment.carrier}"
        )
    if segment.distance_km is None:
        raise ValueError("Koleje Małopolskie: distance_km jest wymagane")
    table = table or _TABLE

    ulga_kod = segment.discounts.pkp_ulga_kod
    if ulga_kod not in _ULGI:
        raise ValueError(f"nieznany kod ulgi: {ulga_kod!r}, dostępne: {list(_ULGI)}")
    ulga_wnioskowana = ulga_kod != "brak"

    band = _band(table, segment.distance_km)
    amount = band["cena"]

    confirmation = _confirmation(band)
    # Ulg KMŁ nie modelujemy (raport ma tylko cenę normalną): pasażer z ulgą dostaje cenę normalną,
    # więc nie jest to odczyt z cennika dla jego biletu.
    verified = _independently_verified(confirmation) and not ulga_wnioskowana
    official = verified and segment.distance_along_track
    obowiazuje_od = table.get("obowiazuje_od")
    breakdown = {
        "cena_bazowa": amount,
        "pasmo_do_km": band["do_km"],
        "pasmo": band.get("zakres"),
        "ulga_kod": ulga_kod,
        "klasa": table["klasa"],
        "price_verified": verified,
        "odleglosc_taryfowa": "po torach" if segment.distance_along_track else "linia prosta",
        "status_weryfikacji": STATUS_WERYFIKACJI,
        "obowiazuje_od": obowiazuje_od,
    }
    if segment.distance_along_track and segment.distance_source:
        breakdown["zrodlo_km"] = segment.distance_source
    obowiazuje_opis = (
        f"od {obowiazuje_od}"
        if obowiazuje_od
        else "data wejścia w życie: brak w raporcie, niezweryfikowana"
    )
    notes = (
        "Bilet jednorazowy Kolei Małopolskich wg Tabeli nr 1 taryfy TP-KMŁ (taryfa normalna, "
        f"2. klasa, pociąg osobowy; {obowiazuje_opis}), pasmo do {band['do_km']} km. Tabela nie "
        "obowiązuje do/z Kraków Lotnisko."
    )
    if confirmation is not None:
        breakdown["zrodlo_url"] = confirmation["zrodlo_url"]
        breakdown["data_weryfikacji"] = confirmation["data"]
        notes += (
            f" Kwota pasma {confirmation.get('status', STATUS_WERYFIKACJI)}: "
            f"{confirmation['zrodlo_url']} ({confirmation['data']})."
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
        notes += " Ulgi KMŁ nie są modelowane: pokazana cena normalna, niepotwierdzona dla ulgi."
    if not verified:
        if confirmation is None:
            reason = "pasmo niepotwierdzone w źródle pierwotnym"
        elif not _independently_verified(confirmation):
            reason = "kwota tylko z raportu Gemini, bez drugiego niezależnego źródła"
        else:
            reason = "ulgi KMŁ nie są modelowane (cena normalna)"
        breakdown["powod_szacunku"] = reason

    return PriceEstimate(
        carrier=Carrier.KOLEJE_MALOPOLSKIE,
        amount=amount,
        currency=table["waluta"],
        price_type=PriceType.OFFICIAL if official else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
