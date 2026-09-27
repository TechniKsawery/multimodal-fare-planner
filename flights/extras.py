"""Placeholderowa tabela kosztów dodatkowych (bagaż, dojazd, transfer) dla wybranych relacji.

Dane w flights/data/extras_placeholder.json są PRZYKŁADOWE — patrz README.md w tym katalogu.
"""
from typing import Optional, Tuple

from .model import ExtrasProfile
from ._data_loading import load

_TABLE = load("extras_placeholder.json")
_BAGGAGE_BY_AIRLINE = load("baggage_by_airline.json")


def _key(origin: str, destination: str) -> str:
    return f"{origin.upper()}-{destination.upper()}"


def get_extras(origin: str, destination: str) -> ExtrasProfile:
    """Zwraca ExtrasProfile dla relacji, albo profil zerowy z notatką, jeśli relacja nieznana."""
    entry = _TABLE["relacje"].get(_key(origin, destination))
    currency = _TABLE.get("waluta", "PLN")

    if entry is None:
        return ExtrasProfile(
            currency=currency,
            note=(
                "Brak danych o kosztach dodatkowych dla tej relacji w placeholderowej tabeli — "
                "podaj własny ExtrasProfile albo dolicz bagaż/dojazd/transfer ręcznie."
            ),
        )

    return ExtrasProfile(
        baggage_cost=entry["bagaz"],
        airport_access_cost=entry["dojazd_na_lotnisko"],
        destination_transfer_cost=entry["transfer_z_lotniska"],
        currency=currency,
        note="Koszty dodatkowe z placeholderowej tabeli — nie realne ceny bagażu/dojazdu/transferu.",
    )


def get_baggage_by_airline(airline_code: Optional[str]) -> Optional[Tuple[float, str, str]]:
    """Zwraca (kwota, waluta, opis_zrodla) dla znanego kodu IATA przewoźnika, albo None gdy
    przewoźnik nieznany w tabeli.

    Dane w flights/data/baggage_by_airline.json to REALNE cenniki (Ryanair, Wizz Air, LOT,
    Eurowings) sprawdzone w publicznych źródłach — ale opłaty za bagaż u tanich linii są
    DYNAMICZNE (zależą od trasy/terminu/sezonu), więc kwota to dolna granica opublikowanego
    przedziału, nie gwarantowana cena konkretnego lotu — patrz README.md."""
    if not airline_code:
        return None
    entry = _BAGGAGE_BY_AIRLINE["przewoznicy"].get(airline_code.upper())
    if entry is None:
        return None
    return entry["koszt"], entry["waluta"], f"{entry['nazwa']}: {entry['zakres']} (źródło: {entry['zrodlo']})"
