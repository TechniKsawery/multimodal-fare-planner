English | Polski: [wersja polska](README.pl.md)

# Flight pricing module (`flights/`)

Estimates the price of a single flight segment: ticket price (from the Travelpayouts Data API) plus additional costs (baggage, access to the airport, and transfer from the airport to the destination city). Its structure is analogous to [`fares/`](../fares/README.md): `Segment` (here: `FlightSegment`), `PriceEstimate`, and `price_type`.

## Price source: Travelpayouts Data API

We use the endpoint `GET https://api.travelpayouts.com/v1/prices/cheap` (`flights/travelpayouts.py`). It returns the cheapest tickets found (separately for direct flights and flights with 1 or 2 stops) for the specified route and departure month/day.

### Meaning of keys "0"/"1"/"2" (a direct flight = ONLY key "0")

In `data[<IATA>]`, the key is the **number of stops**: `"0"` = direct flight, `"1"` = 1 stop, `"2"` = 2 stops. The module treats only entry `"0"` as direct; it ignores `"1"`/`"2"` even when they are cheaper. When `"0"` is missing, `estimate_price` tries the monthly cache and finally returns a rough estimate labelled "cena niepotwierdzona" (`breakdown["price_verified"]=False`)—never a connecting flight.

**Verification status (honestly):** the official Travelpayouts documentation could not be opened from the environment used for this change (no network access to `support.travelpayouts.com`/`travelpayouts.github.io`), so there is no quotation from the official docs. The basis for this decision is: (1) the method description in the Go client ("returns the cheapest direct, as well as 1 and 2 transfers") and this README's original description; (2) live response data—in five checked routes (WAW-DUS, KRK-BER, WRO-MUC, GDN-FRA, POZ-HAM) there were only `"1"`/`"2"` keys, with flight times too long for direct flights (160–380 min); if the key were the next-result number, key `"0"` would always occur. If the official documentation says otherwise, change `DIRECT_KEY` in `flights/travelpayouts.py` and the tests in `tests/test_flights.py`.

**Data comes from the Travelpayouts cache** (their documentation recommends building static sites from this data)—prices may be several days out of date, so every result is marked `PriceType.ESTIMATE` ("szacunek"), just as in `fares/`.

### API token configuration

1. Register for the Travelpayouts affiliate programme: https://www.travelpayouts.com/programs/100/tools/api (Data API / Access token section)—the token is free.
2. Set the environment variable:
   ```
   export TRAVELPAYOUTS_TOKEN=twoj_token          # Linux/macOS/Git Bash
   $env:TRAVELPAYOUTS_TOKEN = "twoj_token"        # PowerShell
   ```
3. Without a token, `estimate_price(...)` raises `TravelpayoutsError` with instructions.

We do not guess any key—you provide the token through the environment variable.

### When the cache has no price for a particular date/route

The Travelpayouts cache does not cover every route and date—for less popular routes or distant dates, a query for a particular day may return nothing. Instead of immediately rejecting the entire flight variant (`TravelpayoutsError` -> `SkippedVariant` in `routing/variants.py`), `estimate_price` tries:

1. The exact date price (as above).
2. A price from the cache for the WHOLE month (the API accepts `depart_date="YYYY-MM"`). It may not match the selected day exactly, but is still a real cached price for the route.
3. If that also yields nothing (including when the cache contains only connecting flights, keys `"1"`/`"2"`): a fixed, very rough estimate labelled "cena niepotwierdzona" (`GENERIC_FLIGHT_FALLBACK_PLN` in `flights/calculator.py`) based on the order of magnitude of typical low-cost fares on short PL-DE routes—not a price for the particular route. The amount is in PLN: for a segment in another currency (for example `currency="EUR"`), it is converted using the NBP rate from `common/currency.py` (an estimate for comparisons), and the note gives both amounts. The same applies to additional costs from `extras_placeholder.json` (PLN) for a segment in EUR. A currency without a rate (for example GBP) raises `UnsupportedCurrencyError` (a `ValueError` subclass) with the supported-currency list—we do not guess rates.

Each of these three cases is clearly described in `PriceEstimate.notes`, so the result shows how realistic the price is.

## Additional costs (baggage, access, transfer)

The ticket price from the API is not the real trip cost. We add three separate, configurable components (`ExtrasProfile` in `flights/model.py`) because they vary by airline and city:

- `baggage_cost`—checked baggage (many low-cost tickets do not include baggage).
- `airport_access_cost`—access to the departure airport.
- `destination_transfer_cost`—transfer from the arrival airport to the destination city.

You can provide your own `ExtrasProfile` in `FlightSegment.extras`. If you do not, the module uses the placeholder table `flights/data/extras_placeholder.json` (several example PL→NRW routes)—**these figures are also examples**, not real tariffs. For an unknown route, it returns a zero profile with a note so that costs can be added manually.

