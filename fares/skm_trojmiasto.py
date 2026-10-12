"""Cena biletu jednorazowego PKP SKM w Trójmieście wg tabeli odległościowej Taryfy Pomorskiej.

Dane: fares/data/skm_trojmiasto.json (21 pasm, cennik C-PKP SKM obowiązujący od 1.03.2026, bilet
normalny oraz ulgi 37/49/51%). Źródło i status są przy KAŻDYM paśmie: "wg Gemini, niezweryfikowane
niezależnie" (domeny przewoźników są z chmury zablokowane, raport Gemini z 2026-10-12).

Wszystkie kwoty pochodzą z raportu Gemini i mają breakdown["price_verified"]=False (CONTRIBUTING.md,
„Dane z zewnętrznych AI”) do czasu drugiego niezależnego źródła: wynik to zawsze PriceType.ESTIMATE.
Po weryfikacji w źródle pierwotnym wystarczy zmienić "status" w "potwierdzone" danego pasma na inny
niż STATUS_WERYFIKACJI — wtedy pasmo (i ulgi z tabel) wraca do price_verified=True.

Bilety komunikacji miejskiej ZTM Gdańsk / ZKM Gdynia NIE obowiązują w pociągach SKM, więc odcinek
SKM w Trójmieście zawsze dostaje bilet kolejowy z tej tabeli. PriceType.OFFICIAL
wymaga zarazem niezależnie zweryfikowanej kwoty i Segment.distance_along_track (km po torach); przy
linii prostej z MOTIS pasmo bywa zaniżone, więc zostaje PriceType.ESTIMATE z opisem przybliżenia
(jak fares/polregio.py).
Bilety strefowe Taryfy Pomorskiej (Bilet Miejski, Bilet Trójmiejski) nie są modelowane."""

import math

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("skm_trojmiasto.json")
_ULGI = load("pkp_intercity.json")["ulgi_procent"]

STATUS_WERYFIKACJI = "wg Gemini, niezweryfikowane niezależnie"


def _band(table: dict, distance_km: float) -> dict:
    """Pasmo dla odległości; km taryfowe są całkowite, więc ułamek zaokrąglamy w górę."""
    tariff_km = math.ceil(distance_km)
    for band in table["pasma_odleglosci_km"]:
        if tariff_km <= band["do_km"]:
            return band
    raise ValueError(f"brak pasma Taryfy Pomorskiej (SKM) dla {distance_km:.0f} km")


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
    if segment.carrier is not Carrier.SKM_TROJMIASTO:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora SKM Trójmiasto: {segment.carrier}"
        )
    if segment.distance_km is None:
        raise ValueError("SKM Trójmiasto: distance_km jest wymagane")
    table = table or _TABLE

    ulga_kod = segment.discounts.pkp_ulga_kod
    if ulga_kod not in _ULGI:
        raise ValueError(f"nieznany kod ulgi: {ulga_kod!r}, dostępne: {list(_ULGI)}")

    band = _band(table, segment.distance_km)
    base = band["cena"]
    ulga_procent = _ULGI[ulga_kod]
    # Tabele ulg 37/49/51% są w cenniku (kwoty z pliku danych); inne ulgi liczymy procentem od
    # ceny bazowej i nie uznajemy za odczyt z cennika.
    z_tabeli_ulg = str(ulga_procent) in band.get("ulgi", {})
    if z_tabeli_ulg:
        amount = band["ulgi"][str(ulga_procent)]
    else:
        amount = round(base * (1 - ulga_procent / 100), 2)

    confirmation = _confirmation(band)
    verified = _independently_verified(confirmation) and (ulga_procent == 0 or z_tabeli_ulg)
    official = verified and segment.distance_along_track
    breakdown = {
        "cena_bazowa": base,
        "pasmo_do_km": band["do_km"],
        "ulga_kod": ulga_kod,
        "ulga_procent": ulga_procent,
        "klasa": table["klasa"],
        "price_verified": verified,
        "odleglosc_taryfowa": "po torach" if segment.distance_along_track else "linia prosta",
        "status_weryfikacji": STATUS_WERYFIKACJI,
        "obowiazuje_od": table["obowiazuje_od"],
    }
    notes = (
        "Bilet jednorazowy PKP SKM w Trójmieście wg tabeli odległościowej Taryfy Pomorskiej "
        f"(od {table['obowiazuje_od']}, 2. klasa), pasmo do {band['do_km']} km. Bilety ZTM Gdańsk "
        "i ZKM Gdynia nie obowiązują w SKM."
    )
    if confirmation is not None:
        breakdown["zrodlo_url"] = confirmation["zrodlo_url"]
        breakdown["data_weryfikacji"] = confirmation["data"]
        notes += (
            f" Kwota pasma {STATUS_WERYFIKACJI}: {confirmation['zrodlo_url']} "
            f"({confirmation['data']})."
        )
    else:
        notes += " Cena NIEPOTWIERDZONA: pasmo bez źródła w pliku danych."
    if not segment.distance_along_track:
        notes += (
            " Pasmo dobrane z odległości w linii prostej, nie z km po torach — cena przybliżona "
            "(rzeczywiste pasmo może być wyższe)."
        )
    if ulga_procent and not z_tabeli_ulg:
        notes += (
            f" Ulga {ulga_procent}% policzona procentem od ceny bazowej (brak jej w tabelach ulg)."
        )
    if not verified:
        if confirmation is None:
            reason = "pasmo niepotwierdzone w źródle pierwotnym"
        elif not _independently_verified(confirmation):
            reason = "kwota tylko z raportu Gemini, bez drugiego niezależnego źródła"
        else:
            reason = "ulga policzona procentem, nie z tabeli ulg"
        breakdown["powod_szacunku"] = reason

    return PriceEstimate(
        carrier=Carrier.SKM_TROJMIASTO,
        amount=amount,
        currency=table["waluta"],
        price_type=PriceType.OFFICIAL if official else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
