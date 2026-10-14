"""Szacowanie ceny segmentu komunikacji miejskiej BVG / VBB Berlin."""

from ._data_loading import load
from ._dzieci_do_6 import bezplatne_dziecko, dziecko_ponizej_6
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("bvg_berlin.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]


def _wybierz_bilet(duration_min: float, strefa: str | None = None) -> dict:
    """Najkrótszy wystarczający bilet wg czasu jazdy. Dla odcinka ze strefy C (strefa="ABC",
    np. lotnisko BER) tylko bilet ABC — AB i Kurzstrecke dobierane po samym czasie jazdy nie
    sprawdzają strefy, a AB nie obowiązuje poza Berlinem (fares/data/bvg_berlin.json::_uwaga)."""
    if strefa == "ABC":
        return next(b for b in _BILETY if b["strefa"] == "ABC")
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.BVG_BERLIN:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora BVG Berlin: {segment.carrier}")
    if segment.ride_duration_min is None:
        raise ValueError("BVG Berlin (taryfa czasowa): ride_duration_min jest wymagane")

    if dziecko_ponizej_6(segment):
        return bezplatne_dziecko(segment, _TABLE)

    bilet = _wybierz_bilet(segment.ride_duration_min, segment.tariff_zone)
    schwerbehindert = segment.discounts.bvg_berlin_schwerbehindert
    wiek_ulgowy = segment.discounts.age is not None and 6 <= segment.discounts.age <= 14
    ulgowy = segment.discounts.bvg_berlin_ulgowy or wiek_ulgowy
    if schwerbehindert:
        amount = 0.0
        typ_biletu = "bezpłatny (Schwerbehindertenausweis + Wertmarke)"
    elif ulgowy:
        amount = bilet["ulgowy"]
        typ_biletu = "ulgowy (Ermäßigungstarif)"
    else:
        amount = bilet["normalny"]
        typ_biletu = "normalny"
    przekroczono = segment.ride_duration_min > bilet["wazny_min"]

    return PriceEstimate(
        carrier=Carrier.BVG_BERLIN,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE if przekroczono else PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "czas_jazdy_min": segment.ride_duration_min,
            "bilet_wazny_min": bilet["wazny_min"],
            "typ_biletu": typ_biletu,
            "strefa": bilet.get("strefa", "AB"),
        },
        notes=(
            f"Taryfa BVG/VBB Berlin ({_TABLE['nazwa_przewoznika']}, ważna od 1.01.2026): dobrano "
            f"bilet {bilet['strefa']} (ważny {bilet['wazny_min']} min)."
            + (
                " Odcinek zaczyna się lub kończy w strefie C (lotnisko BER) — bilet AB tam nie "
                "obowiązuje, potrzebny ABC."
                if segment.tariff_zone == "ABC"
                else ""
            )
            + (
                f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy dostępny "
                f"bilet ({bilet['wazny_min']} min) — cena to szacunek."
                if przekroczono
                else ""
            )
            + (
                " Taryfa ulgowa z wieku (Ermäßigungstarif 6-14 lat)."
                if wiek_ulgowy and not segment.discounts.bvg_berlin_ulgowy and not schwerbehindert
                else ""
            )
        ),
    )
