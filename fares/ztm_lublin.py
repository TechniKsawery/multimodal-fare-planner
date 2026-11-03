"""Szacowanie ceny segmentu komunikacji miejskiej ZTM Lublin (ZDiTM):
taryfa czasowa strefy 1+2 — dobiera najkrótszy bilet, którego czas ważności pokrywa
czas jazdy odcinka.

Dane pochodzą z oficjalnego cennika ZDiTM Lublin / LUBIKA, zweryfikowanego 2026-10-14 (źródło,
data i zasady ulg: fares/data/ztm_lublin.json oraz README.md w tym katalogu).

Przejazd bezpłatny wynika z flagi `ztm_lublin_bezplatny` ALBO z samego wieku (`DiscountProfile.age`):
65+ oraz dzieci do 30.09 roku, w którym kończą 7 lat. Z wieku 7-14 lat ZAKŁADAMY dodatkowo status
ucznia szkoły podstawowej w Lublinie (jak fares/zvon_gorlitz.py) — wiek go nie dowodzi, więc notes
to mówi. Ulgi 50% (uczniowie do 24 lat, doktoranci, ISIC do 26 lat, emeryci, studenci polskich uczelni
z legitymacją, potwierdzone 2026-11-03) wymagają flagi `ztm_lublin_ulgowy`.
"""

from datetime import date

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("ztm_lublin.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]
_BEZPLATNE = _TABLE["bezplatne"]
_ZRODLO = _TABLE["source_url"]
_DATA = _TABLE["verified_date"]


def _wybierz_bilet(duration_min: float) -> dict:
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def _powod_bezplatny(segment: Segment) -> str | None:
    """Opis tytułu bezpłatnego wynikającego z samego wieku (None = wiek nie daje przejazdu bezpłatnego)."""
    age = segment.discounts.age
    if age is None:
        return None
    if age >= _BEZPLATNE["senior_od_wieku"]:
        return f"osoba {_BEZPLATNE['senior_od_wieku']}+"
    limit = _BEZPLATNE["dzieci_do_wieku"]
    if age < limit - 1:
        # Wiek <= 5: siódme urodziny przypadają najwcześniej w przyszłym roku kalendarzowym,
        # więc dziecko jest objęte limitem 30.09 roku siódmych urodzin niezależnie od daty.
        return f"dziecko do 30.09 roku ukończenia {limit} lat"
    if age == limit - 1 and segment.travel_date:
        # Wiek 6: siódme urodziny w tym lub przyszłym roku; pewność tylko do 30.09 bieżącego roku.
        d = date.fromisoformat(segment.travel_date)
        if (d.month, d.day) <= (9, 30):
            return f"dziecko do 30.09 roku ukończenia {limit} lat"
    lo, hi = _BEZPLATNE["uczniowie_podstawowek_zakladany_wiek"]
    if lo <= age <= hi:
        return "uczeń szkoły podstawowej w Lublinie (założony z wieku, wymaga legitymacji szkolnej)"
    return None


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.ZTM_LUBLIN:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora ZTM Lublin: {segment.carrier}")
    if segment.ride_duration_min is None:
        raise ValueError("ZTM Lublin (taryfa czasowa): ride_duration_min jest wymagane")

    bilet = _wybierz_bilet(segment.ride_duration_min)
    powod = _powod_bezplatny(segment)
    bezplatny = segment.discounts.ztm_lublin_bezplatny or powod is not None
    ulgowy = segment.discounts.ztm_lublin_ulgowy
    if bezplatny:
        amount = 0.0
        typ_biletu = "bezpłatny (100%)"
    elif ulgowy:
        amount = bilet["ulgowy"]
        typ_biletu = "ulgowy"
    else:
        amount = bilet["normalny"]
        typ_biletu = "normalny"
    przekroczono = segment.ride_duration_min > _NAJDLUZSZY["wazny_min"]

    return PriceEstimate(
        carrier=Carrier.ZTM_LUBLIN,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE if przekroczono else PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "czas_jazdy_min": segment.ride_duration_min,
            "bilet_wazny_min": bilet["wazny_min"],
            "typ_biletu": typ_biletu,
            "strefa": "1+2",
            "price_verified": True,
            "zrodlo": _ZRODLO,
            "data_weryfikacji": _DATA,
            **(
                {"powod_bezplatny": powod}
                if powod and not segment.discounts.ztm_lublin_bezplatny
                else {}
            ),
        },
        notes=(
            "Taryfa czasowa ZTM Lublin (oficjalna, strefa 1+2, ważna od 16.02.2026, "
            f"zweryfikowano {_DATA}: {_ZRODLO}): dobrano "
            f"bilet {bilet['wazny_min']}-minutowy jako najkrótszy pokrywający czas jazdy."
            + (
                f" Przejazd bezpłatny z wieku: {powod}."
                if powod and not segment.discounts.ztm_lublin_bezplatny
                else ""
            )
            + (
                f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy dostępny "
                f"bilet ({_NAJDLUZSZY['wazny_min']} min) — cena to szacunek (ekstrapolacja)."
                if przekroczono
                else ""
            )
        ),
    )
