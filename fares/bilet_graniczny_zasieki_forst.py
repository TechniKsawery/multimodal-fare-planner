"""Bilet graniczny Polska-Niemcy na odcinku Zasieki - Forst: stała cena 5,00 zł, w jedną stronę.

Dane: fares/data/bilet_graniczny_zasieki_forst.json (regulamin PDF: cena str. 1 §2 ust. 1, brak ulg
ustawowych §5 ust. 2, od 2024-10-01; odczyt 2026-10-13). URL regulaminu jest do uzupełnienia.
Bilet ważny na KD Zasieki - Zasieki(Gr) i DB Regio Zasieki(Gr) - Forst. Ulg ustawowych brak, więc
uczniowie i studenci płacą pełną cenę; gratis tylko dzieci poniżej progu wieku z JSON (age < 6).
Brak wieku = cena pełna."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("bilet_graniczny_zasieki_forst.json")


def dziecko_gratis(segment: Segment) -> bool:
    age = segment.discounts.age
    return age is not None and age < _TABLE["dzieci_gratis_wiek_ponizej"]


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.BILET_GRANICZNY_ZASIEKI_FORST:
        raise ValueError(
            f"nieprawidłowy przewoźnik dla kalkulatora biletu granicznego: {segment.carrier}"
        )

    weryfikacja = _TABLE["weryfikacja"]
    gratis = dziecko_gratis(segment)
    breakdown = {
        "relacja": f"{segment.origin} <-> {segment.destination}",
        "typ_biletu": "Bilet graniczny Polska-Niemcy" + (" (dziecko gratis)" if gratis else ""),
        "kierunek": _TABLE["kierunek"],
        "ulgi_ustawowe": _TABLE["ulgi_ustawowe"],
        "obowiazuje_od": _TABLE["obowiazuje_od"],
        "price_verified": True,
        "status_weryfikacji": weryfikacja["status"],
        "zrodlo_url": weryfikacja["url"],
        "zrodlo_url_do_uzupelnienia": weryfikacja["url_do_uzupelnienia"],
        "data_odczytu": weryfikacja["data_odczytu"],
    }
    notes = (
        "Bilet graniczny Polska-Niemcy Zasieki - Forst (KD Zasieki - Zasieki(Gr) + DB Regio "
        f"Zasieki(Gr) - Forst), w jedną stronę, od {_TABLE['obowiazuje_od']}; regulamin odczytany "
        f"{weryfikacja['data_odczytu']} (URL do uzupełnienia). "
    )
    if gratis:
        notes += (
            f"Dziecko do {_TABLE['dzieci_gratis_wiek_ponizej']} lat (wiek {segment.discounts.age}) "
            "jedzie bezpłatnie."
        )
    else:
        notes += (
            "Stała cena; brak ulg ustawowych (§5 ust. 2), uczniowie i studenci płacą pełną cenę."
        )
    return PriceEstimate(
        carrier=Carrier.BILET_GRANICZNY_ZASIEKI_FORST,
        amount=0.0 if gratis else _TABLE["cena"],
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown=breakdown,
        notes=notes,
    )
