# Multimodal Fare Planner

🇺🇸 English (this file) · 🇵🇱 [Wersja polska → README.pl.md](README.pl.md)

A journey search engine for rail (plus some bus and flight options) between Poland and Germany
(e.g. Lublin → Gelsenkirchen) that **estimates what you would actually pay**, taking discounts, age and
cards into account.

## Project status

> **Portfolio project / prototype, not a commercial product.** Last repository update:
> **2026-11-12** (clean-up before publication); last functional changes: 2026-11-09.

- **Scope:** PL + DE routing on the open-source [MOTIS](https://github.com/motis-project/motis) engine
  and open GTFS feeds, plus a price-estimation layer (discounts, cards, city tickets, attractions).
  Prices are **estimates**, not an offer, with no guarantee of accuracy. Ticket purchase is not implemented.
- **Data and freshness:** GTFS/OSM data is downloaded by scripts (not stored in the repo) and expires.
  According to notes from 2026-10-12 the feeds used locally were valid until 2026-11-09 (Warsaw until
  2026-11-11), so **they must be refreshed before use** (see "Refreshing data"). Fare records carry
  `zrodlo_url`, `data_weryfikacji` and `price_verified` fields; `price_verified: false` means not confirmed
  at the source. Most verification was done in October 2026.
- **Use of AI:** code, tests, translations, part of the source research and commit messages were produced
  with heavy use of AI tools (Claude, Gemini). Research data from AI is marked "per Gemini, not independently
  verified" until checked at the primary source.
- **Licence:** **All Rights Reserved** (see [LICENSE](LICENSE)). The code may be viewed to evaluate the
  author's work; copying, modifying, redistributing or commercial use requires written permission.
  Third-party data keeps its own licences ([DATA_SOURCES.md](DATA_SOURCES.md)). The repository does not
  contain the carriers' original price-list PDFs; sources are linked.

## Rebuilding the environment from scratch

Requirements: Python 3.11+, Docker Desktop (WSL2 on Windows), git, **at least 40 GB free disk**,
**about 10 GB RAM for WSL2/Docker** (the OSM import ran out of memory at the default limit; see the
`.wslconfig` example in `motis/DE-FULL-CITY-GTFS-NOTES.md`). Downloads are several GB (Poland + NRW OSM;
full Germany is ~7 GB and only used by the `docker-compose.de-full*.yml` variants).

1. `python -m venv venv`, activate it, `pip install -r requirements.txt` (`requirements-dev.txt` for tests).
2. `python scripts/fetch_data.py` downloads the GTFS feeds and OSM extracts into `data/`
   (sources and licences: [DATA_SOURCES.md](DATA_SOURCES.md)). If a URL stops working, update it there and in the script.
3. `scripts/merge_osm.sh` merges the Poland and NRW extracts into `data/osm/poland-nrw-latest.osm.pbf`,
   which `motis/config.yml` expects (needs `osmium-tool` or Docker; the Docker variant is untested).
4. `scripts/run_motis.sh import` (Windows: `scripts\run_motis.ps1 import`) builds the MOTIS index in a Docker
   volume; typically tens of minutes up to over an hour. Then `scripts/run_motis.sh server`
   (MOTIS API at `http://localhost:8080`).
5. API: `uvicorn api.main:app --reload`; UI: `python -m streamlit run app.py` (`http://localhost:8501`);
   command-line demo: `python demo.py`.
6. Tests: `pytest -q` (no Docker or token needed; tests that need MOTIS skip themselves).
7. Optional: copy `.env.example` to `.env` and set `TRAVELPAYOUTS_TOKEN` for flight prices; without it
   everything else works and flight variants simply do not appear.

### Refreshing data

GTFS feeds expire (gtfs.de within days, others within weeks/months). `python scripts/check_gtfs_freshness.py`
reports validity dates; on Windows `scripts\refresh_prod.ps1` rebuilds MOTIS without deleting the previous
data (see [scripts/README-refresh.md](scripts/README-refresh.md), in Polish). Fares and discounts in
`fares/data/*.json` are updated by hand using each record's `zrodlo_url` and `data_weryfikacji`.

### Versions and reproducibility

The `docker-compose*.yml` files pin the MOTIS image to a digest (pulled 2026-11-12):
`ghcr.io/motis-project/motis@sha256:594eff881d4319549387563a28dffb2ac48650df5422325a44a6c2f69f79e9b9`. Override it with `MOTIS_IMAGE` in `.env`. To update the pin:
`docker pull ghcr.io/motis-project/motis:latest`, then
`docker image inspect ghcr.io/motis-project/motis:latest --format "{{index .RepoDigests 0}}"`, and replace the digest in
`docker-compose*.yml` (search for `MOTIS_IMAGE`). Note: the pinned build was tested only with data imported on that date.

## What the repository does NOT contain

The repository is the single source of truth; everything below must be recreated from it.

| Item | Status | How to get it back |
|---|---|---|
| `.env` and API tokens (`TRAVELPAYOUTS_TOKEN`) | **Not recoverable**: secrets are never committed | Create a new Travelpayouts token and put it in `.env` (copy `.env.example`); optional, flights are skipped without it |
| GTFS and OSM data (`data/`) | Downloaded, not stored | `python scripts/fetch_data.py` (+ `scripts/fetch_data_extended.py`); feeds are "latest" snapshots, so **past versions cannot be restored** and the HVV link (dated snapshot) may need replacing |
| Built MOTIS index (Docker volumes) | Rebuilt, not stored | `scripts/run_motis.ps1 import` (or `docker compose` for the variant you use); tens of minutes to over an hour |
| Production/rollback containers and volumes (`motis-main`, `motis-main-old`, `mw_motis_refresh_*`) | Local only, not needed | Recreated by `scripts/refresh_prod.ps1` from the repo; no data from the old machine is required |
| Carriers' price-list PDFs and page snapshots | Removed (copyright) | Sources are linked in `fares/data/*.json` (`zrodlo_url`); re-verify prices by hand |
| Old PR/issue history, review comments | Not carried over to this repository | none |
| Unofficial DB prices service (`tools/db-vendo-service`) | Optional | `npm install && npm start`; may be blocked by DB; needs no token |
| Human verification of prices | Dated, goes stale | each record's `data_weryfikacji`; `price_verified: false` = unverified |

### Production-like variant (Warsaw/Kraków/Hamburg/Munich/Cologne city feeds, full-Germany OSM)

```
python scripts/fetch_data.py
python scripts/fetch_data_extended.py        # Germany OSM + HVV/MVV/VRS feeds (several GB)
bash scripts/merge_osm.sh germany            # -> data/osm/poland-germany-latest.osm.pbf (~7 GB)
docker compose -f docker-compose.pl-cities.yml --profile import-pl-cities run --rm motis-import-pl-cities
docker compose -f docker-compose.pl-cities.yml up motis-pl-cities     # MOTIS on http://localhost:8082
```

Point the app at it with `MOTIS_BASE_URL=http://localhost:8082` (PowerShell: `$env:MOTIS_BASE_URL="http://localhost:8082"`).
Later refreshes: `scripts\refresh_prod.ps1` (see `scripts/README-refresh.md`).

## End-to-end check on a clean machine

1. Fresh folder: `git clone <repo>`, `cd` into it, `python -m venv .venv`, activate, `pip install -r requirements.txt -r requirements-dev.txt`.
2. `pytest -q` (expect ~2079 passed, 12 skipped, no Docker needed).
3. `python scripts/fetch_data.py` then `bash scripts/merge_osm.sh` (default NRW variant).
4. Clean Docker state for the test: `docker volume ls` should not list this project's volume (`<folder>_motis-data`); then `scripts\run_motis.ps1 import`.
5. `scripts\run_motis.ps1 server` (port 8080; stop any other container using it).
6. One route query with a date inside the feed validity window: `python demo.py --from "Lublin Dworzec Główny" --to "Gelsenkirchen Hbf" --date <date within the next week> --age 25`.
7. Optional: `python -m streamlit run app.py` and `uvicorn api.main:app --port 8010`.
8. If all of the above works, nothing from the original machine is needed.

## Repository map

`routing/` MOTIS client and itinerary building · `fares/` fare calculators and data · `attractions/`
attractions and city cards · `places/` place aliases and selection · `flights/` flight prices ·
`api/` FastAPI service · `app.py` Streamlit UI (PL/EN/DE/ES/FR/NL) · `i18n/` UI texts · `motis/` engine
config and notes · `scripts/` data and refresh tooling · `tests/` pytest suite · `research/`,
`verification/` source audits and verification notes (Polish).

The detailed technical documentation (sessions 1–7, API, fares, architecture) is in
[README.pl.md](README.pl.md) (Polish).
