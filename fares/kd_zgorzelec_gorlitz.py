"""Pociąg Kolei Dolnośląskich na odcinku granicznym Zgorzelec - Görlitz: przejazd bezpłatny (0 zł).

Dane: fares/data/kd_zgorzelec_gorlitz.json (wg Gemini, niezweryfikowane niezależnie, 2026-10-13).
Wpis dotyczy wyłącznie pociągu KD między tymi dwiema stacjami; autobus zastępczy i komunikacja
miejska (ZVON EuropastadtTarif) są poza nim.

Gdyby status w JSON wrócił do STATUS_WERYFIKACJI (dane tylko z raportu AI), cena jest
niepotwierdzonym szacunkiem (breakdown["price_verified"]=False, PriceType.ESTIMATE)."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("kd_zgorzelec_gorlitz.json")

STATUS_WERYFIKACJI = "wg Gemini, niezweryfikowane niezależnie"


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.KD_ZGORZELEC_GORLITZ:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora KD: {segment.carrier}")

    weryfikacja = _TABLE["weryfikacja"]
    potwierdzone = weryfikacja["status"] != STATUS_WERYFIKACJI
    breakdown = {
        "relacja": f"{segment.origin} <-> {segment.destination}",
        "status_weryfikacji": weryfikacja["status"],
        "zrodlo_url": weryfikacja["url"],
        "data_odczytu": weryfikacja["data_odczytu"],
        "price_verified": potwierdzone,
    }
    notes = (
        "Pociąg Kolei Dolnośląskich na odcinku granicznym Zgorzelec - Görlitz: przejazd "
        f"bezpłatny ({weryfikacja['status']}, odczyt {weryfikacja['data_odczytu']})."
    )
    if not potwierdzone:
        breakdown["powod_szacunku"] = "bezpłatność tylko z raportu Gemini, bez drugiego źródła"
        notes += " Cena niepotwierdzona."
    return PriceEstimate(
        carrier=Carrier.KD_ZGORZELEC_GORLITZ,
        amount=_TABLE["cena"],
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL if potwierdzone else PriceType.ESTIMATE,
        breakdown=breakdown,
        notes=notes,
    )
