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


def to_pln(amount: float, currency: str) -> float:
    rate = PLACEHOLDER_RATES_TO_PLN.get(currency.upper())
    if rate is None:
        raise ValueError(
            f"Brak placeholderowego kursu dla waluty {currency!r} — dodaj go w "
            "routing/currency.py (PLACEHOLDER_RATES_TO_PLN)."
        )
    return amount * rate
