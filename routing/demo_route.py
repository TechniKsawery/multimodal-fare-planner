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
DUSSELDORF_HBF_STOP = "defv_126321"
KRAKOW_LOTNISKO_STOP = "pl_235879"


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

# UWAGA: HubConfig "Lublin(LUZ)-Dortmund" (lot LUZ->DTM) był tu wcześniej skonfigurowany, ale
# zgłoszony 2026-09-29 jako fałszywy wariant: lotnisko w Lublinie (LUZ, Świdnik) nie ma i nigdy
# nie miało żadnego bezpośredniego ani pośredniego połączenia lotniczego do Niemiec — user
# zweryfikował na Skyscanner, że jedyne realne opcje LUZ->DTM to 998+ PLN z 1-2 przesiadkami
# w 13-21h, a nasz silnik i tak nie umie modelować lotów z przesiadkami (build_flight_leg buduje
# zawsze JEDEN odcinek ze sztywnym czasem 2h, patrz variants.py) — pokazywanie takiego wariantu
# jako "lot (Lublin-Dortmund)" sugerowało nieistniejące bezpośrednie połączenie. Usunięty, żeby
# nie fabrykować danych zamiast po prostu nie mieć wariantu — patrz tests/test_demo_route.py.

# Wariant "kolej + lot + kolej lokalna": ... -> Warszawa Lotnisko Chopina (kolej) -> WAW -> DUS
# (lot) -> Düsseldorf Hbf (kolej lokalna/dalsza). Lot WAW-DUS zweryfikowany 2026-10-03: LOT (13
# rejsów/tydz.) i Eurowings (4 rejsy/tydz.) latają bezpośrednio — patrz PR, w którym ten hub
# dodano.
HUB_WARSZAWA_DUSSELDORF = HubConfig(
    label="Warszawa-Düsseldorf",
    origin_iata="WAW",
    destination_iata="DUS",
    origin_rail_access_stop_id=WARSZAWA_LOTNISKO_CHOPINA_STOP,
    destination_rail_access_stop_id=DUSSELDORF_HBF_STOP,
)

# UWAGA: hub "Warszawa-Köln/Bonn" (lot WAW-CGN) był sprawdzany 2026-10-03, ale NIE dodany:
# zweryfikowano (wyszukiwanie lotów), że na trasie Warszawa<->Köln/Bonn nie ma obecnie żadnego
# bezpośredniego połączenia lotniczego żadnego przewoźnika (0 nonstop) — tylko loty z
# przesiadkami, których nasz silnik i tak nie umie modelować (patrz UWAGA o LUZ-DTM wyżej).
# Dodanie takiego huba sugerowałoby nieistniejące bezpośrednie połączenie, więc pomijamy go
# zamiast fabrykować dane — patrz tests/test_demo_route.py.

# Wariant "kolej + lot + kolej lokalna": Kraków -> Kraków Lotnisko (kolej, linia SKA) -> KRK ->
# DTM (lot) -> Dortmund Hbf (kolej lokalna/dalsza). Lot KRK-DTM zweryfikowany 2026-10-03: Ryanair
# i Wizz Air latają bezpośrednio, ok. 7 rejsów/tydz. — patrz PR, w którym ten hub dodano.
HUB_KRAKOW_DORTMUND = HubConfig(
    label="Kraków-Dortmund",
    origin_iata="KRK",
    destination_iata="DTM",
    origin_rail_access_stop_id=KRAKOW_LOTNISKO_STOP,
    destination_rail_access_stop_id=DORTMUND_HBF_STOP,
)

RAIL_FLIGHT_RAIL_HUBS = [HUB_WARSZAWA_DORTMUND, HUB_WARSZAWA_DUSSELDORF, HUB_KRAKOW_DORTMUND]
FLIGHT_REGIONAL_HUBS = []

POZNAN_GLOWNY_STOP = "pl_30601"
ESSEN_HBF_STOP = "defv_351643"

# Sesja 6: jawnie sprawdzane węzły pośrednie / alternatywne dworce mety (tylko kolej).
VIA_HUB_STOPS = [AlternativeStop(label="Poznań Główny", stop_id=POZNAN_GLOWNY_STOP)]

# UWAGA: to podmienia destination_stop_id/destination_label na SZTYWNY dworzec (Essen Hbf),
# więc nadaje się tylko do zapytań, w których destination_stop_id już JEST dworcem
# (np. lublin_gelsenkirchen_request poniżej, destination_stop_id=Gelsenkirchen Hbf — porównanie
# dworzec vs dworzec). Dla zapytań adres->adres (request_from_addresses) destination_stop_id to
# konkretny adres/współrzędne, więc ta podmiana ODCINA rzeczywisty adres docelowy razem z
# ostatnim odcinkiem pieszym/autobusowym/tramwajowym do niego — dlatego demo.py/app.py (wyszukiwanie
# adres->adres) NIE przekazują tej listy do generate_variants, tylko testy na sztywnym
# lublin_gelsenkirchen_request.
ALTERNATIVE_DESTINATION_STOPS = [AlternativeStop(label="Essen Hbf", stop_id=ESSEN_HBF_STOP)]
