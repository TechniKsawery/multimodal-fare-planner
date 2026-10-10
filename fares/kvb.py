"""Szacowanie ceny segmentu komunikacji miejskiej w Kolonii: VRS/Rheinlandtarif, najniższy
potwierdzony poziom cenowy (przybliżenie przejazdu w obrębie miasta Kolonii).

Dane pochodzą z oficjalnej strony VRS (nowy "Rheinlandtarif" 2026), zweryfikowanej w
przeglądarce — patrz pole "_zrodlo"/"_uwaga" w fares/data/vrs_koln.json oraz README.md w tym
katalogu. UWAGA: w przeciwieństwie do HVV/MVV, tu nawet przypisanie NAZWY poziomu cenowego
(Kurzstrecke/Preisstufe 1a/1b/...) do konkretnej kwoty nie jest w 100% potwierdzone — kwoty same
są ze strony operatora, ale które dokładnie oznaczają przejazd miejski w Kolonii, nie jest jasne.
Dlatego wynik ma price_type=ESTIMATE, nie OFFICIAL.
"""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("vrs_koln.json")
_POZIOMY = {p["poziom"]: p for p in _TABLE["poziomy_cenowe"]}
_DOMYSLNY = _POZIOMY[_TABLE["poziom_uzywany_domyslnie"]]


def estimate(segment: Segment) -> PriceEstimate:
    if segment.carrier is not Carrier.VRS_KOLN:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora VRS/Köln: {segment.carrier}")

    dziecko = segment.discounts.vrs_koln_dziecko
    amount = _DOMYSLNY["dziecko"] if dziecko else _DOMYSLNY["normalny"]

    return PriceEstimate(
        carrier=Carrier.VRS_KOLN,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "relacja": f"{segment.origin} <-> {segment.destination}",
            "typ_biletu": "dziecko" if dziecko else "normalny",
            "poziom_cenowy": _DOMYSLNY["poziom"],
        },
        notes=(
            "Taryfa VRS/Rheinlandtarif (Kolonia): użyto najniższego potwierdzonego poziomu "
            "cenowego jako przybliżenia przejazdu w obrębie miasta. Przypisanie nazwy poziomu "
            "(Kurzstrecke/Preisstufe) do tej kwoty nie jest w 100% potwierdzone u źródła — "
            "wynik oznaczony jako szacunek, nie oficjalna taryfa."
        ),
    )
