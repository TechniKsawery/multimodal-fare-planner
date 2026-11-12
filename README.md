# Multimodal Fare Planner

🇺🇸 English · 🇵🇱 [Wersja polska → README.pl.md](README.pl.md)

**A portfolio project for searching multimodal journeys between Poland and Germany and estimating their real-world cost.**

The application combines public timetable data, walking routes, rail and local-transit fares, passenger profiles, discounts, city cards, attractions, buses and optional flights. Instead of returning only a route, it explains the estimated total and the assumptions behind it.

> **Portfolio prototype — not a commercial booking service.** Prices are estimates, not offers. Always verify the final fare with the carrier before buying.

## What this project demonstrates

- Python application design with a FastAPI backend and Streamlit interface
- Multimodal routing through the open-source [MOTIS](https://github.com/motis-project/motis) engine
- GTFS and OpenStreetMap data ingestion, validation and refresh tooling
- Fare modelling for rail, regional transit, city tickets, discounts and passenger profiles
- Separation of routing, pricing, data sources and presentation layers
- Reproducible Docker-based local infrastructure
- Automated tests and end-to-end verification

## Current coverage

| Area | Included | Important limitation |
|---|---|---|
| Geography | Poland and Germany | Other countries are outside the current data and fare scope |
| Transport | Rail, selected city transit, FlixBus and optional flights | Coverage depends on available feeds and APIs |
| Pricing | PKP Intercity, selected Polish and German fares, city tariffs, discounts and cards | Estimates can be incomplete or out of date |
| Passenger profiles | Adult, student, senior, child and selected BahnCard/PKP/VRR options | Multiple passengers and several cards are not modelled |
| Travel extras | Selected city cards and 82 attractions in 10 cities | Prices are indicative and not always independently verified |
| Booking | Route and price estimation only | Ticket purchase and payment are not implemented |

The default setup covers Polish rail, German long-distance/regional rail, Lublin and NRW. A production-like configuration additionally includes Warsaw, Hamburg, Munich and Cologne/Bonn. See [`DATA_SOURCES.md`](DATA_SOURCES.md) for the feeds, licences and freshness notes.

## Architecture

```text
Streamlit UI / CLI
        ↓
FastAPI service
        ↓
Routing + itinerary normalisation
        ↓
MOTIS + GTFS + OpenStreetMap
        ↓
Fare calculators + discounts + city cards
```

Repository map:

- `routing/` — MOTIS client, itinerary processing and pricing orchestration
- `fares/` — fare calculators, discounts and source-backed data
- `attractions/` and `places/` — attractions, city cards and place selection
- `api/` — FastAPI application
- `app.py` — Streamlit user interface
- `motis/` — engine configuration and deployment notes
- `scripts/` — data download, validation, refresh and reproducibility tooling
- `tests/` — unit, integration and API tests

## Quick start

### Requirements

Python 3.11+, Docker Desktop, git, and at least 40 GB of free disk space. The full import needs approximately 10 GB of RAM available to Docker/WSL2.

```bash
git clone https://github.com/TechniKsawery/multimodal-fare-planner.git
cd multimodal-fare-planner
python -m venv .venv
```

Activate the environment and install dependencies:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt -r requirements-dev.txt
```

Download current GTFS and OSM data, build the MOTIS index and start the services:

```bash
python scripts/fetch_data.py
bash scripts/merge_osm.sh
bash scripts/run_motis.sh import
bash scripts/run_motis.sh server
```

In separate terminals:

```bash
uvicorn api.main:app --reload
python -m streamlit run app.py
```

The UI is available at `http://localhost:8501`, the API at `http://localhost:8000`, and MOTIS at `http://localhost:8080`.

For Windows, use the PowerShell equivalents in `scripts/`. For the larger Poland-plus-cities configuration, see `docker-compose.pl-cities.yml` and the detailed refresh notes in `scripts/README-refresh.md`.

### Optional flight prices

Copy `.env.example` to `.env` and set `TRAVELPAYOUTS_TOKEN`. Without a token, all non-flight functionality remains available and flight variants are omitted.

### Tests

```bash
pytest -q
```

The test suite does not require Docker or an API token; tests that need a running MOTIS instance skip themselves.

## Data freshness and reproducibility

GTFS and OSM files are downloaded locally and are intentionally not committed. Feeds expire, so refresh them before using the application:

```bash
python scripts/check_gtfs_freshness.py
```

Fare records include `zrodlo_url`, `data_weryfikacji` and `price_verified`. A value of `price_verified: false` means that the fare was not confirmed at the primary source. The repository currently contains no carrier price-list PDFs, feed copies, OSM extracts or Docker-built MOTIS index.

An end-to-end clean-machine verification was completed on 2026-11-12 on Windows/Python 3.13, including tests, data validation, OSM merging, MOTIS import, API queries and Streamlit search. The exact data snapshot is not permanent; current feeds must be downloaded again.

## Legal and licensing notes

- This is an independent project and is not affiliated with PKP Intercity, Deutsche Bahn, FlixBus, VRR, HVV, MVV, VRS, ZTM or any attraction operator.
- Prices, discounts and timetables are estimates and may be wrong or outdated. This software does not sell or reserve tickets.
- OpenStreetMap data requires attribution under the [ODbL](https://www.openstreetmap.org/copyright). GTFS providers retain their own licences; see [`DATA_SOURCES.md`](DATA_SOURCES.md).
- The project code is **All Rights Reserved**; viewing it for portfolio evaluation is allowed, but copying, modifying, redistributing or commercial use requires written permission. See [`LICENSE`](LICENSE).
- Optional unofficial carrier interfaces are disabled by default and should be used only for personal testing where permitted.
- Code, tests, translations and part of the research were created with substantial assistance from AI tools. AI-generated research was treated as unverified until checked against primary sources.

For security matters, see [`SECURITY.md`](SECURITY.md).
