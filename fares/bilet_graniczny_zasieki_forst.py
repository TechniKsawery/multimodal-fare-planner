"""Bilet graniczny Polska-Niemcy na odcinku Zasieki - Forst: stała cena 5,00 zł, w jedną stronę.

Dane: fares/data/bilet_graniczny_zasieki_forst.json (regulamin PDF: cena str. 1 §2 ust. 1, brak ulg
ustawowych §5 ust. 2, od 2024-10-01; odczyt 2026-10-13). Źródła: PDF regulaminu i strona KD
(oferty przygraniczne), URL-e w JSON. Bilet jest DODATKIEM do biletu krajowego KD do Zasieki
(strona KD: "oprócz biletu krajowego do Zasieki"). Bilet ważny na KD Zasieki - Zasieki(Gr) i
DB Regio Zasieki(Gr) - Forst. Ulg ustawowych brak, więc uczniowie i studenci płacą pełną cenę; gratis tylko dzieci poniżej progu wieku z JSON (age < 6).
Brak wieku = cena pełna. Posiadacze Dolnośląskiego Biletu Weekendowego, miesięcznego sieciowego
KD, Brandenburg-Berlin-Ticket i Schönes-Wochenende-Ticket jadą bez dopłaty 5 zł (strona KD);
DiscountProfile nie ma na to pól, więc to INFORMACJA w notes + flaga w breakdown, cena bez zmian."""

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
    bez_doplaty = _TABLE["bilety_bez_doplaty"]
    breakdown = {
        "relacja": f"{segment.origin} <-> {segment.destination}",
        "typ_biletu": "Bilet graniczny Polska-Niemcy" + (" (dziecko gratis)" if gratis else ""),
        "kierunek": _TABLE["kierunek"],
        "ulgi_ustawowe": _TABLE["ulgi_ustawowe"],
        "obowiazuje_od": _TABLE["obowiazuje_od"],
        "price_verified": True,
        "status_weryfikacji": weryfikacja["status"],
        "zrodlo_url": weryfikacja["url"],
        "zrodlo_url_strony": weryfikacja["url_strony"],
        "dodatek_do_biletu_krajowego": True,
        "bilety_bez_doplaty": list(bez_doplaty["bilety"]),
        "bilet_bez_doplaty_info_niezweryfikowany_w_profilu": True,
        "okaziciel": _TABLE["okaziciel"],
        "max_osob_na_blankiecie": _TABLE["max_osob_na_blankiecie"],
        "bagaz_rower_pies_bezplatnie": _TABLE["bagaz_rower_pies_bezplatnie"],
        "przedsprzedaz_dni": _TABLE["przedsprzedaz_dni"],
        "dzieci_gratis_niejednoznaczne": _TABLE["dzieci_gratis_niejednoznaczne"],
        "data_odczytu": weryfikacja["data_odczytu"],
    }
    notes = (
        "Bilet graniczny Polska-Niemcy Zasieki - Forst (KD Zasieki - Zasieki(Gr) + DB Regio "
        f"Zasieki(Gr) - Forst), w jedną stronę, od {_TABLE['obowiazuje_od']}; regulamin odczytany "
        f"{weryfikacja['data_odczytu']}. {_TABLE['dodatek_do_biletu_krajowego']['tresc']} "
        f"Bilet na okaziciela (do {_TABLE['max_osob_na_blankiecie']} osób na blankiecie), rower, "
        f"bagaż i pies bezpłatnie, przedsprzedaż {_TABLE['przedsprzedaz_dni']} dni. "
        f"{bez_doplaty['tresc']} Profil pasażera nie obejmuje jeszcze tych biletów, więc cena "
        "nie jest obniżana - jeśli masz któryś z nich, dopłata 5 zł nie obowiązuje. "
    )
    if gratis:
        notes += (
            f"Dziecko do {_TABLE['dzieci_gratis_wiek_ponizej']} lat (wiek {segment.discounts.age}) "
            "jedzie bezpłatnie (granica wieku w regulaminie niejednoznaczna: poniżej 6 lat "
            "traktowane jako gratis)."
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
