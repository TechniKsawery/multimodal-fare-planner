"""Bardzo uproszczone przeliczanie walut do PLN — tylko do PORÓWNYWANIA wariantów.

Kursy są STAŁE, wpisane ręcznie ze źródła (tabela A NBP, nie z API kursowego na żywo) — patrz sekcja
"Waluty" w routing/README.md.
Do rzeczywistej ceny każdego odcinka i tak używamy oryginalnej waluty (breakdown w PricedLeg),
PLN-owa suma służy wyłącznie do rankingu "najtańsza" i scoringu "cena/godzina" między wariantami
mieszającymi PLN i EUR.

Kurs EUR zweryfikowany wobec kursu średniego NBP (tabela A, api.nbp.pl) 2026-10-09: 4,3775.
"""

PLACEHOLDER_RATES_TO_PLN = {
    "PLN": 1.0,
    "EUR": 4.3775,
}


SUPPORTED_CURRENCIES = tuple(sorted(PLACEHOLDER_RATES_TO_PLN))
"""Waluty, dla których mamy kurs — NIE dodajemy kursów "na oko": nowa waluta wymaga kursu ze
źródła (np. tabela NBP) wraz z datą weryfikacji w komentarzu przy PLACEHOLDER_RATES_TO_PLN."""


class UnsupportedCurrencyError(ValueError):
    """Waluta bez kursu w PLACEHOLDER_RATES_TO_PLN. Podklasa ValueError, żeby dotychczasowe
    `except ValueError` nadal działały; warstwa API zamienia ją na czytelny błąd 4xx."""


def normalize_currency(currency: str) -> str:
    """Kod waluty wielkimi literami; podnosi UnsupportedCurrencyError dla waluty bez kursu."""
    code = str(currency).strip().upper()
    if code not in PLACEHOLDER_RATES_TO_PLN:
        raise UnsupportedCurrencyError(
            f"Nieobsługiwana waluta {currency!r} — obsługiwane: {', '.join(SUPPORTED_CURRENCIES)}. "
            "Nie zgadujemy kursów; nowa waluta wymaga kursu ze źródła (np. tabela A NBP) "
            "z datą weryfikacji w common/currency.py."
        )
    return code


def _rate(currency: str) -> float:
    return PLACEHOLDER_RATES_TO_PLN[normalize_currency(currency)]


def to_pln(amount: float, currency: str) -> float:
    return amount * _rate(currency)


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Przelicza między dwiema walutami przez PLN (PLACEHOLDER_RATES_TO_PLN) — np. bagaż w EUR
    z cennika przewoźnika na walutę, w jakiej liczony jest segment lotu (flight_currency)."""
    if normalize_currency(from_currency) == normalize_currency(to_currency):
        return amount
    return to_pln(amount, from_currency) / _rate(to_currency)
