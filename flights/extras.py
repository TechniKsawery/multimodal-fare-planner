"""Placeholderowa tabela kosztów dodatkowych (bagaż, dojazd, transfer) dla wybranych relacji.

Dane w flights/data/extras_placeholder.json są PRZYKŁADOWE — patrz README.md w tym katalogu.
"""
from .model import ExtrasProfile
from ._data_loading import load

_TABLE = load("extras_placeholder.json")


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
