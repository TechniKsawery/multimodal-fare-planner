"""Bardzo uproszczone przeliczanie walut do PLN — tylko do PORÓWNYWANIA wariantów.

Kursy są SZTYWNYM PLACEHOLDEREM (nie z API kursowego) — patrz README.md w tym katalogu.
Do rzeczywistej ceny każdego odcinka i tak używamy oryginalnej walutysą (breakdown w PricedLeg),
PLN-owa suma służy wyłącznie do rankingu "najtańsza" i scoringu "cena/godzina" między wariantami
mieszającymi PLN i EUR.
"""

PLACEHOLDER_RATES_TO_PLN = {
    "PLN": 1.0,
    "EUR": 4.30,
}


def _rate(currency: str) -> float:
    rate = PLACEHOLDER_RATES_TO_PLN.get(currency.upper())
    if rate is None:
        raise ValueError(
            f"Brak placeholderowego kursu dla waluty {currency!r} — dodaj go w "
            "routing/currency.py (PLACEHOLDER_RATES_TO_PLN)."
        )
    return rate


def to_pln(amount: float, currency: str) -> float:
    return amount * _rate(currency)


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Przelicza między dwiema walutami przez PLN (PLACEHOLDER_RATES_TO_PLN) — np. bagaż w EUR
    z cennika przewoźnika na walutę, w jakiej liczony jest segment lotu (flight_currency)."""
    if from_currency.upper() == to_currency.upper():
        return amount
    return to_pln(amount, from_currency) / _rate(to_currency)
