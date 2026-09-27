import pytest

from flights import ExtrasProfile, FlightSegment, PriceType, estimate_price
from flights import calculator, extras as extras_module, travelpayouts
from flights.travelpayouts import TravelpayoutsError, cheapest_entry

SAMPLE_PAYLOAD = {
    "success": True,
    "data": {
        "DUS": {
            "0": {
                "price": 450.0,
                "airline": "FR",
                "flight_number": 123,
                "departure_at": "2026-11-15T06:00:00Z",
                "return_at": None,
                "expires_at": "2026-11-13T00:00:00Z",
            },
            "1": {
                "price": 300.0,
                "airline": "W6",
                "flight_number": 456,
                "departure_at": "2026-11-15T10:00:00Z",
                "return_at": None,
                "expires_at": "2026-11-13T00:00:00Z",
            },
        }
    },
    "error": None,
}


def test_cheapest_entry_wybiera_najnizsza_cene_miedzy_liczba_przesiadek():
    entry = cheapest_entry(SAMPLE_PAYLOAD, "DUS")
    assert entry["price"] == 300.0
    assert entry["transfers"] == 1
    assert entry["airline"] == "W6"


def test_cheapest_entry_brak_danych_dla_relacji():
    with pytest.raises(TravelpayoutsError):
        cheapest_entry({"success": True, "data": {}}, "XXX")


def test_fetch_cheapest_price_bez_tokena(monkeypatch):
    monkeypatch.delenv(travelpayouts.TOKEN_ENV_VAR, raising=False)
    with pytest.raises(TravelpayoutsError):
        travelpayouts.fetch_cheapest_price("WAW", "DUS", "2026-11-15")


def test_estimate_price_dolicza_wlasny_extras_profile(monkeypatch):
    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD)

    seg = FlightSegment(
        origin="WAW", destination="DUS", depart_date="2026-11-15", currency="PLN",
        extras=ExtrasProfile(baggage_cost=100, airport_access_cost=30, destination_transfer_cost=20),
    )
    result = estimate_price(seg)

    assert result.price_type is PriceType.ESTIMATE
    assert result.amount == pytest.approx(300 + 100 + 30 + 20)
    assert result.breakdown["cena_biletu"] == 300
    assert result.breakdown["przesiadki"] == 1
    assert result.breakdown["bagaz"] == 100
    assert result.origin == "WAW"
    assert result.destination == "DUS"


def test_estimate_price_uzywa_placeholderowej_tabeli_gdy_brak_extras(monkeypatch):
    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD)

    seg = FlightSegment(origin="WAW", destination="DUS", depart_date="2026-11-15")
    result = estimate_price(seg)

    assert result.amount > 300
    assert "placeholderowej" in result.notes


def test_estimate_price_brak_dokladnej_daty_uzywa_cache_miesiecznego(monkeypatch):
    """Gdy dokładna data nie ma wpisu w cache, ale cały miesiąc (depart_date="YYYY-MM") ma —
    użyj tej ceny zamiast od razu odrzucać wariant."""
    empty_payload = {"success": True, "data": {}}

    def fake_fetch(**kw):
        return SAMPLE_PAYLOAD if kw["depart_date"] == "2026-11" else empty_payload

    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", fake_fetch)

    seg = FlightSegment(
        origin="WAW", destination="DUS", depart_date="2026-11-15", currency="PLN",
        extras=ExtrasProfile(baggage_cost=0),
    )
    result = estimate_price(seg)

    assert result.amount == 300  # cena z SAMPLE_PAYLOAD, znaleziona przez zapytanie miesięczne
    assert "miesiąc" in result.notes


def test_estimate_price_brak_ceny_w_ogole_uzywa_zgrubnego_szacunku(monkeypatch):
    """Gdy nawet cały miesiąc nie ma ceny dla tej relacji (zbyt egzotyczna trasa/data poza
    zakresem cache), użyj stałego zgrubnego szacunku zamiast podnosić błąd i tracić cały wariant."""
    empty_payload = {"success": True, "data": {}}
    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: empty_payload)

    seg = FlightSegment(
        origin="WAW", destination="DTM", depart_date="2026-11-15", currency="PLN",
        extras=ExtrasProfile(baggage_cost=0),
    )
    result = estimate_price(seg)

    assert result.amount == calculator.GENERIC_FLIGHT_FALLBACK_PLN
    assert result.price_type is PriceType.ESTIMATE
    assert "zgrubny szacunek" in result.notes.lower()
    assert result.breakdown["linia"] is None


def test_estimate_price_niezgodna_waluta_extras(monkeypatch):
    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD)

    seg = FlightSegment(
        origin="WAW", destination="DUS", depart_date="2026-11-15", currency="PLN",
        extras=ExtrasProfile(baggage_cost=10, currency="EUR"),
    )
    with pytest.raises(ValueError):
        estimate_price(seg)


def test_extras_nieznana_relacja_zwraca_profil_zerowy_z_notatka():
    profile = extras_module.get_extras("XXX", "YYY")
    assert profile.total == 0
    assert profile.note


def test_extras_znana_relacja():
    profile = extras_module.get_extras("waw", "dus")
    assert profile.total > 0
    assert profile.currency == "PLN"


def test_get_baggage_by_airline_znany_przewoznik():
    amount, currency, source = extras_module.get_baggage_by_airline("fr")
    assert amount == 21.0
    assert currency == "EUR"
    assert "Ryanair" in source
    assert "zrodlo" not in source  # opis ma prawdziwy URL, nie nazwę pola


def test_get_baggage_by_airline_lufthansa():
    amount, currency, source = extras_module.get_baggage_by_airline("LH")
    assert amount == 30.0
    assert currency == "EUR"
    assert "Lufthansa" in source


def test_get_baggage_by_airline_nieznany_przewoznik():
    assert extras_module.get_baggage_by_airline("XX") is None


def test_get_baggage_by_airline_brak_kodu():
    assert extras_module.get_baggage_by_airline(None) is None
    assert extras_module.get_baggage_by_airline("") is None
