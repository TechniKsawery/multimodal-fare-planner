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

### Gdy w cache nie ma ceny dla konkretnej daty/relacji

Cache Travelpayouts nie obejmuje każdej relacji i daty — dla mniej popularnych tras albo dat
odległych w czasie zapytanie o konkretny dzień może nie zwrócić nic. Zamiast od razu odrzucać
cały wariant lotu (`TravelpayoutsError` -> `SkippedVariant` w `routing/variants.py`),
`estimate_price` próbuje kolejno:

1. Cenę dla dokładnej daty (jak wyżej).
2. Cenę z cache dla CAŁEGO miesiąca (API akceptuje `depart_date="YYYY-MM"`) — może nie trafiać
   dokładnie w wybrany dzień, ale to wciąż realna cena z cache dla tej relacji.
3. Jeśli i to nie da wyniku: stały, bardzo zgrubny szacunek (`GENERIC_FLIGHT_FALLBACK_PLN` w
   `flights/calculator.py`) oparty na rzędzie wielkości typowych cen tanich linii na krótkich
   trasach PL-DE — NIE jest to cena dla konkretnej relacji.

Każdy z tych trzech przypadków jest jasno opisany w `PriceEstimate.notes`, więc widać po wyniku,
na ile realna jest podana cena.

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

### Realne cenniki bagażu wg linii (`flights/data/baggage_by_airline.json`)

`flights.extras.get_baggage_by_airline(kod_iata)` zwraca (kwota, waluta, opis_źródła) dla
przewoźników, dla których sprawdziliśmy realny, publiczny cennik bagażu rejestrowanego (nie
placeholder): **Ryanair (FR)**, **Wizz Air (W6)**, **LOT (LO)**, **Eurowings (EW)**,
**Lufthansa (LH)** — kody IATA tak jak zwraca je Travelpayouts w polu `airline`. Dla nieznanego
przewoźnika zwraca `None`.

Dobór tej piątki nie jest przypadkowy: to faktyczni przewoźnicy z lotniska w Lublinie (LUZ) —
Ryanair, Wizz Air i Lufthansa — plus Wizz Air/Ryanair na Warszawa-Dortmund (oba huby użyte w
`routing/demo_route.py`) i Eurowings jako częsty operator tras Warszawa-Düsseldorf/Kolonia.
Dodawanie kolejnych linii bez sprawdzenia, czy faktycznie obsługują interesujące nas trasy,
nie ma sensu — i tak nie mamy publicznego API cen bagażu, więc każdy kolejny wpis to ręczne
wyszukanie i zweryfikowanie cennika.

**Ważne:** opłaty za bagaż u tanich linii są **dynamiczne** (zależą od trasy, terminu zakupu i
sezonu) — kwota w tabeli to **dolna granica** opublikowanego przedziału (patrz pole `zakres` i
`zrodlo` w JSON-ie), nie gwarantowana cena konkretnego lotu. Dlatego to i tak `PriceType.ESTIMATE`.
Silnik tras (`routing/`) używa tej funkcji, żeby doprecyzować szacunek bagażu, gdy z biletu
Travelpayouts znana jest linia — patrz `routing/README.md`.

### Bagaż podręczny (`flights/data/cabin_baggage.json`, `flights/cabin_baggage.py`)

`get_cabin_baggage(kod_iata)` zwraca jeden z trzech jawnych stanów: **wliczony**, **płatny**
(dopłata jako kwota lub widełki w ORYGINALNEJ walucie przewoźnika — bez przeliczania po
placeholderowym kursie) albo **nieznany** (brak przewoźnika/wpisu, wpis bez `price_verified`,
albo zasada zależna od taryfy, której nie znamy z ceny z cache). Wynik trafia do
`breakdown["bagaz_podreczny"]` odcinka lotu i jest pokazywany w UI (`app.py`) i `demo.py`.
Dopłata za podręczny NIE jest doliczana do ceny biletu ani do ceny łącznej.

**Uwaga o pochodzeniu danych:** wpisy Wizz Air, Ryanair, Eurowings i easyJet wpisała zewnętrzna
AI (Gemini) i NIE zostały jeszcze sprawdzone przez Claude; na tej gałęzi aplikacja traktuje je
zgodnie z flagą `price_verified` w pliku. Nie scalać na `main` przed weryfikacją w źródłach.

Sprawdzone źródła (stan na 2026-09-27):
- Ryanair: https://www.moneyguideireland.com/ryanair-increased-baggage-allowance-of-20kg.html
- Wizz Air: https://www.sendmybag.com/airlines/wizz-air-baggage-allowance/
- LOT: https://kolokwialnienaemigracji.pl/ile-kosztuje-bagaz-rejestrowany-w-lot-sprawdz-ceny-i-uniknij-doplat
- Eurowings: https://www.eurosender.com/en/airlines/eurowings-baggage-allowance
- Lufthansa: https://business.lufthansagroup.com/content/dam/b2b/experts/files/LHG_FBAG_EcoLight_EN.pdf (oficjalny cennik)

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
