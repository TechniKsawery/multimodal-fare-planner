"""Cena odcinka komunikacji miejskiej ZVON w Görlitz–Zgorzelec: EuropastadtTarif, Einzelfahrt.

Dane: fares/data/zvon_gorlitz.json (zvon.de/de/grenzueberschreitende-fahrten/europastadttarif,
odczyt Ksaviego 2026-10-13). Bilet ermäßigt (1,50 EUR) przysługuje TYLKO uczniom do 15. urodzin,
więc wybieramy go po wieku z `DiscountProfile.age` (age < 15); studenci i starsi uczniowie płacą
cenę normalną, a brak wieku = cena normalna (górna granica). Wiek nie dowodzi statusu ucznia, więc
przy ulgowej cenie notes o tym mówi."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("zvon_gorlitz.json")
_BILET = _TABLE["einzelfahrt"]
_WIEK_PONIZEJ = _TABLE["ermaessigt_wiek_ponizej"]
_ZRODLO = _TABLE["weryfikacja"]["url"]
_DATA = _TABLE["weryfikacja"]["data"]


def ma_ulge(segment: Segment) -> bool:
    age = segment.discounts.age
    return age is not None and age < _WIEK_PONIZEJ


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.ZVON_GORLITZ:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora ZVON: {segment.carrier}")

    ulgowy = ma_ulge(segment)
    return PriceEstimate(
        carrier=Carrier.ZVON_GORLITZ,
        amount=_BILET["ermaessigt"] if ulgowy else _BILET["normalny"],
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelfahrt ermäßigt" if ulgowy else "Einzelfahrt normal",
            "bilet_wazny_min": _BILET["wazny_min"],
            "taryfa": "EuropastadtTarif (Görlitz–Zgorzelec)",
            "price_verified": True,
            "zrodlo": _ZRODLO,
            "data_weryfikacji": _DATA,
        },
        notes=(
            f"EuropastadtTarif ZVON, Einzelfahrt (ważny {_BILET['wazny_min']} min od skasowania), "
            f"zweryfikowano {_DATA}: {_ZRODLO}. "
            + (
                f"Cena ermäßigt: ulga tylko dla uczniów do 15. urodzin (wiek {segment.discounts.age} "
                "< 15; zakładamy status ucznia, którego wiek sam nie potwierdza)."
                if ulgowy
                else "Cena normalna (ulga ermäßigt tylko dla uczniów do 15. urodzin)."
            )
        ),
    )
