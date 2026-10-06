"""Modele requestów REST API (api/main.py) — odzwierciedlają fares.model.DiscountProfile i
parametry używane przez routing.variants.request_from_addresses()."""

from pydantic import BaseModel, Field


class DiscountProfileIn(BaseModel):
    """Profil ulg pasażera — patrz fares/model.py::DiscountProfile (to samo pole po polu)."""

    pkp_ulga_kod: str = "brak"
    bahncard: str | None = None
    ztm_lublin_ulgowy: bool = False
    vrr_dziecko: bool = False


class RouteSearchRequest(BaseModel):
    """Zapytanie o trasę adres -> adres (geocoding OSM przez MOTIS, jak w app.py/demo.py)."""

    origin: str = Field(
        ..., description="Adres/miejsce startowe, np. 'Krakowskie Przedmieście 50, Lublin'"
    )
    destination: str = Field(..., description="Adres/miejsce docelowe")
    date: str = Field(..., description="Dzień wyjazdu, YYYY-MM-DD")
    departure_time: str = Field(
        "06:00:00", description="Najwcześniejsza godzina wyjazdu brana pod uwagę"
    )
    discounts: DiscountProfileIn = Field(default_factory=DiscountProfileIn)
    flight_currency: str = "PLN"