### Real airline baggage tariffs (`flights/data/baggage_by_airline.json`)

`flights.extras.get_baggage_by_airline(IATA_code)` returns (amount, currency, source description) for carriers whose real public checked-baggage tariff we verified (not a placeholder): **Ryanair (FR)**, **Wizz Air (W6)**, **LOT (LO)**, **Eurowings (EW)**, **Lufthansa (LH)**—IATA codes as returned by Travelpayouts in the `airline` field. For an unknown carrier it returns `None`.

This set is intentional: they are actual carriers from Lublin Airport (LUZ)—Ryanair, Wizz Air, and Lufthansa—plus Wizz Air/Ryanair on Warsaw-Dortmund (both hubs used in `routing/demo_route.py`) and Eurowings as a frequent Warsaw-Düsseldorf/Cologne operator. Adding more airlines without checking whether they actually serve the routes of interest makes no sense—we have no public baggage-price API, so every new entry requires a manual tariff search and verification.

**Important:** low-cost baggage fees are **dynamic** (depending on route, purchase timing, and season)—the table amount is the **lower bound** of the published range (see `zakres` and `zrodlo` in the JSON), not a guaranteed price for a particular flight. It is therefore still `PriceType.ESTIMATE`. The routing engine (`routing/`) uses this function to refine the baggage estimate when the airline is known from the Travelpayouts ticket—see `routing/README.md`.

### Cabin baggage (`flights/data/cabin_baggage.json`, `flights/cabin_baggage.py`)

`get_cabin_baggage(IATA_code)` returns one of three explicit states: **included**, **paid** (a fee as an amount or range in the carrier's ORIGINAL currency—without conversion using a placeholder rate), or **unknown** (missing carrier/entry, an entry without `price_verified`, or a fare-dependent rule that cannot be inferred from the cached price). The result is placed in `breakdown["bagaz_podreczny"]` for the flight segment and shown in the UI (`app.py`) and `demo.py`. The cabin-baggage fee is NOT added to the ticket price or total price.

**Cabin-baggage data verification (2026-10-12):** `price_verified: true` means that dimensions, weight, and inclusion rule were checked on the carrier's website (source and date are present in every entry). Fees have a separate `doplata_potwierdzona` flag:
- **Ryanair (FR)**: `true`—**only as an official range** (the UI says “range”, not a flight price). Official PL and EN pages differ, so both ranges are stored: online at booking PL **6–36** vs EN **12,49–36**; after booking / at the airport PL 20–60 vs EN 19,99–45,50 (EN stored, PL in the label); at the gate both versions 46–75 (€/£). Basis: two matching Gemini reports from the rendered official fee table (2026-10-12), **according to Gemini, not independently verified** (the page renders via script). Details and quotations: `doplata_potwierdzenie` in the JSON.
- **Wizz Air (W6)**: `true`—same, only as an official range. Three separate tariff entries: WIZZ Priority online / call centre **13,00–57,50 €**; **65–75 €** = purchase of WIZZ Priority at the airport; **55–65 €** = fee for cabin baggage sent to the hold (Cabin Baggage fee).
- **Eurowings (EW)**: `false`—the online price is only a minimum “from €21” (the former €18 was resolved as an archived marketing rate and a 23 kg checked-baggage rate; offline airport €45, at the gate €60), with no public upper bound.
- **easyJet (U2)**: `false`—the online price is fully dynamic without a public amount range (gate: 300 zł / 70 € / 60 £).
Each carrier's amounts remain in one currency (no conversion); source discrepancies are described in `uwaga` fields (Ryanair PL vs EN—both are stored rather than choosing one).

Checked checked-baggage sources (as of 2026-09-27):
- Ryanair: https://www.moneyguideireland.com/ryanair-increased-baggage-allowance-of-20kg.html
- Wizz Air: https://www.sendmybag.com/airlines/wizz-air-baggage-allowance/
- LOT: https://kolokwialnienaemigracji.pl/ile-kosztuje-bagaz-rejestrowany-w-lot-sprawdz-ceny-i-uniknij-doplat
- Eurowings: https://www.eurosender.com/en/airlines/eurowings-baggage-allowance
- Lufthansa: https://business.lufthansagroup.com/content/dam/b2b/experts/files/LHG_FBAG_EcoLight_EN.pdf (official tariff)

## Usage

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

## Tests

```
pytest tests/test_flights.py
```

The tests mock Travelpayouts API calls (no real token or network required)—they check selection of only the direct entry (key `"0"`, fixtures from live data for five routes), adding extra costs, and handling missing tokens/data.
