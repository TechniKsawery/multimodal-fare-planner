"""Szacowanie ceny segmentu komunikacji miejskiej w Kolonii: VRS/Rheinlandtarif, Preisstufe
1b (przejazd w obrębie miasta Kolonii lub Bonn — oficjalnie nazwana strefa, nie przybliżenie).

Dane pochodzą z oficjalnej angielskiej strony dialogforum.vrs.de ("Ticket assortment" ->
"Einzeltickets"), zweryfikowanej 2026-10-10 — patrz pole "_zrodlo" w fares/data/vrs_koln.json
oraz README.md w tym katalogu. To źródło NAZYWA jednoznacznie każdy poziom cenowy (1a = gmina
w której się jest, poza Kolonią/Bonn; 1b = przejazd w obrębie Kolonii lub Bonn; 2a/2b/3/4/5 =
coraz dalsze relacje), co rozwiązuje wcześniejszą niejednoznaczność mapowania nazwa->kwota
(poprzednia wersja tego kalkulatora miała price_type=ESTIMATE z tego powodu).

Zniżka dla osób z ciężką niepełnosprawnością (Wertmarke, § 228 SGB IX) jest ogólnoniemiecka,
nie specyficzna dla VRS — patrz komentarz przy DiscountProfile.schwerbehinderte_wertmarke_de
w fares/model.py.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("vrs_koln.json")
_POZIOMY = {p["poziom"]: p for p in _TABLE["poziomy_cenowe"]}
_DOMYSLNY = _POZIOMY[_TABLE["poziom_uzywany_domyslnie"]]


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.VRS_KOLN:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora VRS/Köln: {segment.carrier}")

    if segment.discounts.schwerbehinderte_wertmarke_de:
        return PriceEstimate(
            carrier=Carrier.VRS_KOLN,
            amount=0.0,
            currency=_TABLE["waluta"],
            price_type=PriceType.OFFICIAL,
            breakdown={
                "relacja": f"{segment.origin} <-> {segment.destination}",
                "typ_biletu": "bezpłatny (Schwerbehinderte, Wertmarke)",
            },
            notes=(
                "Bezpłatny przejazd dla osób z ciężką niepełnosprawnością z ważną Wertmarke "
                "w legitymacji (§ 228 SGB IX) — zasada ogólnoniemiecka, dotyczy identycznie "
                "całego lokalnego transportu VRS/KVB."
            ),
        )

    dziecko = segment.discounts.vrs_koln_dziecko
    amount = _DOMYSLNY["dziecko"] if dziecko else _DOMYSLNY["normalny"]

    return PriceEstimate(
        carrier=Carrier.VRS_KOLN,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.OFFICIAL,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "Einzelticket dziecko" if dziecko else "Einzelticket normalny",
            "poziom_cenowy": _DOMYSLNY["poziom"],
        },
        notes=(
            "Taryfa VRS/Rheinlandtarif: Preisstufe 1b (przejazd w obrębie Kolonii lub Bonn), "
            "Kindertarif 6-14 lat, dzieci do 6 lat jeżdżą bezpłatnie (poza zakresem tego pola "
            "— patrz fares/data/vrs_koln.json). Dla relacji wychodzących poza miasto (Preisstufe "
            "2a i wyżej) rzeczywista cena jest wyższa — patrz pełna tabela w "
            "fares/data/vrs_koln.json."
        ),
    )
