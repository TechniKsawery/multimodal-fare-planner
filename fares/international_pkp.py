"""Szacowanie WŁASNEJ oferty PKP Intercity na biletach PL-DE ("Oferta Polska-Niemcy") — OSOBNY
produkt sprzedawany na TYCH SAMYCH pociągach co taryfa DB modelowana w fares/international.py
(np. Berlin-Warszawa-Express). Pasażer może kupić bilet w KTÓRYMKOLWIEK z dwóch kanałów, więc
routing/pricing.py liczy obie oferty i pokazuje tańszą jako cenę główną (zob.
routing/pricing.py::price_rail_leg). Patrz fares/data/international_pl_de_pkp.json dla źródeł
i zastrzeżeń (w tym o pominiętej taryfie promocyjnej "Super Promo International").

Relacja rozpoznawana WYŁĄCZNIE po nazwie miasta (dopasowanie podłańcucha, analogicznie do
infer_rail_carrier w routing/pricing.py) — stacja spoza wymienionych w tabeli miast zwraca
None (brak oferty PKP dla tej relacji w naszych danych, nie błąd)."""

from ._data_loading import load
from .model import Carrier, PriceEstimate, PriceType, Segment

_TABLE = load("international_pl_de_pkp.json")


def _matches_any(name: str, keywords: list[str]) -> bool:
    lname = (name or "").lower()
    return any(k in lname for k in keywords)


def _relation_price(origin: str, destination: str) -> tuple[float, str] | None:
    """(cena_eur, etykieta_miasta_pl) dla relacji PL-miasto <-> Berlin, albo None gdy nie
    rozpoznajemy relacji (żaden koniec nie pasuje do "Berlin", oba pasują, albo polski koniec
    nie jest w tabeli relacji)."""
    berlin_kw = _TABLE["berlin_miasta"]
    o_is_berlin = _matches_any(origin, berlin_kw)
    d_is_berlin = _matches_any(destination, berlin_kw)
    if o_is_berlin == d_is_berlin:
        return None
    pl_side = destination if o_is_berlin else origin
    for relacja in _TABLE["relacje"]:
        if _matches_any(pl_side, relacja["miasta"]):
            return relacja["cena"], relacja["miasta"][0]
    return None


def estimate_pkp_offer(segment: Segment) -> PriceEstimate | None:
    """None, gdy relacja (origin/destination) nie jest rozpoznana w tabeli — wtedy brak oferty
    PKP dla tego segmentu, routing/pricing.py pokazuje wyłącznie taryfę DB."""
    if segment.carrier is not Carrier.INTERNATIONAL_PL_DE:
        raise ValueError(f"nieprawidłowy przewoźnik dla kalkulatora PKP PL-DE: {segment.carrier}")

    dopasowanie = _relation_price(segment.origin, segment.destination)
    if dopasowanie is None:
        return None
    cena_regularna, etykieta_relacji = dopasowanie

    age = segment.discounts.age
    kategoria_wieku = "normalny"
    rabat_procent = 0
    if age is not None and age < _TABLE["niemowle_wiek_max"]:
        kategoria_wieku = "niemowle"
        rabat_procent = _TABLE["niemowle_rabat_procent"]
    elif age is not None and _TABLE["dziecko_wiek_min"] <= age <= _TABLE["dziecko_wiek_max"]:
        kategoria_wieku = "dziecko"
        rabat_procent = _TABLE["dziecko_rabat_procent"]

    amount = round(cena_regularna * (1 - rabat_procent / 100), 2)

    return PriceEstimate(
        carrier=Carrier.INTERNATIONAL_PL_DE,
        amount=amount,
        currency=_TABLE["waluta"],
        price_type=PriceType.ESTIMATE,
        breakdown={
            "oferta": "pkp_oferta_polska_niemcy",
            "relacja_miasto_pl": etykieta_relacji,
            "cena_regularna": cena_regularna,
            "kategoria_wieku": kategoria_wieku,
            "rabat_procent": rabat_procent,
            "wiek": age,
        },
        notes=(
            f"Własna oferta PKP Intercity 'Polska-Niemcy' (cennik regularny, 2 klasa) na tym "
            f"samym połączeniu: {cena_regularna:.2f} EUR"
            + (f", kategoria '{kategoria_wieku}' (-{rabat_procent}%)" if rabat_procent else "")
            + ". PKP sprzedaje też tańszą, pulowaną ofertę 'Super Promo International' na tej "
            "samej relacji (zaobserwowana na żywo np. jako 44,90 EUR Warszawa-Berlin na jedną "
            "sprawdzoną datę) — realna cena może być niższa niż ten cennik regularny, ale nie "
            "modelujemy promocji z pojedynczego pomiaru (zob. dane źródłowe)."
        ),
    )
