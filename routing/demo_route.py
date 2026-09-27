"""Konfiguracja przykładowej relacji Lublin -> Gelsenkirchen (demo.py, tests/test_routing.py).

Identyfikatory stopId pochodzą z MOTIS (Sesja 2, GTFS PL+DE) — zweryfikowane manualnie
zapytaniami do /api/v1/geocode i /api/v6/plan pod uruchomionym lokalnie MOTIS. Huby (lotniska
+ stacje dojazdowe) są ustalone RAZ, bez przeszukiwania alternatyw — patrz README.md.
"""
from .variants import AlternativeStop, HubConfig, RouteRequest

LUBLIN_GLOWNY_STOP = "pl_50500"
GELSENKIRCHEN_HBF_STOP = "defv_344028"

WARSZAWA_LOTNISKO_CHOPINA_STOP = "pl_241994"
DORTMUND_HBF_STOP = "defv_64583"


def lublin_gelsenkirchen_request(date: str, **overrides) -> RouteRequest:
    """RouteRequest dla Lublin Główny -> Gelsenkirchen Hbf w podanym dniu (YYYY-MM-DD)."""
    kwargs = dict(
        origin_stop_id=LUBLIN_GLOWNY_STOP,
        destination_stop_id=GELSENKIRCHEN_HBF_STOP,
        origin_label="Lublin",
        destination_label="Gelsenkirchen",
        date=date,
    )
    kwargs.update(overrides)
    return RouteRequest(**kwargs)


# Wariant "kolej + lot + kolej lokalna": Lublin -> Warszawa Lotnisko Chopina (kolej) ->
# WAW -> DTM (lot) -> Dortmund Hbf -> Gelsenkirchen Hbf (kolej lokalna).
HUB_WARSZAWA_DORTMUND = HubConfig(
    label="Warszawa-Dortmund",
    origin_iata="WAW",
    destination_iata="DTM",
    origin_rail_access_stop_id=WARSZAWA_LOTNISKO_CHOPINA_STOP,
    destination_rail_access_stop_id=DORTMUND_HBF_STOP,
)

# Wariant "lot + transport regionalny": lot z lotniska w Lublinie (LUZ, Świdnik) bez długiego
# dojazdu kolejowego -> DTM -> Dortmund Hbf -> Gelsenkirchen Hbf (kolej lokalna).
HUB_LUBLIN_AIRPORT_DORTMUND = HubConfig(
    label="Lublin(LUZ)-Dortmund",
    origin_iata="LUZ",
    destination_iata="DTM",
    origin_rail_access_stop_id=None,
    destination_rail_access_stop_id=DORTMUND_HBF_STOP,
)

RAIL_FLIGHT_RAIL_HUBS = [HUB_WARSZAWA_DORTMUND]
FLIGHT_REGIONAL_HUBS = [HUB_LUBLIN_AIRPORT_DORTMUND]

POZNAN_GLOWNY_STOP = "pl_30601"
ESSEN_HBF_STOP = "defv_351643"

# Sesja 6: jawnie sprawdzane węzły pośrednie / alternatywne dworce mety (tylko kolej).
VIA_HUB_STOPS = [AlternativeStop(label="Poznań Główny", stop_id=POZNAN_GLOWNY_STOP)]
ALTERNATIVE_DESTINATION_STOPS = [AlternativeStop(label="Essen Hbf", stop_id=ESSEN_HBF_STOP)]
