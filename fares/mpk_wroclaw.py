"""Szacowanie ceny segmentu komunikacji miejskiej MPK Wrocław."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("mpk_wroclaw.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]


def _wybierz_bilet(duration_min: float) -> dict:
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.MPK_WROCLAW:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora MPK Wrocław: {segment.carrier}")
    if segment.ride_duration_min is None:
        raise ValueError("MPK Wrocław (taryfa czasowa): ride_duration_min jest wymagane")

    bilet = _wybierz_bilet(segment.ride_duration_min)
    ulgowy = segment.discounts.mpk_wroclaw_ulgowy
    amount = bilet["ulgowy"] if ulgowy else bilet["normalny"]
    przekroczono = segment.ride_duration_min > _NAJDLUZSZY["wazny_min"]

    return PriceEstimate(
        carrier=Carrier.MPK_WROCLAW,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE if przekroczono else PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "czas_jazdy_min": segment.ride_duration_min,
            "bilet_wazny_min": bilet["wazny_min"],
            "typ_biletu": "ulgowy (50%)" if ulgowy else "normalny",
            "strefa": bilet.get("strefa", "miejska"),
        },
        notes=(
            f"Taryfa czasowa MPK Wrocław ({_TABLE['nazwa_przewoznika']}): dobrano "
            f"bilet {bilet['wazny_min']}-minutowy."
            + (
                f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy dostępny "
                f"bilet ({_NAJDLUZSZY['wazny_min']} min) — cena to szacunek."
                if przekroczono
                else ""
            )
        ),
    )
