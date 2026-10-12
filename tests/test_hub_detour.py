from routing.demo_route import (
    HUB_KRAKOW_DORTMUND,
    HUB_WARSZAWA_DORTMUND,
    HUB_WARSZAWA_DUSSELDORF,
)
from routing.variants import hub_is_detour

LUBLIN = (51.2314, 22.5692)
BERLIN = (52.5251, 13.3694)
GELSENKIRCHEN = (51.5049, 7.1022)
ESSEN = (51.4515, 7.0131)


def test_lublin_berlin_nie_dostaje_lotu_na_dusseldorf():
    assert hub_is_detour(LUBLIN, BERLIN, HUB_WARSZAWA_DUSSELDORF)
    assert hub_is_detour(LUBLIN, BERLIN, HUB_WARSZAWA_DORTMUND)


def test_lublin_gelsenkirchen_zachowuje_huby():
    for hub in (HUB_WARSZAWA_DORTMUND, HUB_WARSZAWA_DUSSELDORF):
        assert not hub_is_detour(LUBLIN, GELSENKIRCHEN, hub)


def test_krakow_dortmund_hub_dla_lublina_nie_jest_zawsze_odrzucany():
    # Kraków leży na południe od Lublina, ale nadal w kierunku zachodnim: ratio < 1.5
    assert not hub_is_detour(LUBLIN, ESSEN, HUB_KRAKOW_DORTMUND)


def test_brak_wspolrzednych_nie_filtruje():
    assert not hub_is_detour(None, BERLIN, HUB_WARSZAWA_DUSSELDORF)
