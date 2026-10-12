import pytest

from flights import (
    ExtrasProfile,
    FlightSegment,
    PriceType,
    calculator,
    estimate_price,
    travelpayouts,
)
from flights import extras as extras_module
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


def test_cheapest_entry_wybiera_najnizsza_cene_a_przesiadki_sa_nieznane():
    entry = cheapest_entry(SAMPLE_PAYLOAD, "DUS")
    assert entry["price"] == 300.0
    assert entry["transfers"] is None  # klucz "1" to numer wyniku, nie liczba przesiadek
    assert entry["airline"] == "W6"


def test_cheapest_entry_brak_danych_dla_relacji():
    with pytest.raises(TravelpayoutsError):
        cheapest_entry({"success": True, "data": {}}, "XXX")


def test_fetch_cheapest_price_bez_tokena(monkeypatch):
    monkeypatch.delenv(travelpayouts.TOKEN_ENV_VAR, raising=False)
    with pytest.raises(TravelpayoutsError):
        travelpayouts.fetch_cheapest_price("WAW", "DUS", "2026-11-15")


def test_estimate_price_dolicza_wlasny_extras_profile(monkeypatch):
    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD
    )

    seg = FlightSegment(
        origin="WAW",
        destination="DUS",
        depart_date="2026-11-15",
        currency="PLN",
        extras=ExtrasProfile(
            baggage_cost=100, airport_access_cost=30, destination_transfer_cost=20
        ),
    )
    result = estimate_price(seg)

    assert result.price_type is PriceType.ESTIMATE
    assert result.amount == pytest.approx(300 + 100 + 30 + 20)
    assert result.breakdown["cena_biletu"] == 300
    assert result.breakdown["przesiadki"] is None
    assert result.breakdown["bagaz"] == 100
    assert result.origin == "WAW"
    assert result.destination == "DUS"


def test_estimate_price_uzywa_placeholderowej_tabeli_gdy_brak_extras(monkeypatch):
    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD
    )

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
        origin="WAW",
        destination="DUS",
        depart_date="2026-11-15",
        currency="PLN",
        extras=ExtrasProfile(baggage_cost=0),
    )
    result = estimate_price(seg)

    assert result.amount == 300  # cena z SAMPLE_PAYLOAD, znaleziona przez zapytanie miesięczne
    assert "miesiąc" in result.notes


def test_estimate_price_brak_ceny_w_ogole_uzywa_zgrubnego_szacunku(monkeypatch):
    """Gdy nawet cały miesiąc nie ma ceny dla tej relacji (zbyt egzotyczna trasa/data poza
    zakresem cache), użyj stałego zgrubnego szacunku zamiast podnosić błąd i tracić cały wariant."""
    empty_payload = {"success": True, "data": {}}
    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: empty_payload
    )

    seg = FlightSegment(
        origin="WAW",
        destination="DTM",
        depart_date="2026-11-15",
        currency="PLN",
        extras=ExtrasProfile(baggage_cost=0),
    )
    result = estimate_price(seg)

    assert result.amount == calculator.GENERIC_FLIGHT_FALLBACK_PLN
    assert result.price_type is PriceType.ESTIMATE
    assert "zgrubny szacunek" in result.notes.lower()
    assert result.breakdown["linia"] is None


def test_estimate_price_zgrubny_szacunek_jest_przeliczany_na_walute_segmentu(monkeypatch):
    """350 PLN to kwota w złotych: z flight_currency=EUR nie wolno jej podpisać jako 350 EUR."""
    from common.currency import PLACEHOLDER_RATES_TO_PLN

    empty_payload = {"success": True, "data": {}}
    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: empty_payload
    )

    seg = FlightSegment(
        origin="WAW",
        destination="DTM",
        depart_date="2026-11-15",
        currency="EUR",
        extras=ExtrasProfile(baggage_cost=0, currency="EUR"),
    )
    result = estimate_price(seg)

    expected = round(calculator.GENERIC_FLIGHT_FALLBACK_PLN / PLACEHOLDER_RATES_TO_PLN["EUR"], 2)
    assert result.currency == "EUR"
    assert result.amount == pytest.approx(expected)
    assert result.amount != calculator.GENERIC_FLIGHT_FALLBACK_PLN
    assert result.breakdown["cena_biletu"] == pytest.approx(expected)
    # notatka podaje i kwotę źródłową w PLN, i przeliczenie
    assert "350 PLN" in result.notes
    assert f"{expected:.2f} EUR" in result.notes


def test_estimate_price_tabela_extras_w_pln_jest_przeliczana_na_eur(monkeypatch):
    """Bez własnego ExtrasProfile koszty z tabeli (PLN) wcześniej dawały ValueError dla EUR."""
    from common.currency import PLACEHOLDER_RATES_TO_PLN

    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD
    )
    seg = FlightSegment(origin="WAW", destination="DUS", depart_date="2026-11-15", currency="EUR")
    result = estimate_price(seg)

    rate = PLACEHOLDER_RATES_TO_PLN["EUR"]
    table = extras_module.get_extras("WAW", "DUS")  # 150 / 40 / 25 PLN
    assert result.currency == "EUR"
    assert result.breakdown["bagaz"] == pytest.approx(table.baggage_cost / rate, abs=0.01)
    assert result.breakdown["dojazd_na_lotnisko"] == pytest.approx(
        table.airport_access_cost / rate, abs=0.01
    )
    assert result.breakdown["transfer_z_lotniska"] == pytest.approx(
        table.destination_transfer_cost / rate, abs=0.01
    )
    # bilet z cache jest już w EUR (Travelpayouts dostaje currency=EUR), extras w PLN dodane NIE 1:1
    assert result.amount == pytest.approx(300 + table.total / rate, abs=0.02)


def test_estimate_price_nieobslugiwana_waluta_podnosi_czytelny_blad(monkeypatch):
    from common.currency import UnsupportedCurrencyError

    def must_not_be_called(**kw):
        raise AssertionError("waluta bez kursu powinna być odrzucona przed zapytaniem do API")

    monkeypatch.setattr(calculator.travelpayouts, "fetch_cheapest_price", must_not_be_called)
    seg = FlightSegment(origin="WAW", destination="DUS", depart_date="2026-11-15", currency="GBP")
    with pytest.raises(UnsupportedCurrencyError) as exc_info:
        estimate_price(seg)
    assert "GBP" in str(exc_info.value)
    assert "EUR" in str(exc_info.value) and "PLN" in str(exc_info.value)


def test_estimate_price_niezgodna_waluta_extras(monkeypatch):
    monkeypatch.setattr(
        calculator.travelpayouts, "fetch_cheapest_price", lambda **kw: SAMPLE_PAYLOAD
    )

    seg = FlightSegment(
        origin="WAW",
        destination="DUS",
        depart_date="2026-11-15",
        currency="PLN",
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
