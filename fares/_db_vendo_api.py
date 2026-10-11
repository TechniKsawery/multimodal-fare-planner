"""Klient lokalnego serwisu tools/db-vendo-service (nieoficjalne API DB przez db-vendo-client).

Adres: DB_VENDO_URL (domyślnie http://127.0.0.1:3100). Cache i limit zapytań: fares/_unofficial.py.
Zgodnie z README biblioteki formalnie potrzebna jest zgoda DB — dlatego źródło jest opcjonalne.
"""

import os

import requests

from . import _unofficial


class DbVendoError(RuntimeError):
    """Serwis niedostępny, limit przekroczony albo brak ceny."""


def fetch_cheapest(origin: str, destination: str, date: str, bahncard: str | None = None) -> dict:
    key = f"{origin}|{destination}|{date}|{bahncard or '-'}"
    cached = _unofficial.cache_get("db", key)
    if cached:
        return {**cached, "z_cache": True}
    if not _unofficial.allow_request("db"):
        raise DbVendoError("przekroczono limit zapytań UNOFFICIAL_PRICES_PER_MINUTE")

    base = os.environ.get("DB_VENDO_URL", "http://127.0.0.1:3100")
    params = {"from": origin, "to": destination, "date": date}
    if bahncard in ("25", "50"):
        params["bahncard"] = bahncard
    try:
        response = requests.get(f"{base}/price", params=params, timeout=30)
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DbVendoError(f"db-vendo-service niedostępny: {exc}") from exc
    if response.status_code != 200 or "amount" not in payload:
        raise DbVendoError(f"brak ceny z DB ({response.status_code}): {payload.get('error', payload)}")

    _unofficial.cache_set("db", key, payload)
    return {**payload, "z_cache": False}
