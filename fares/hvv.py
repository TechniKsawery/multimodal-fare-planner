"""Szacowanie ceny segmentu komunikacji miejskiej HVV (Hamburg): Einzelkarte najniższej
strefy (1-2 Ringe / Hamburg AB).

Dane pochodzą z oficjalnego cennika HVV (Tarifstand 01.01.2026), zweryfikowanego w przeglądarce
— patrz pole "_zrodlo" w fares/data/hvv.json oraz README.md w tym katalogu. Taryfa HVV jest
strefowa (Ringe), a nie mamy mapowania przystanek->Ring, więc kalkulator zawsze liczy najniższą
strefę — to NIEDOSZACOWUJE realną cenę dla relacji obejmujących więcej Ringów.

Zniżka dla osób z ciężką niepełnosprawnością (Wertmarke, § 228 SGB IX) jest ogólnoniemiecka,
nie specyficzna dla HVV — patrz komentarz przy DiscountProfile.schwerbehinderte_wertmarke_de
w fares/model.py.
"""

from ._data_loading import load
from ._dzieci_do_6 import bezplatne_dziecko, dziecko_ponizej_6
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("hvv.json")


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.HVV:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora HVV: {segment.carrier}")

    if dziecko_ponizej_6(segment):
        return bezplatne_dziecko(segment, _TABLE)

    if segment.discounts.schwerbehinderte_wertmarke_de:
        return PriceEstimate(
            carrier=Carrier.HVV,
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
                "całego lokalnego transportu HVV."
            ),
        )

    dziecko = segment.discounts.hvv_dziecko
    bilet = _TABLE["einzelkarte_najnizsza_strefa"]
    amount = bilet["dziecko"] if dziecko else bilet["normalny"]

    return PriceEstimate(
        carrier=Carrier.HVV,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelkarte dziecko" if dziecko else "Einzelkarte normalny",
            "strefa": "1-2 Ringe / Hamburg AB (przybliżenie najniższej strefy)",
            "zrodlo_url": _TABLE.get("zrodlo_url"),
            "data_weryfikacji": _TABLE.get("data_weryfikacji"),
        },
        notes=(
            "Taryfa HVV (Tarifstand 01.01.2026): Einzelkarte najniższej strefy (1-2 Ringe / "
            "Hamburg AB). Kindertarif 6-14 lat (dzieci do 6 lat jeżdżą bezpłatnie, poza "
            "zakresem tego pola — patrz fares/data/hvv.json). Brak mapowania przystanek->Ring "
            "— relacje obejmujące więcej Ringów są w rzeczywistości droższe niż ten wynik "
            "(patrz pełna tabela stref w fares/data/hvv.json)."
        ),
    )
