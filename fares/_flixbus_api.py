"""Klient nieoficjalnego, ale publicznie dostępnego API FlixBusa (tego samego, którego używa
flixbus.pl/flixbus.de w przeglądarce) do pobierania REALNYCH cen konkretnego przejazdu na
konkretną datę.

WAŻNE: to NIE jest udokumentowane, wspierane API — endpointy są community-known (używane przez
kilka publicznych projektów typu "flixbus-api" na GitHubie), mogą się zmienić bez ostrzeżenia i
FlixBus może w każdej chwili zablokować taki dostęp. Sieć środowiska Claude blokuje ruch do
global.api.flixbus.com (patrz README.md w tym katalogu), więc ten kod NIE BYŁ przetestowany na
żywo — przetestuj go lokalnie u siebie (patrz README) zanim zaczniesz na nim polegać, i popraw
parsowanie odpowiedzi jeśli faktyczny kształt JSON-a się różni od założonego tutaj.
"""
import json
from datetime import datetime
from typing import Optional

import requests

API_BASE = "https://global.api.flixbus.com"

_city_id_cache: dict = {}


class FlixbusApiError(RuntimeError):
    """Błąd komunikacji z API FlixBusa albo nieoczekiwany/niezrozumiały kształt odpowiedzi."""


def _to_flixbus_date(iso_date: str) -> str:
    """"YYYY-MM-DD" -> "dd.mm.yyyy" (format oczekiwany przez search/service/v4/search)."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError as exc:
        raise FlixbusApiError(f"travel_date musi być w formacie YYYY-MM-DD, dostano: {iso_date!r}") from exc


def find_city_id(city_query: str, locale: str = "pl", country: Optional[str] = None) -> str:
    """GET /search/autocomplete/cities — zwraca id pierwszego (najlepiej dopasowanego) miasta.

    Cache w pamięci procesu, żeby nie odpytywać tego samego miasta wielokrotnie w jednej sesji.
    """
    cache_key = (city_query, locale, country)
    if cache_key in _city_id_cache:
        return _city_id_cache[cache_key]

    params = {"q": city_query, "lang": locale}
    if country:
        params["country"] = country

    try:
        response = requests.get(f"{API_BASE}/search/autocomplete/cities", params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FlixbusApiError(f"Błąd zapytania autocomplete FlixBus dla '{city_query}': {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise FlixbusApiError(f"Odpowiedź autocomplete FlixBus nie jest poprawnym JSON-em: {exc}") from exc

    if not payload:
        raise FlixbusApiError(
            f"FlixBus autocomplete nie znalazł żadnego miasta dla zapytania '{city_query}' "
            "(albo endpoint zmienił kształt odpowiedzi)."
        )

    try:
        city_id = str(payload[0]["id"])
    except (KeyError, TypeError, IndexError) as exc:
        raise FlixbusApiError(
            f"Nieoczekiwany kształt odpowiedzi autocomplete FlixBus dla '{city_query}': "
            f"{str(payload)[:300]}"
        ) from exc

    _city_id_cache[cache_key] = city_id
    return city_id


def fetch_cheapest_trip(
    from_city_id: str,
    to_city_id: str,
    departure_date: str,
    currency: str = "EUR",
    locale: str = "pl",
) -> dict:
    """GET /search/service/v4/search — najtańszy przejazd (spośród wszystkich godzin/przesiadek
    tego dnia) dla podanej pary miast i daty. Zwraca surowy wpis "trip" z odpowiedzi API."""
    params = {
        "from_city_id": from_city_id,
        "to_city_id": to_city_id,
        "departure_date": _to_flixbus_date(departure_date),
        "products": json.dumps({"adult": 1}),
        "currency": currency,
        "locale": locale,
        "search_timezone": "Europe/Warsaw",
        "search_by": "cities",
    }

    try:
        response = requests.get(f"{API_BASE}/search/service/v4/search", params=params, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FlixbusApiError(
            f"Błąd zapytania search FlixBus {from_city_id}->{to_city_id} na {departure_date}: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise FlixbusApiError(f"Odpowiedź search FlixBus nie jest poprawnym JSON-em: {exc}") from exc

    trips = payload.get("trips") or []
    if not trips:
        raise FlixbusApiError(
            f"FlixBus nie zwrócił żadnych przejazdów dla {from_city_id}->{to_city_id} na "
            f"{departure_date} (brak bezpośredniego/pośredniego połączenia albo data poza zakresem "
            "sprzedaży)."
        )

    results = trips[0].get("results") or {}
    if not results:
        raise FlixbusApiError(
            f"FlixBus zwrócił pustą listę wyników dla {from_city_id}->{to_city_id} na {departure_date}."
        )

    try:
        cheapest = min(results.values(), key=lambda trip: trip["price"]["total"])
    except (KeyError, TypeError) as exc:
        raise FlixbusApiError(
            "Nieoczekiwany kształt odpowiedzi FlixBus API (endpoint mógł się zmienić od czasu "
            f"napisania tego klienta): {exc}. Fragment surowej odpowiedzi: {str(results)[:500]}"
        ) from exc

    return cheapest
