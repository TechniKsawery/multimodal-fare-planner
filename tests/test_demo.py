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
        origin_stop_id="51.0,22.0", destination_stop_id="51.5,7.1",
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
        ["demo.py", "--from", "Skubiszewskiego 22, Lublin", "--to", "Buerer Strasse 8, Gelsenkirchen",
         "--date", "2026-10-05"],
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
        origin_stop_id="a", destination_stop_id="prawdziwy_adres_docelowy",
        origin_label="A", destination_label="Buerer Strasse 8, Gelsenkirchen",
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
