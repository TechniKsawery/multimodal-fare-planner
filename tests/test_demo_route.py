"""Regresja: HubConfig lot<->kolej muszą odpowiadać realnie istniejącym połączeniom lotniczym.

Zgłoszony 2026-09-29: silnik pokazywał wariant "Lot (Lublin(LUZ)-Dortmund)" jako bezpośredni
lot LUZ->DTM (120 min, szacunek 480 PLN), mimo że takie połączenie w ogóle nie istnieje —
Lublin (LUZ, Świdnik) nie ma żadnych lotów do Niemiec. Realne najtańsze opcje (Skyscanner)
to 998+ PLN z 1-2 przesiadkami, 13-21h — czego nasz silnik nie umie zbudować (build_flight_leg
modeluje lot zawsze jako JEDEN odcinek ze sztywnym czasem 2h). Fałszywy wariant brał się z
HUB_LUBLIN_AIRPORT_DORTMUND w routing/demo_route.py, połączonego z GENERIC_FLIGHT_FALLBACK_PLN
w flights/calculator.py (fallback ceny, gdy Travelpayouts nie ma danych dla tej relacji) —
fallback szacuje tylko CENĘ, nie sprawdzając czy dany hub w ogóle ma bezpośrednie połączenie."""
from routing import demo_route


def test_flight_regional_hubs_nie_zawiera_lublina():
    """LUZ (Lublin) nie ma żadnych lotów do Niemiec — nie może być origin_iata żadnego huba."""
    for hub in demo_route.FLIGHT_REGIONAL_HUBS:
        assert hub.origin_iata != "LUZ", (
            f"Hub {hub.label!r} zakłada lot z LUZ (Lublin), który w rzeczywistości nie istnieje"
        )


def test_flight_regional_hubs_pusta_po_usunieciu_nierealistycznego_hubu():
    """Jedyny hub, jaki tu kiedykolwiek był (Lublin(LUZ)-Dortmund), został usunięty jako
    nierealistyczny — lista ma być pusta, dopóki nie dojdzie realny, zweryfikowany hub."""
    assert demo_route.FLIGHT_REGIONAL_HUBS == []
