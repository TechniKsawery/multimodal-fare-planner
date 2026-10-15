"""Modele requestów i response'ów REST API (api/main.py)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from common.currency import SUPPORTED_CURRENCIES, UnsupportedCurrencyError, normalize_currency
from fares._data_loading import load

_PKP_TABLE = load("pkp_intercity.json")
VALID_PKP_ULGI = set(_PKP_TABLE["ulgi_procent"].keys())
VALID_BAHNCARD = {None, "brak", "25", "50", "100"}
VALID_OBYWATELSTWO = {None, "PL", "UE", "poza_UE"}


class DiscountProfileIn(BaseModel):
    """Profil ulg pasażera — patrz fares/model.py::DiscountProfile (to samo pole po polu)."""

    model_config = ConfigDict(extra="forbid")

    pkp_ulga_kod: str = "brak"
    bahncard: str | None = None
    ztm_lublin_ulgowy: bool = False
    ztm_lublin_bezplatny: bool = False
    ztm_warszawa_ulgowy: bool = False
    ztm_warszawa_bezplatny: bool = False
    mpk_krakow_ulgowy: bool = False
    mpk_krakow_bezplatny: bool = False
    ztm_poznan_ulgowy: bool = False
    ztm_poznan_bezplatny: bool = False
    mpk_wroclaw_ulgowy: bool = False
    mpk_wroclaw_bezplatny: bool = False
    bvg_berlin_ulgowy: bool = False
    bvg_berlin_schwerbehindert: bool = False
    vrr_dziecko: bool = False
    hvv_dziecko: bool = False
    mvv_dziecko: bool = False
    vrs_koln_dziecko: bool = False
    schwerbehinderte_wertmarke_de: bool = False
    age: int | None = None
    child_with_guardian: bool = False
    obywatelstwo: str | None = None
    legitymacja_zagraniczna: bool = False

    @field_validator("pkp_ulga_kod")
    @classmethod
    def _validate_pkp_ulga_kod(cls, v: str) -> str:
        if v not in VALID_PKP_ULGI:
            raise ValueError(f"Nieznany kod ulgi PKP: {v!r}. Dopuszczalne: {sorted(VALID_PKP_ULGI)}")
        return v

    @field_validator("bahncard")
    @classmethod
    def _validate_bahncard(cls, v: str | None) -> str | None:
        if v not in VALID_BAHNCARD:
            raise ValueError(f"Nieznany kod BahnCard: {v!r}. Dopuszczalne: {sorted(k for k in VALID_BAHNCARD if k is not None)}")
        return v

    @field_validator("obywatelstwo")
    @classmethod
    def _validate_obywatelstwo(cls, v: str | None) -> str | None:
        if v not in VALID_OBYWATELSTWO:
            raise ValueError(f"Nieznane obywatelstwo: {v!r}. Dopuszczalne: {sorted(k for k in VALID_OBYWATELSTWO if k is not None)}")
        return v


class RouteSearchRequest(BaseModel):
    """Zapytanie o trasę adres -> adres (geocoding OSM przez MOTIS, jak w app.py/demo.py)."""

    model_config = ConfigDict(extra="forbid")

    origin: str = Field(

        ..., description="Adres/miejsce startowe, np. 'Krakowskie Przedmieście 50, Lublin'"
    )
    destination: str = Field(..., description="Adres/miejsce docelowe")
    date: str = Field(..., description="Dzień wyjazdu, YYYY-MM-DD")
    departure_time: str = Field(
        "06:00:00", description="Najwcześniejsza godzina wyjazdu brana pod uwagę"
    )
    discounts: DiscountProfileIn = Field(default_factory=DiscountProfileIn)
    flight_currency: str = Field(
        "PLN",
        description=(
            "Waluta wyceny lotów. Obsługiwane (mamy dla nich kurs): "
            + ", ".join(SUPPORTED_CURRENCIES)
        ),
    )
    checked_baggage: bool = Field(
        True, description="True = bagaż rejestrowany (w cenie lotu, bufor po lądowaniu 90 min); False = tylko podręczny (60 min). Bufory to szacunek."
    )

    @field_validator("flight_currency")
    @classmethod
    def _flight_currency_supported(cls, value: str) -> str:
        """Nieobsługiwana waluta to błąd zapytania (422 z komunikatem), nie 500 z głębi wyceny."""
        try:
            return normalize_currency(value)
        except UnsupportedCurrencyError as exc:
            raise ValueError(str(exc)) from exc


class CityCardEvaluateRequest(BaseModel):
    """Żądanie oceny opłacalności kart miejskich dla wskazanych atrakcji i miasta."""

    model_config = ConfigDict(extra="forbid")

    city: str = Field(..., description="Nazwa lub adres miasta, np. 'Berlin' lub 'Gelsenkirchen'")
    attraction_ids: list[str] = Field(
        default_factory=list, description="Lista identyfikatorów wybranych atrakcji"
    )
    estimated_transit_cost: float = Field(
        0.0, description="Szacowany koszt lokalnego transportu miejskiego w walucie docelowej"
    )
