"""REST API (FastAPI) nad silnikiem routingu i taryf (routing/, fares/) — ta sama logika,
którą woła Streamlit (app.py, przez routing/search_service.py), wydzielona jako samodzielny
serwis, żeby dało się podłączyć inny frontend (appka mobilna, inny klient webowy) bez
przepisywania silnika.

Uruchomienie:
    pip install fastapi "uvicorn[standard]"
    uvicorn api.main:app --reload

Wymaga działającego MOTIS (patrz README.md) — bez niego /route zwróci 502.
"""

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder

from fares.model import DiscountProfile
from routing.motis_client import MotisError
from routing.search_service import search
from routing.variants import request_from_addresses

from .schemas import RouteSearchRequest

app = FastAPI(
    title="Multimodalna wyszukiwarka API",
    description=(
        "Routing + szacowanie cen (kolej PL/DE, loty, transport miejski) dla trasy "
        "adres -> adres, z uwzględnieniem zniżek pasażera (BahnCard, ulgi PKP, ZTM, VRR)."
    ),
    version="0.1.0",
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
