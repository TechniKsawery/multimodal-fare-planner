from datetime import date

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("ztm_warszawa.json")
_BILETY = sorted(_TABLE["bilety_czasowe"], key=lambda b: b["wazny_min"])
_NAJDLUZSZY = _BILETY[-1]
_DZIECI_BEZPLATNE = _TABLE.get("dzieci_bezplatne")
_DZIECI_ULGOWE = _TABLE.get("dzieci_ulgowe")


def _wybierz_bilet(duration_min: float) -> dict:
    for bilet in _BILETY:
        if duration_min <= bilet["wazny_min"]:
            return bilet
    return _NAJDLUZSZY


def _uprawnienia_wiekowe(segment: Segment) -> tuple[bool, bool, bool, str | None]:
    """Zwraca (czy_bezplatny, czy_ulgowy, czy_szacunek, opis)."""
    age = segment.discounts.age
    if age is None or not _DZIECI_BEZPLATNE:
        return False, False, False, None
    limit_bezplatny = _DZIECI_BEZPLATNE["do_wieku"]
    if age < limit_bezplatny - 1:
        return True, False, False, f"dziecko do 30.09 roku ukończenia {limit_bezplatny} lat"
    if age == limit_bezplatny - 1:
        if segment.travel_date:
            d = date.fromisoformat(segment.travel_date)
            if (d.month, d.day) <= (9, 30):
                return True, False, True, "dziecko w wieku 6 lat przed 30.09 (status bezpłatny/ulgowy zależy od daty urodzenia)"
            else:
                return False, True, True, "dziecko w wieku 6 lat po 30.09 (status bezpłatny/ulgowy zależy od daty urodzenia)"
        return False, True, True, "dziecko w wieku 6 lat (status bezpłatny/ulgowy zależy od daty urodzenia)"
    if age == limit_bezplatny:
        if segment.travel_date:
            d = date.fromisoformat(segment.travel_date)
            if (d.month, d.day) <= (9, 30):
                return True, False, True, "dziecko w wieku 7 lat do 30.09 (status bezpłatny/ulgowy zależy od daty urodzenia)"
            else:
                return False, True, False, "dziecko w wieku 7 lat po 30.09 (bilet ulgowy)"
        return False, True, True, "dziecko w wieku 7 lat (status bezpłatny/ulgowy zależy od daty urodzenia)"
    if _DZIECI_ULGOWE:
        limit_ulgowy = _DZIECI_ULGOWE["do_wieku"]
        if limit_bezplatny < age < limit_ulgowy:
            return False, True, False, f"dziecko od 1.10 roku ukończenia 7 lat do {limit_ulgowy} lat"
    return False, False, False, None


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.ZTM_WARSZAWA:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora ZTM Warszawa: {segment.carrier}"
        )
    if segment.ride_duration_min is None:
        raise ValueError("ZTM Warszawa (taryfa czasowa): ride_duration_min jest wymagane")

    bilet = _wybierz_bilet(segment.ride_duration_min)
    wiek_bezplatny, wiek_ulgowy, wiek_szacunek, opis_wieku = _uprawnienia_wiekowe(segment)
    bezplatny = segment.discounts.ztm_warszawa_bezplatny or wiek_bezplatny
    ulgowy = segment.discounts.ztm_warszawa_ulgowy or wiek_ulgowy
    if bezplatny:
        amount = 0.0
        typ_biletu = "bezpłatny (100%)"
    elif ulgowy:
        amount = bilet["ulgowy"]
        typ_biletu = "ulgowy (50%)"
    else:
        amount = bilet["normalny"]
        typ_biletu = "normalny"
    przekroczono = segment.ride_duration_min > _NAJDLUZSZY["wazny_min"]
    jest_szacunek = przekroczono or (wiek_szacunek and not segment.discounts.ztm_warszawa_bezplatny)

    return PriceEstimate(
        carrier=Carrier.ZTM_WARSZAWA,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE if jest_szacunek else PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "czas_jazdy_min": segment.ride_duration_min,
            "bilet_wazny_min": bilet["wazny_min"],
            "typ_biletu": typ_biletu,
            "strefa": bilet.get("strefa", "1+2"),
            **(
                {"powod_bezplatny": opis_wieku}
                if wiek_bezplatny and not segment.discounts.ztm_warszawa_bezplatny
                else {}
            ),
            **(
                {"uprawnienie_wiek": opis_wieku}
                if wiek_ulgowy and not segment.discounts.ztm_warszawa_ulgowy
                else {}
            ),
            **({"wiek_status_szacunek": True} if wiek_szacunek and not segment.discounts.ztm_warszawa_bezplatny else {}),
        },
        notes=(
            f"Taryfa czasowa ZTM Warszawa ({_TABLE['nazwa_przewoznika']}): dobrano "
            f"bilet {bilet['wazny_min']}-minutowy."
            + (
                f" Przejazd bezpłatny z wieku: {opis_wieku}."
                if wiek_bezplatny and not segment.discounts.ztm_warszawa_bezplatny
                else ""
            )
            + (
                f" Ulga z wieku: {opis_wieku}."
                if wiek_ulgowy and not segment.discounts.ztm_warszawa_ulgowy
                else ""
            )
            + (
                (
                    " Dla dziecka w wieku 6 lat status bezpłatny/ulgowy zależy od daty urodzenia "
                    "(czy 7. urodziny przypadają w roku podróży, czy w następnym) — wynik to szacunek."
                    if segment.discounts.age == 6
                    else (
                        " Dla dziecka w wieku 7 lat status bezpłatny/ulgowy zależy od daty urodzenia "
                        "(czy 7. urodziny przypadają w roku podróży, czy w poprzednim) — wynik to szacunek."
                        if segment.discounts.age == 7
                        else ""
                    )
                )
                if wiek_szacunek and not segment.discounts.ztm_warszawa_bezplatny
                else ""
            )
            + (
                f" Czas jazdy ({segment.ride_duration_min:.0f} min) przekracza najdłuższy dostępny "
                f"bilet ({_NAJDLUZSZY['wazny_min']} min) — cena to szacunek."
                if przekroczono
                else ""
            )
        ),
    )
