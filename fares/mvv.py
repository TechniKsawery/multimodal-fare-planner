"""Szacowanie ceny segmentu komunikacji miejskiej MVV (Monachium): Einzelkarte Zone M
(najniższa strefa, centrum Monachium).

Dane pochodzą z oficjalnego cennika MVV (ceny od 01.01.2026), zweryfikowanego w przeglądarce
— patrz pole "_zrodlo" w fares/data/mvv.json oraz README.md w tym katalogu. Taryfa MVV jest
strefowa (Zone M + strefy 1-12), a nie mamy mapowania przystanek->strefa, więc kalkulator
zawsze liczy Zone M — to NIEDOSZACOWUJE realną cenę dla relacji wychodzących poza Zone M.

Zniżka dla osób z ciężką niepełnosprawnością (Wertmarke, § 228 SGB IX) jest ogólnoniemiecka,
nie specyficzna dla MVV — patrz komentarz przy DiscountProfile.schwerbehinderte_wertmarke_de
w fares/model.py.
"""

from ._data_loading import load
from ._dzieci_do_6 import bezplatne_dziecko, dziecko_ponizej_6
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("mvv.json")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.MVV:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora MVV: {segment.carrier}")

    if dziecko_ponizej_6(segment):
        return bezplatne_dziecko(segment, _TABLE)

    if segment.discounts.schwerbehinderte_wertmarke_de:
        return PriceEstimate(
            carrier=Carrier.MVV,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.OFFICIAL,
            breakdown={
                "relacja": f"{segment.origin} <-> {segment.destination}",
                "typ_biletu": "bezpłatny (Schwerbehinderte, Wertmarke)",
                "zrodlo_url": _TABLE.get("zrodlo_url"),
                "data_weryfikacji": _TABLE.get("data_weryfikacji"),
            },
            notes=(
                "Bezpłatny przejazd dla osób z ciężką niepełnosprawnością z ważną Wertmarke "
                "w legitymacji (§ 228 SGB IX) — zasada ogólnoniemiecka, dotyczy identycznie "
                "całego lokalnego transportu MVV."
            ),
        )

    dziecko = segment.discounts.mvv_dziecko
    bilet = _TABLE["einzelkarte_zone_m"]
    amount = bilet["dziecko"] if dziecko else bilet["normalny"]

    return PriceEstimate(
        carrier=Carrier.MVV,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelkarte dziecko" if dziecko else "Einzelkarte normalny",
            "strefa": "Zone M (przybliżenie najniższej strefy)",
            "zrodlo_url": _TABLE.get("zrodlo_url"),
            "data_weryfikacji": _TABLE.get("data_weryfikacji"),
        },
        notes=(
            "Taryfa MVV (ceny od 01.01.2026): Einzelkarte Zone M. Kindertarif 6-14 lat (dzieci "
            "do 6 lat jeżdżą bezpłatnie, poza zakresem tego pola — patrz fares/data/mvv.json). "
            "Brak mapowania przystanek->strefa — relacje wychodzące poza Zone M (strefy 1-12) "
            "są w rzeczywistości droższe niż ten wynik."
        ),
    )
