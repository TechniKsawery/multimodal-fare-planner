"""Klient Travelpayouts Data API (endpoint /v1/prices/cheap) — ceny lotów z cache.

Wymaga darmowego tokena API (rejestracja w programie partnerskim Travelpayouts).
Token podaj w zmiennej środowiskowej TRAVELPAYOUTS_TOKEN — patrz README.md w tym katalogu.
"""
import os
from typing import Optional

import requests

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
    return_date: Optional[str] = None,
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


def cheapest_entry(payload: dict, destination: str) -> dict:
    """Wybiera najtańszy wpis (spośród bezpośrednich / 1 / 2 przesiadek) dla danego kierunku.

    /v1/prices/cheap grupuje wyniki wg liczby przesiadek (klucze "0"/"1"/"2"), więc żeby
    dostać jedną, faktycznie najtańszą cenę trzeba porównać ceny między tymi wpisami.
    """
    data = payload.get("data") or {}
    entries = data.get(destination.upper())
    if not entries:
        raise TravelpayoutsError(
            f"Brak cen dla relacji -> {destination.upper()} w odpowiedzi Travelpayouts "
            "(zbyt egzotyczna trasa albo data poza zakresem cache)."
        )

    best_stops, best = min(entries.items(), key=lambda item: item[1]["price"])
    return {**best, "transfers": int(best_stops)}
