"""REST API (FastAPI) nad silnikiem routingu, taryf i atrakcji (routing/, fares/, attractions/) —
ta sama logika, którą woła Streamlit (app.py), wydzielona jako samodzielny serwis,
żeby dało się podłączyć inny frontend (appka mobilna, landing page, inny klient webowy).

Uruchomienie:
    pip install fastapi "uvicorn[standard]"
    uvicorn api.main:app --reload

Wymaga działającego MOTIS (patrz README.md) — bez niego /route zwróci 502.
Endpointy /attractions i /city-cards działają niezależnie od MOTIS.
"""

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder

from attractions import (
    AttractionCategory,
    evaluate_city_cards,
    get_attractions,
    get_city_cards,
    normalize_city,
)
from fares.model import DiscountProfile
from routing.motis_client import MotisError
from routing.search_service import search
from routing.variants import request_from_addresses

from .schemas import CityCardEvaluateRequest, RouteSearchRequest

app = FastAPI(
    title="Multimodalna wyszukiwarka API",
    description=(
        "Routing + szacowanie cen (kolej PL/DE, loty, transport miejski) dla trasy "
        "adres -> adres, z uwzględnieniem zniżek pasażera (BahnCard, ulgi PKP, ZTM, VRR) "
        "oraz moduł atrakcji i kart miejskich (City Cards)."
    ),
    version="0.2.0",
)


@app.get("/health")
def health() -> dict:
    """Health-check — nie dotyka MOTIS, tylko potwierdza, że proces API żyje."""
    return {"status": "ok"}


@app.post("/route")
def find_route(payload: RouteSearchRequest) -> dict:
    """Wyszukuje warianty trasy adres -> adres + rekomendacje (patrz routing/scoring.py).

    Zwraca 502, jeśli MOTIS jest nieosiągalny albo nie udało się zgeokodować adresu —
    to nie jest błąd zapytania klienta (4xx), tylko zależności, którą API samo nie kontroluje.
    """
    discounts = DiscountProfile(**payload.discounts.model_dump())
    try:
        route_request = request_from_addresses(
            payload.origin,
            payload.destination,
            payload.date,
            departure_time=payload.departure_time,
            discounts=discounts,
            flight_currency=payload.flight_currency,
            checked_baggage=payload.checked_baggage,
        )
        result = search(route_request)
    except MotisError as exc:
        raise HTTPException(status_code=502, detail=f"Błąd MOTIS/geokodowania: {exc}") from exc

    return jsonable_encoder(
        {
            "origin_label": result.request.origin_label,
            "destination_label": result.request.destination_label,
            "date": payload.date,
            "built": result.built,
            "skipped": result.skipped,
            "recommendations": result.recommendations,
        }
    )


def _require_known_city(city: str | None) -> None:
    """Podane, ale nierozpoznane miasto = 400 (zamiast cichego zwrócenia WSZYSTKICH rekordów)."""
    if city and not normalize_city(city):
        raise HTTPException(
            status_code=400,
            detail=f"Nie rozpoznano obsługiwanego miasta dla zapytania: {city!r}",
        )


@app.get("/attractions")
def list_attractions(city: str | None = None, category: str | None = None) -> list[dict]:
    """Zwraca katalog atrakcji i rekomendowanych miejsc, z opcjonalnym filtrowaniem po mieście i kategorii."""
    _require_known_city(city)
    if category is not None and category not in {c.value for c in AttractionCategory}:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nieznana kategoria: {category!r}. Dozwolone: "
                + ", ".join(c.value for c in AttractionCategory)
            ),
        )
    items = get_attractions(city=city, category=category)
    return jsonable_encoder(items)


@app.get("/city-cards")
def list_city_cards(city: str | None = None) -> list[dict]:
    """Zwraca karty miejskie (City Cards) dla wskazanego miasta."""
    _require_known_city(city)
    cards = get_city_cards(city=city)
    return jsonable_encoder(cards)


@app.post("/city-cards/evaluate")
def evaluate_cards(payload: CityCardEvaluateRequest) -> list[dict]:
    """Kalkuluje opłacalność wariantów kart miejskich dla wskazanych atrakcji i transportu."""
    norm_city = normalize_city(payload.city)
    if not norm_city:
        raise HTTPException(
            status_code=400,
            detail=f"Nie rozpoznano obsługiwanego miasta dla zapytania: {payload.city!r}",
        )
    all_city_attractions = get_attractions(city=norm_city)
    attr_map = {a.id: a for a in all_city_attractions}
    selected = [attr_map[aid] for aid in payload.attraction_ids if aid in attr_map]
    evaluations = evaluate_city_cards(
        city=norm_city,
        attractions=selected,
        estimated_transit_cost=payload.estimated_transit_cost,
    )
    return jsonable_encoder(evaluations)
