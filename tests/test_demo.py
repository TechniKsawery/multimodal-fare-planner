"""Regresja: wyszukiwanie adres->adres (demo.py/app.py) nie może podmieniać rzeczywistego
adresu docelowego na sztywny dworzec (routing/demo_route.ALTERNATIVE_DESTINATION_STOPS).

Zgłoszony przypadek: Lublin (Skubiszewskiego 22) -> Buerer Strasse 8, Gelsenkirchen pokazywał
trasę urywającą się na Essen Hbf, bez ostatniego odcinka (autobus/U-Bahn) do faktycznego adresu.
Przyczyna: demo.py/app.py przekazywały do generate_variants() sztywną listę
ALTERNATIVE_DESTINATION_STOPS = [Essen Hbf] (z routing/demo_route.py, zbudowaną dla zapytania
stacja->stacja Lublin Główny -> Gelsenkirchen Hbf), która dla zapytań adres->adres podmienia
destination_stop_id/destination_label na Essen Hbf, odcinając prawdziwy adres."""

from unittest.mock import patch

import demo
from routing import variants


def test_demo_main_nie_przekazuje_alternative_destination_stops(monkeypatch, capsys):
    """demo.main() (wyszukiwanie adres->adres) nie może wołać generate_variants z
    alternative_destination_stops — to podmieniłoby prawdziwy adres docelowy na dworzec."""
    fake_request = variants.RouteRequest(
        origin_stop_id="51.0,22.0",
        destination_stop_id="51.5,7.1",
        origin_label="Skubiszewskiego 22, Lublin",
        destination_label="Buerer Strasse 8, Gelsenkirchen",
        date="2026-10-05",
    )
    monkeypatch.setattr(demo, "request_from_addresses", lambda *a, **kw: fake_request)

    captured_kwargs = {}

    def fake_generate_variants(request, **kwargs):
        captured_kwargs.update(kwargs)
        return [], []

    monkeypatch.setattr(demo, "generate_variants", fake_generate_variants)
    monkeypatch.setattr(
        "sys.argv",
        [
            "demo.py",
            "--from",
            "Skubiszewskiego 22, Lublin",
            "--to",
            "Buerer Strasse 8, Gelsenkirchen",
            "--date",
            "2026-10-05",
        ],
    )

    demo.main()

    assert not captured_kwargs.get("alternative_destination_stops")
    out = capsys.readouterr().out
    assert "Brak żadnego działającego wariantu" in out


def test_alternative_destination_stop_nie_moze_ucinac_adresu_docelowego():
    """Dokumentuje samo zachowanie generate_variants(): AlternativeStop w
    alternative_destination_stops PODMIENIA destination_stop_id/destination_label — dlatego
    wolno go używać tylko dla zapytań stacja->stacja (patrz routing/demo_route.py), nigdy dla
    zapytań zbudowanych przez request_from_addresses()."""
    request = variants.RouteRequest(
        origin_stop_id="a",
        destination_stop_id="prawdziwy_adres_docelowy",
        origin_label="A",
        destination_label="Buerer Strasse 8, Gelsenkirchen",
        date="2026-11-15",
    )
    alt = variants.AlternativeStop("Essen Hbf", "essen_hbf_stop")
    with patch.object(variants, "build_rail_only_variants") as fake_build:
        fake_build.return_value = []
        variants.generate_variants(request, alternative_destination_stops=[alt])

        # druga wywołana wersja żądania (dla alternatywnego dworca mety) ma podmienioną metę —
        # to jest właśnie mechanizm, który demo.py/app.py muszą omijać dla adresów
        alt_request_call = fake_build.call_args_list[-1]
        alt_request = alt_request_call.args[0]
        assert alt_request.destination_stop_id == "essen_hbf_stop"
        assert alt_request.destination_stop_id != request.destination_stop_id


def test_resolve_pkp_ulga_student_dorosly():
    from demo import resolve_pkp_ulga

    kod, uwaga = resolve_pkp_ulga(None, 20, True)
    assert kod == "student_do_26_lat_doktorant_do_35_lat" and uwaga is None


def test_resolve_pkp_ulga_jawny_kod_wygrywa_i_bez_studenta_z_wieku():
    from demo import resolve_pkp_ulga

    assert resolve_pkp_ulga("opiekun_lub_przewodnik_osoby_niepelnosprawnej", 20, True)[0] == (
        "opiekun_lub_przewodnik_osoby_niepelnosprawnej"
    )
    assert resolve_pkp_ulga(None, 20, False) == ("brak", None)
    assert resolve_pkp_ulga(None, 10, False)[0] == "dzieci_mlodziez_szkolna_do_24_lat"


def test_resolve_pkp_ulga_student_nie_zgaduje_poza_26_i_dla_dzieci():
    from demo import resolve_pkp_ulga

    kod, uwaga = resolve_pkp_ulga(None, 30, True)
    assert kod == "brak" and uwaga
    kod, uwaga = resolve_pkp_ulga(None, 15, True)
    assert kod == "dzieci_mlodziez_szkolna_do_24_lat" and uwaga


def test_build_discount_profile_ustawia_ulge_pkp_i_cena_spada():
    from demo import build_discount_profile
    from fares import pkp
    from fares.model import Carrier, Segment

    profil = build_discount_profile(20, False, "student_do_26_lat_doktorant_do_35_lat")
    pelna = pkp.estimate(Segment(origin="A", destination="B", carrier=Carrier.PKP_INTERCITY, distance_km=170, discounts=build_discount_profile(20, False, "brak")))
    ulga = pkp.estimate(Segment(origin="A", destination="B", carrier=Carrier.PKP_INTERCITY, distance_km=170, discounts=profil))
    assert ulga.breakdown["ulga_procent"] == 51
    assert ulga.amount == round(pelna.amount * 0.49, 2)
