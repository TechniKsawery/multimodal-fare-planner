"""Szacowanie ceny segmentu komunikacji miejskiej ZTM Lublin (ZDiTM):
taryfa czasowa strefy 1+2 — dobiera najkrótszy bilet, którego czas ważności pokrywa
czas jazdy odcinka.

Dane pochodzą z oficjalnego cennika LUBIKA (system biletu elektronicznego ZDiTM Lublin) —
patrz pole "_zrodlo" w fares/data/ztm_lublin.json oraz README.md w tym katalogu.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("ztm_lublin.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]


def _wybierz_bilet(duration_min: float) -> dict:
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.ZTM_LUBLIN:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora ZTM Lublin: {segment.carrier}")
    if segment.ride_duration_min is None:
        raise ValueError("ZTM Lublin (taryfa czasowa): ride_duration_min jest wymagane")

    bilet = _wybierz_bilet(segment.ride_duration_min)
    bezplatny = segment.discounts.ztm_lublin_bezplatny
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
        },
        notes=(
            "Taryfa czasowa ZTM Lublin (oficjalna, strefa 1+2, ważna od 16.02.2026): dobrano "
            f"bilet {bilet['wazny_min']}-minutowy jako najkrótszy pokrywający czas jazdy."
            + (
                f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy dostępny "
                f"bilet ({_NAJDLUZSZY['wazny_min']} min) — cena to szacunek (ekstrapolacja)."
                if przekroczono
                else ""
            )
        ),
    )
