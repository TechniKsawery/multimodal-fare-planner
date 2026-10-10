"""Modele requestów i response'ów REST API (api/main.py)."""

from pydantic import BaseModel, Field


class DiscountProfileIn(BaseModel):
    """Profil ulg pasażera — patrz fares/model.py::DiscountProfile (to samo pole po polu)."""

    pkp_ulga_kod: str = "brak"
    bahncard: str | None = None
    ztm_lublin_ulgowy: bool = False
    ztm_warszawa_ulgowy: bool = False
    mpk_krakow_ulgowy: bool = False
    ztm_poznan_ulgowy: bool = False
    mpk_wroclaw_ulgowy: bool = False
    bvg_berlin_ulgowy: bool = False
    vrr_dziecko: bool = False
    hvv_dziecko: bool = False
    mvv_dziecko: bool = False
    vrs_koln_dziecko: bool = False
    schwerbehinderte_wertmarke_de: bool = False
    age: int | None = None


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


class CityCardEvaluateRequest(BaseModel):
    """Żądanie oceny opłacalności kart miejskich dla wskazanych atrakcji i miasta."""

    city: str = Field(..., description="Nazwa lub adres miasta, np. 'Berlin' lub 'Gelsenkirchen'")
    attraction_ids: list[str] = Field(
        default_factory=list, description="Lista identyfikatorów wybranych atrakcji"
    )
    estimated_transit_cost: float = Field(
        0.0, description="Szacowany koszt lokalnego transportu miejskiego w walucie docelowej"
    )
