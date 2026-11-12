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

## Repository map

`routing/` MOTIS client and itinerary building · `fares/` fare calculators and data · `attractions/`
attractions and city cards · `places/` place aliases and selection · `flights/` flight prices ·
`api/` FastAPI service · `app.py` Streamlit UI (PL/EN/DE/ES/FR/NL) · `i18n/` UI texts · `motis/` engine
config and notes · `scripts/` data and refresh tooling · `tests/` pytest suite · `research/`,
`verification/` source audits and verification notes (Polish).

The detailed technical documentation (sessions 1–7, API, fares, architecture) is in
[README.pl.md](README.pl.md) (Polish).
