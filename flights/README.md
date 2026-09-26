# Moduł cen lotów (`flights/`)

Szacuje cenę pojedynczego segmentu lotu: cena biletu (z Travelpayouts Data API) + koszty
dodatkowe (bagaż, dojazd na lotnisko, transfer z lotniska do miasta docelowego). Struktura
analogiczna do [`fares/`](../fares/README.md): `Segment` (tu: `FlightSegment`), `PriceEstimate`,
`price_type`.

## Źródło cen: Travelpayouts Data API

Używamy endpointu `GET https://api.travelpayouts.com/v1/prices/cheap` (`flights/travelpayouts.py`).
Zwraca on najtańsze znalezione bilety (osobno dla lotów bezpośrednich, z 1 i z 2 przesiadkami)
dla podanej relacji i miesiąca/dnia wylotu — wybieramy z nich najtańszy.

**Dane pochodzą z cache Travelpayouts** (zgodnie z ich dokumentacją zalecają budowanie stron
statycznych na tych danych) — ceny mogą być nieaktualne o kilka dni, dlatego każdy wynik jest
oznaczony jako `PriceType.ESTIMATE` ("szacunek"), tak samo jak w module `fares/`.

### Konfiguracja tokena API

1. Zarejestruj się w programie partnerskim Travelpayouts: https://www.travelpayouts.com/programs/100/tools/api
   (sekcja Data API / Access token) — token jest darmowy.
2. Ustaw zmienną środowiskową:
   ```
   export TRAVELPAYOUTS_TOKEN=twoj_token          # Linux/macOS/Git Bash
   $env:TRAVELPAYOUTS_TOKEN = "twoj_token"        # PowerShell
   ```
3. Bez ustawionego tokena `estimate_price(...)` rzuci `TravelpayoutsError` z instrukcją, co zrobić.

Nie zgadywaliśmy żadnego klucza — token wstawiasz sam przez zmienną środowiskową.

## Koszty dodatkowe (bagaż, dojazd, transfer)

Sama cena biletu z API to nie jest realny koszt podróży. Doliczamy trzy osobne, konfigurowalne
składniki (`ExtrasProfile` w `flights/model.py`), bo różnią się między liniami lotniczymi i miastami:

- `baggage_cost` — bagaż rejestrowany (u wielu tanich linii bilet bez bagażu w cenie).
- `airport_access_cost` — dojazd na lotnisko wylotu.
- `destination_transfer_cost` — transfer z lotniska przylotu do miasta docelowego.

Możesz podać własny `ExtrasProfile` w `FlightSegment.extras`. Jeśli go nie podasz, moduł sięga
do placeholderowej tabeli `flights/data/extras_placeholder.json` (kilka przykładowych relacji
PL→NRW) — **te liczby też są przykładowe**, nie realne cenniki. Dla nieznanej relacji zwracany
jest profil zerowy z notatką, żeby dało się doliczyć koszty ręcznie.

## Użycie

```python
from flights import FlightSegment, ExtrasProfile, estimate_price

# z placeholderową tabelą kosztów dodatkowych
segment = FlightSegment(
    origin="WAW", destination="DUS",
    depart_date="2026-11-15", currency="PLN",
)
result = estimate_price(segment)
print(result)              # np. "624.00 PLN (szacunek) — WAW->DUS"
print(result.breakdown)

# z własnymi kosztami dodatkowymi
segment2 = FlightSegment(
    origin="KRK", destination="FMM", depart_date="2026-12-01", currency="PLN",
    extras=ExtrasProfile(baggage_cost=180, airport_access_cost=45, destination_transfer_cost=60),
)
result2 = estimate_price(segment2)
```

## Testy

```
pytest tests/test_flights.py
```

Testy mockują wywołanie Travelpayouts API (nie wymagają realnego tokena ani sieci) — sprawdzają
logikę wyboru najtańszego wpisu, doliczanie kosztów dodatkowych i obsługę braku tokena/danych.
