"""Klient Travelpayouts Data API (endpoint /v1/prices/cheap) — ceny lotów z cache.

Wymaga darmowego tokena API (rejestracja w programie partnerskim Travelpayouts).
Token podaj w zmiennej środowiskowej TRAVELPAYOUTS_TOKEN — patrz README.md w tym katalogu.
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# .env w katalogu głównym repo; zmienna środowiskowa już ustawiona ma pierwszeństwo (override=False)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE = "https://api.travelpayouts.com/v1"
TOKEN_ENV_VAR = "TRAVELPAYOUTS_TOKEN"


class TravelpayoutsError(RuntimeError):
    """Błąd komunikacji z Travelpayouts Data API albo brak/niepoprawna odpowiedź."""


def _get_token() -> str:
    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise TravelpayoutsError(
            f"Brak tokena API Travelpayouts w zmiennej środowiskowej {TOKEN_ENV_VAR}. "
            "Darmowy token dostępny po rejestracji na "
            "https://www.travelpayouts.com/programs/100/tools/api (sekcja Data API / Access token)."
        )
    return token


def fetch_cheapest_price(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    currency: str = "PLN",
) -> dict:
    """GET /v1/prices/cheap — surowa odpowiedź API (zwalidowana pod kątem success=true).

    depart_date/return_date w formacie "YYYY-MM-DD" lub "YYYY-MM" (zgodnie z API).
    """
    token = _get_token()
    params = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "depart_date": depart_date,
        "currency": currency,
    }
    if return_date:
        params["return_date"] = return_date

    try:
        response = requests.get(
            f"{API_BASE}/prices/cheap",
            params=params,
            headers={"x-access-token": token},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TravelpayoutsError(f"Błąd zapytania do Travelpayouts API: {exc}") from exc

    payload = response.json()
    if not payload.get("success"):
        raise TravelpayoutsError(f"Travelpayouts API zwróciło błąd: {payload.get('error')}")
    return payload


def cheapest_entry_or_none(payload: dict, destination: str) -> dict | None:
    """Jak cheapest_entry, ale zwraca None zamiast podnosić błąd, gdy brak wpisów dla tej
    relacji w odpowiedzi — używane przez calculator.py do próby fallbacku (np. cache
    miesięczny) zamiast od razu odrzucać cały wariant lotu."""
    data = payload.get("data") or {}
    entries = data.get(destination.upper())
    if not entries:
        return None
    # Klucze "0"/"1"/"2" w /v1/prices/cheap to numer kolejny wyniku, NIE liczba przesiadek
    # (dokumentacja Travelpayouts), a odpowiedź nie ma pola z przesiadkami — więc nie wiemy ile ich jest.
    _, best = min(entries.items(), key=lambda item: item[1]["price"])
    return {**best, "transfers": None}


def cheapest_entry(payload: dict, destination: str) -> dict:
    """Wybiera najtańszy wpis spośród wyników dla danego kierunku (liczba przesiadek nieznana).
    """
    entry = cheapest_entry_or_none(payload, destination)
    if entry is None:
        raise TravelpayoutsError(
            f"Brak cen dla relacji -> {destination.upper()} w odpowiedzi Travelpayouts "
            "(zbyt egzotyczna trasa albo data poza zakresem cache)."
        )
    return entry


def fetch_direct_tickets(
    origin: str, destination: str, departure_at: str, currency: str = "PLN"
) -> list[dict]:
    """GET /aviasales/v3/prices_for_dates z direct=true — bilety bezpośrednie (transfers == 0)
    z cache Travelpayouts dla daty ("YYYY-MM-DD") albo miesiąca ("YYYY-MM").

    Używane do potwierdzania, że lot bezpośredni między lotniskami w ogóle istnieje. Uwaga:
    /v1/prices/cheap NIE nadaje się do tego — klucze "0"/"1"/"2" w jego odpowiedzi to numer
    kolejny wyniku, nie liczba przesiadek (dokumentacja Travelpayouts). Pusta lista oznacza
    brak biletu bezpośredniego W CACHE, a nie dowód braku lotu."""
    token = _get_token()
    try:
        response = requests.get(
            "https://api.travelpayouts.com/aviasales/v3/prices_for_dates",
            params={
                "origin": origin.upper(),
                "destination": destination.upper(),
                "departure_at": departure_at,
                "direct": "true",
                "one_way": "true",
                "sorting": "price",
                "limit": 30,
                "currency": currency,
            },
            headers={"x-access-token": token},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TravelpayoutsError(f"Błąd zapytania do Travelpayouts API: {exc}") from exc
    payload = response.json()
    if not payload.get("success"):
        raise TravelpayoutsError(f"Travelpayouts API zwróciło błąd: {payload.get('error')}")
    return [t for t in payload.get("data") or [] if t.get("transfers") == 0]
