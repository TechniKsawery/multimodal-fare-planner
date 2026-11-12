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

## Coverage: what is supported and what is not

Based on the code (`routing/pricing.py`, `fares/`), the MOTIS configs (`motis/config*.yml`) and the data files; state of
the data as of **2026-11-12**. "Estimate" means the price is not an official tariff or is unconfirmed (`price_verified: false`).

| Area | Supported | NOT supported / limits |
|---|---|---|
| **Countries** | Poland and Germany only | Any other country (CZ, AT, NL, FR ...) has no timetable data and no tariffs |
| **Timetables (MOTIS)** | Default config: Polish rail, German FV/RV/NV (gtfs.de), ZTM Lublin. Production-like config adds Warsaw, Kraków, Hamburg (HVV), Munich (MVV), Cologne/Bonn (VRS) | Other cities' local transit has no timetable; Kraków (ZTP) licence unconfirmed. Feeds expire: those used on 2026-11-12 were valid only until about 2026-11-09, refresh before use |
| **Addresses / walking** | Default OSM extract covers Poland + NRW; production-like config covers Poland + all Germany | Outside the loaded OSM area, address geocoding and walking legs do not work |
| **Rail, long-distance** | PKP Intercity (domestic bands), DB Flexpreis (domestic upper bound), cross-border PL↔DE (Sparpreis Europa, PKP Super Promo International levels I–V) | Saxonia, Via Regia (Leipzig), Chopin and Carpatia (Munich, sleepers) are not modelled; no tariffs for other operators |
| **Rail, regional** | Polregio, Koleje Mazowieckie, Koleje Małopolskie, ŁKA, SKM Trójmiasto, VRR eezy.nrw (NRW only), Zgorzelec–Görlitz (ZVON, KD), border ticket Zasieki–Forst | German regional rail outside NRW is an unconfirmed estimate; other Polish regional carriers are not modelled |
| **Local transit, with city tariff** | Lublin, Warsaw, Kraków, Poznań, Wrocław, Berlin (BVG/VBB), Hamburg (HVV), Munich (MVV), Cologne (VRS/KVB), NRW (VRR) | Every other city (e.g. Gdańsk, Łódź, Katowice, Szczecin, Dresden, Leipzig, Frankfurt, Stuttgart) has no local tariff; the app falls back to a generic estimate |
| **Long-distance bus** | FlixBus (unofficial API with live prices; fallback 0.27 PLN/km) | Other bus operators; the FlixBus API may be blocked and prices are snapshots |
| **Flights** | Prices from Travelpayouts Data API (optional token); 12 Polish and 25 German airports in `routing/data/airports.json`, 6 relations with baggage/transfer extras (placeholder values) | Not verified at the airline; bagage/transfer extras are placeholders; multi-segment flights are out of scope |
| **Discounts and profiles** | Age, student, senior, BahnCard 25/50/100, PKP discount codes, VRR child tariff, per-city student/child/senior tiers where verified | Deutschlandticket exists only as data (not applied in price calculation); discounts without a source are set to 0% and flagged; other cards and multiple passengers are out of scope |
| **City attractions and cards** | 82 attractions in 10 cities (Gelsenkirchen, Berlin, Kraków, Lublin, Warsaw, Hamburg, Munich, Cologne, Wrocław, Poznań); 9 city cards (Berlin, Ruhr, Kraków, Hamburg, Munich, Cologne, Warsaw, Poznań, Lublin) | Other cities; prices are indicative and some are not confirmed at the source |
| **Booking / payment** | none | The app only estimates; it does not sell or book tickets |

Known limits: prices are estimates and may be outdated (verification dates in the data files, mostly October 2026, newest 2026-11-03);
some research data comes from AI and is marked as not independently verified; results depend on feed validity.

## Legal notices, attribution and disclaimer

*Not legal advice; a good-faith summary of the terms checked on 2026-11-12. Verify at the sources.*

