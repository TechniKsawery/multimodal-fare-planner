"""Cena odcinka ŁKA w Strefie A (granice Łodzi): własne bilety czasowe ŁKA 20/40/80 min.

Dane: fares/data/lka_lodz.json (wg Gemini, niezweryfikowane niezależnie, 2026-10-12). Bilety
strefowe ŁKA obowiązują też w pojazdach MPK Łódź, a w ŁKA w Strefie A honorowane są bilety MPK
Łódź — cennika MPK Łódź w repo nie ma, więc wyceniamy biletem ŁKA. Wybór biletu jak w
fares/ztm_warszawa.py: najkrótszy, którego ważność pokrywa czas jazdy. Ulgi (ulgowy 50%) i bilety
okresowe nie są modelowane.

Kwoty z raportu Gemini mają breakdown["price_verified"]=False i PriceType.ESTIMATE (CONTRIBUTING.md,
„Dane z zewnętrznych AI”) do czasu drugiego niezależnego źródła; po jego dodaniu wystarczy zmienić
"weryfikacja"."status" w lka_lodz.json na inny niż STATUS_WERYFIKACJI."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("lka_lodz.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]

STATUS_WERYFIKACJI = "wg Gemini, niezweryfikowane niezależnie"


def _wybierz_bilet(duration_min: float) -> dict:
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.LKA_LODZ:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora ŁKA: {segment.carrier}")
    if segment.ride_duration_min is None:
        raise ValueError("ŁKA (taryfa czasowa): ride_duration_min jest wymagane")

    bilet = _wybierz_bilet(segment.ride_duration_min)
    przekroczono = segment.ride_duration_min > _NAJDLUZSZY["wazny_min"]
    ulga_wnioskowana = segment.discounts.pkp_ulga_kod != "brak"
    niezaleznie_zweryfikowane = _TABLE["weryfikacja"]["status"] != STATUS_WERYFIKACJI
    # Ulg ŁKA/MPK Łódź nie modelujemy: pasażer z ulgą dostaje cenę normalną (górna granica),
    # oznaczoną jako niepotwierdzoną, żeby ranking nie traktował jej jak odczytu z cennika.
    verified = niezaleznie_zweryfikowane and not ulga_wnioskowana
    breakdown = {
        "relacja": f"{segment.origin} <-> {segment.destination}",
        "czas_jazdy_min": segment.ride_duration_min,
        "bilet_wazny_min": bilet["wazny_min"],
        "typ_biletu": "normalny",
        "strefa": bilet["strefa"],
        "status_weryfikacji": STATUS_WERYFIKACJI,
        "price_verified": verified,
        "zrodlo_url": _TABLE.get("zrodlo_url"),
        "data_weryfikacji": _TABLE.get("data_weryfikacji"),
    }
    if not verified:
        breakdown["powod_szacunku"] = (
            "ulgi ŁKA/MPK Łódź nie są modelowane (cena normalna)"
            if niezaleznie_zweryfikowane
            else "kwota tylko z raportu Gemini, bez drugiego niezależnego źródła"
        )
    notes = (
        f"Bilet strefowy ŁKA (Strefa A, Łódź) {bilet['wazny_min']}-minutowy, honorowany też w MPK "
        f"Łódź; {STATUS_WERYFIKACJI}. Bilety z aplikacji kasuje się kodem QR; Open Payment System "
        "nie jest honorowany."
    )
    if przekroczono:
        notes += (
            f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy bilet "
            f"({_NAJDLUZSZY['wazny_min']} min) — cena to szacunek."
        )
    if not niezaleznie_zweryfikowane:
        notes += " Cena niepotwierdzona: brak drugiego niezależnego źródła kwot."
    if ulga_wnioskowana:
        notes += " Ulgi nie są modelowane: pokazana cena normalna, niepotwierdzona dla ulgi."

    return PriceEstimate(
        carrier=Carrier.LKA_LODZ,
        amount=bilet["normalny"],
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE if (przekroczono or not verified) else PriceType.OFFICIAL,
        breakdown=breakdown,
        notes=notes,
    )
