from unittest.mock import patch

from routing import airports
from routing.variants import HubConfig, RouteRequest, generate_variants

LUBLIN = (51.2314, 22.5692)
BERLIN = (52.5251, 13.3694)
GELSEN = (51.5049, 7.1022)


def _iata(pairs):
    return {(a.iata, b.iata) for a, b in pairs}


def test_pary_dla_gelsenkirchen_maja_lotniska_zachodnie_i_nie_berlin():
    pairs = _iata(airports.candidate_airport_pairs(LUBLIN, GELSEN))
    assert pairs and all(b not in ("BER", "LEJ", "DRS") for _, b in pairs)
    assert any(b in ("DTM", "DUS", "CGN", "FMO", "NRN") for _, b in pairs)


def test_lublin_berlin_nie_ma_par_z_zachodu():
    pairs = _iata(airports.candidate_airport_pairs(LUBLIN, BERLIN))
    assert all(b not in ("DUS", "DTM", "CGN") for _, b in pairs)


def test_discover_hubs_tylko_z_lotem_bezposrednim_i_pomija_statyczne():
    status = lambda a, b, d: ((True, "") if (a, b) == ("WAW", "DUS") else (False, "brak"))
    with patch.object(airports, "direct_flight_status", status):
        hubs, rejected = airports.discover_hubs(LUBLIN, GELSEN, "2026-10-20")
        assert [h.label for h in hubs] == ["WAW-DUS"]
        assert len(rejected) == 1 and "brak." in rejected[0][1] and "WMI→DUS" in rejected[0][1]
        assert airports.discover_hubs(LUBLIN, GELSEN, "2026-10-20", skip={("WAW", "DUS")})[0] == []


def test_blad_api_lotow_trafia_do_skipped():
    req = RouteRequest("51.2314,22.5692", "51.5049,7.1022", "A", "B", "2026-10-20")

    def boom(*a):
        raise RuntimeError("brak tokena")

    with patch("routing.variants.build_rail_only_variants", return_value=[]):
        built, skipped = generate_variants(req, hub_discovery=boom)
    assert any("dobór lotnisk" in s.variant_name for s in skipped)


def test_odrzucone_pary_trafiaja_do_skipped_z_powodem():
    req = RouteRequest("51.2314,22.5692", "52.5251,13.3694", "A", "B", "2026-10-20")
    disc = lambda o, d, skip: ([], [("Loty bez potwierdzenia (1 par)", "brak bezpośredniego. Pary: WAW→BER")])
    with patch("routing.variants.build_rail_only_variants", return_value=[]):
        _, skipped = generate_variants(req, hub_discovery=disc)
    assert any("Loty bez potwierdzenia" in s.variant_name and "WAW→BER" in s.reason for s in skipped)


CITIES = {
    "Kraków": (50.0647, 19.9450),
    "Hamburg": (53.5527, 10.0060),
    "Wrocław": (51.0986, 17.0366),
    "Köln": (50.9430, 6.9589),
    "Poznań": (52.4019, 16.9125),
    "München": (48.1403, 11.5600),
}


def test_dowolne_pary_miast_dostaja_lotniska_z_promienia_bez_sztywnej_listy():
    cases = [
        ("Kraków", "Hamburg", "KRK", "HAM"),
        ("Wrocław", "Köln", "WRO", "CGN"),
        ("Poznań", "München", "POZ", "MUC"),
    ]
    for o, d, a, b in cases:
        pairs = _iata(airports.candidate_airport_pairs(CITIES[o], CITIES[d]))
        assert (a, b) in pairs, (o, d, sorted(pairs))


def test_search_nie_uzywa_listy_par_tylko_dyskoweri():
    import routing.search_service as ss

    assert not hasattr(ss, "RAIL_FLIGHT_RAIL_HUBS")


def test_direct_status_uzywa_biletow_direct_i_nie_miesza_indeksow_z_przesiadkami():
    from flights import travelpayouts as tp

    calls = []

    def fake(o, d, when, currency="PLN"):
        calls.append(when)
        return [{"transfers": 0}] if when == "2026-10" else []

    with patch.object(tp, "fetch_direct_tickets", fake):
        assert airports.direct_flight_status("WAW", "BER", "2026-10-20") == (True, "")
    assert calls == ["2026-10-20", "2026-10"]
    with patch.object(tp, "fetch_direct_tickets", lambda *a, **k: []):
        ok, reason = airports.direct_flight_status("WAW", "BER", "2026-10-20")
    assert not ok and "nie dowodzi" in reason


def test_lotnisko_bez_dojazdu_ma_jasny_powod_w_skipped():
    from routing.motis_client import MotisError

    req = RouteRequest("51.2314,22.5692", "52.5251,13.3694", "A", "B", "2026-10-20")
    hub = HubConfig("WAW-BER", "WAW", "BER", "52.1657,20.9671", "52.3667,13.5033")
    disc = lambda o, d, skip: ([hub], [])

    def boom(request, h):
        raise MotisError("MOTIS nie znalazł żadnego połączenia")

    with patch("routing.variants.build_rail_only_variants", return_value=[]), patch(
        "routing.variants.build_rail_flight_rail_variant", boom
    ):
        _, skipped = generate_variants(req, hub_discovery=disc)
    assert any("Brak dojazdu komunikacją do lotniska" in s.reason for s in skipped)


def test_tabela_nie_ma_lotnisk_bez_sensownego_dojazdu():
    codes = {a["iata"] for a in airports._AIRPORTS}
    assert "IEG" not in codes and "SZY" not in codes