- **Independence / trademarks:** this is an independent hobby/portfolio project. It is **not affiliated with,
  endorsed or sponsored by** PKP Intercity, Deutsche Bahn, FlixBus, VRR, HVV, MVV, VRS, ZTM, any city or any other
  carrier or attraction operator. All names and trademarks (e.g. BahnCard, Deutschlandticket, Intercity) belong to their
  owners and are used only to identify the products whose prices are estimated. No logos are included.
- **No warranty / not an offer:** prices, discounts and timetables are estimates from public sources and can be wrong or
  outdated; they are not an offer and not a booking. Always check the price with the carrier before buying.
  The software is provided "as is" (see [LICENSE](LICENSE)).
- **Map and routing data:** contains information from OpenStreetMap, **© OpenStreetMap contributors**, available under the
  [Open Database Licence (ODbL)](https://www.openstreetmap.org/copyright). Any public deployment of this software must
  show that credit. Extracts come from Geofabrik. The repository contains no OSM data.
- **Timetable data (GTFS):** Polish rail feed by M. Kuranowski ([mkuran.pl/gtfs](https://mkuran.pl/gtfs); data of PKP PLK
  and Koleje Mazowieckie under their public-sector terms), Warsaw feed: ZTM Warszawa / M. Kuranowski / OpenStreetMap
  contributors (ODbL for shapes), Lublin: CC0, German feeds from [gtfs.de](https://gtfs.de) (CC BY 4.0, provided without
  guarantee), HVV (DL-DE-BY-2.0), MVV and VRS (CC BY 4.0). Details: [DATA_SOURCES.md](DATA_SOURCES.md). Kraków (ZTP)
  has no confirmed licence and is for local testing only. The repository contains no feed copies.
- **Routing engine:** [MOTIS](https://github.com/motis-project/motis) (MIT), run from its official Docker image; not
  bundled in this repository. Other dependencies (Streamlit, FastAPI, Uvicorn, Requests, python-dotenv,
  db-vendo-client) keep their own open-source licences and are not redistributed here.
- **Unofficial sources:** optional price lookups (`UNOFFICIAL_PRICES=1`, off by default) use unofficial interfaces of
  carriers; their terms may forbid this. Use only for your own testing, at your own risk.
- **AI use:** see "Use of AI" above. Commits carry `Claude <noreply@anthropic.com>` as author where the code was generated.
- **Security / contact:** see [SECURITY.md](SECURITY.md).

## Rebuilding the environment from scratch

Requirements: Python 3.11+, Docker Desktop (WSL2 on Windows), git, **at least 40 GB free disk**,
**about 10 GB RAM for WSL2/Docker** (the OSM import ran out of memory at the default limit; see the
`.wslconfig` example in `motis/DE-FULL-CITY-GTFS-NOTES.md`). Downloads are several GB (Poland + NRW OSM;
full Germany is ~7 GB and only used by the `docker-compose.de-full*.yml` variants).

1. `python -m venv venv`, activate it, `pip install -r requirements.txt` (`requirements-dev.txt` for tests).
2. `python scripts/fetch_data.py` downloads the GTFS feeds and OSM extracts into `data/`
   (sources and licences: [DATA_SOURCES.md](DATA_SOURCES.md)). If a URL stops working, update it there and in the script.
3. `scripts/merge_osm.sh` merges the Poland and NRW extracts into `data/osm/poland-nrw-latest.osm.pbf`,
   which `motis/config.yml` expects (needs `osmium-tool` or Docker; the Docker variant was verified on Windows on 2026-11-12, ~8 min, 3.06 GB output).
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

## Verified end to end (2026-11-12)

A clean clone on Windows (Docker 28.1.1, Python 3.13) went through: `pytest -q` (2091 passed), `scripts/fetch_data.py`
(MD5 and GTFS validation OK), `merge_osm.sh` via Docker (`iboates/osmium`, ~8 min, 3.06 GB), the MOTIS import
(~2.3 GB of index files plus `osr`/`adr`), the server, and a Warsaw → Kraków query (5 itineraries).

The production-like variant below was also verified on 2026-11-12 on the same machine: `fetch_data_extended.py`
(Germany OSM 4.88 GB, HVV 40 MB, MVV 19 MB, VRS 29 MB), the OSM merge via Docker (`poland-germany-latest.osm.pbf`,
7.05 GB), the MOTIS import into the volume `multimodal-fare-planner_motis-data-pl-cities`, the server on port 8082,
route queries Warsaw → Kraków, Hamburg → Berlin and Cologne → Munich (5 itineraries each), and one manual search in the
Streamlit UI (`MOTIS_BASE_URL=http://localhost:8082`). Disk use: free space dropped from 45.7 GB to 27.3 GB after the import
(about 40 GB peak while the downloads and the merged file coexist, so keep at least 45 GB free).
Not verified: creating the `motis-main` container and `refresh_prod.ps1` on a clean machine.

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
`scripts\refresh_prod.ps1` only refreshes an EXISTING container named `motis-main` (it fails if there is none). To create it
once from the volume imported above (not verified on a clean machine):

```
docker run -d --name motis-main --restart unless-stopped -p 8080:8080 `
  -v multimodal-fare-planner_motis-data-pl-cities:/data `
  -v "${PWD}\motis\config.pl-cities.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis@sha256:594eff881d4319549387563a28dffb2ac48650df5422325a44a6c2f69f79e9b9
```

Later refreshes: `scripts\refresh_prod.ps1` (see `scripts/README-refresh.md`).

## End-to-end check on a clean machine

1. Fresh folder: `git clone <repo>`, `cd` into it, `python -m venv .venv`, activate, `pip install -r requirements.txt -r requirements-dev.txt`.
2. `pytest -q` (no Docker needed; 2091 passed on Windows/Python 3.13 and 2079 passed + 12 skipped on Linux; the count varies by platform).
3. `python scripts/fetch_data.py` then `bash scripts/merge_osm.sh` (default NRW variant).
4. Clean Docker state for the test: `docker volume ls` should not list this project's volume (`<folder>_motis-data`); then `scripts\run_motis.ps1 import`.
5. `scripts\run_motis.ps1 server` (port 8080; stop any other container using it).
6. One route query with a date inside the feed validity window: `python demo.py --from "Lublin Dworzec Główny" --to "Gelsenkirchen Hbf" --date <date within the next week> --age 25`.
7. Optional: `python -m streamlit run app.py` and `uvicorn api.main:app --port 8010`.
8. If all of the above works, nothing from the original machine is needed.

## Troubleshooting

- **Port 8080 already in use:** the first `docker compose up` then leaves the container without a published port.
  Free the port (`docker ps`, `docker stop <container>`) and run `docker compose up -d --force-recreate motis`.
  `scripts\run_motis.ps1 server` now refuses to start when port 8080 is taken.
- **`/data/config.yml` is 0 bytes inside the Docker volume:** expected. The real file is bind-mounted over an empty
  placeholder file that Docker creates in the volume; the container reads the mounted one.
- **Out of memory during import:** raise the WSL2 limit (about 10 GB, see `motis/DE-FULL-CITY-GTFS-NOTES.md`).

## Repository map

`routing/` MOTIS client and itinerary building · `fares/` fare calculators and data · `attractions/`
attractions and city cards · `places/` place aliases and selection · `flights/` flight prices ·
`api/` FastAPI service · `app.py` Streamlit UI (PL/EN/DE/ES/FR/NL) · `i18n/` UI texts · `motis/` engine
config and notes · `scripts/` data and refresh tooling · `tests/` pytest suite · `research/`,
`verification/` source audits and verification notes (Polish).

The detailed technical documentation (sessions 1–7, API, fares, architecture) is in
[README.pl.md](README.pl.md) (Polish).
