"""Klient Travelpayouts Data API (endpoint /v1/prices/cheap) — ceny lotów z cache.

Wymaga darmowego tokena API (rejestracja w programie partnerskim Travelpayouts).
Token podaj w zmiennej środowiskowej TRAVELPAYOUTS_TOKEN — patrz README.md w tym katalogu.
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from i18n import Msg

# .env w katalogu głównym repo; zmienna środowiskowa już ustawiona ma pierwszeństwo (override=False)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE = "https://api.travelpayouts.com/v1"
TOKEN_ENV_VAR = "TRAVELPAYOUTS_TOKEN"


class TravelpayoutsError(RuntimeError):
    """Błąd komunikacji z Travelpayouts Data API albo brak/niepoprawna odpowiedź. Komunikat może
    być `i18n.Msg` (UI renderuje go w wybranym języku przez `i18n.exc_text` + `tm`)."""


def _get_token() -> str:
    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise TravelpayoutsError(Msg("err.tp_no_token", var=TOKEN_ENV_VAR))
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
        raise TravelpayoutsError(Msg("err.tp_request", error=str(exc))) from exc

    payload = response.json()
    if not payload.get("success"):
        raise TravelpayoutsError(Msg("err.tp_api", error=str(payload.get("error"))))
    return payload


DIRECT_KEY = "0"
"""Klucz wpisu bez przesiadek w data[<IATA>] odpowiedzi /v1/prices/cheap. Klucze "0"/"1"/"2" to
liczba przesiadek (0 = lot bezpośredni), a NIE numer kolejny wyniku — patrz flights/README.md,
sekcja "Znaczenie kluczy"."""


def cheapest_entry_or_none(payload: dict, destination: str) -> dict | None:
    """Wpis z BEZPOŚREDNIM lotem (klucz "0") dla relacji albo None, gdy go brak.

    Wpisy z kluczy "1"/"2" (lot z przesiadkami) są ignorowane — nie wolno ich podawać jako lotu
    bezpośredniego. None oznacza dla calculator.py próbę fallbacku (cache miesięczny), a na końcu
    szacunek z etykietą "cena niepotwierdzona"."""
    data = payload.get("data") or {}
    entries = data.get(destination.upper())
    if not entries:
        return None
    direct = entries.get(DIRECT_KEY)
    if not direct:
        return None
    return {**direct, "transfers": 0}


def cheapest_entry(payload: dict, destination: str) -> dict:
    """Jak cheapest_entry_or_none, ale podnosi błąd, gdy brak bezpośredniego wpisu dla relacji."""
    entry = cheapest_entry_or_none(payload, destination)
    if entry is None:
        raise TravelpayoutsError(Msg("err.tp_no_direct_price", destination=destination.upper()))
    return entry


def fetch_direct_tickets(
    origin: str, destination: str, departure_at: str, currency: str = "PLN"
) -> list[dict]:
    """GET /aviasales/v3/prices_for_dates z direct=true — bilety bezpośrednie (transfers == 0)
    z cache Travelpayouts dla daty ("YYYY-MM-DD") albo miesiąca ("YYYY-MM").

    Używane do potwierdzania, że lot bezpośredni między lotniskami w ogóle istnieje (filtrujemy
    jeszcze po stronie klienta po transfers == 0). Pusta lista oznacza brak biletu
    bezpośredniego W CACHE, a nie dowód braku lotu."""
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
        raise TravelpayoutsError(Msg("err.tp_request", error=str(exc))) from exc
    payload = response.json()
    if not payload.get("success"):
        raise TravelpayoutsError(Msg("err.tp_api", error=str(payload.get("error"))))
    return [t for t in payload.get("data") or [] if t.get("transfers") == 0]
