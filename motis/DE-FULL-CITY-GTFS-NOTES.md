English | Polski: [wersja polska](DE-FULL-CITY-GTFS-NOTES.pl.md)

# Local HVV/MVV/VRS public transport in MOTIS—to be done by RC on the PC

Status: **PREPARED, NOT EXECUTED**. This container (cloud session) cannot access
your Docker or the `mvv-muenchen.de`/`vrsinfo.de`/`mobilitydatabase.org` hosts—
the download and `docker compose`/`docker run` must be performed by a Remote
Control session on your PC. The ready-to-paste commands below are in order.
Nothing here has been run yet.

Continuation of PR #46 (all-Germany OSM, `motis-main` on port 8080)—**OSM
remains unchanged**; we only add 3 new GTFS files for local transport in
Hamburg, Munich, and Cologne/Bonn, so that the `fares/hvv.py`/`mvv.py`/`kvb.py`
calculators (PR #42, #49) have real routes to price, not only a fixed price
without a segment.

## 0. Where the files come from and their licences (research, see project memory)

| Network | URL | Licence | Size (ZIP / unpacked) |
|---|---|---|---|
| HVV (Hamburg) | https://files.mobilitydatabase.org/mdb-3362/mdb-3362-202607201528/mdb-3362-202607201528.zip | **DL-DE-BY-2.0** (https://www.govdata.de/dl-de/by-2-0)—attribution is sufficient | ~38-41 MB / ~275-280 MB |
| MVV (Munich) | https://www.mvv-muenchen.de/fileadmin/mediapool/developer/opendata/gesamt_gtfs.zip | **CC BY 4.0** | not disclosed |
| VRS (Cologne/Bonn, also includes SPNV) | http://download.vrsinfo.de/gtfs/GTFS_VRS_mit_SPNV.zip | **CC BY 4.0** | not disclosed |

Attribution to add to the README/application footer (if not already present—check
`fares/README.md`/`attractions/README.md` for an attribution section):

```
Dane GTFS: Hamburger Verkehrsverbund GmbH (HVV), licencja DL-DE-BY-2.0 — https://www.govdata.de/dl-de/by-2-0
Dane GTFS: Münchner Verkehrs- und Tarifverbund GmbH (MVV), licencja CC BY 4.0
Dane GTFS: Verkehrsverbund Rhein-Sieg GmbH (VRS), licencja CC BY 4.0
```

HVV and MVV are updated occasionally (monthly), VRS **every night**—if this
becomes permanent, automate VRS downloads eventually (outside this PR's scope).

## 1. Downloading the 3 GTFS files (PowerShell, from the main checkout directory)

```powershell
cd "<katalog-projektu>"
New-Item -ItemType Directory -Force -Path data\gtfs\de | Out-Null

Invoke-WebRequest -Uri "https://files.mobilitydatabase.org/mdb-3362/mdb-3362-202607201528/mdb-3362-202607201528.zip" -OutFile "data\gtfs\de\hvv.zip"
Invoke-WebRequest -Uri "https://www.mvv-muenchen.de/fileadmin/mediapool/developer/opendata/gesamt_gtfs.zip" -OutFile "data\gtfs\de\mvv.zip"
Invoke-WebRequest -Uri "http://download.vrsinfo.de/gtfs/GTFS_VRS_mit_SPNV.zip" -OutFile "data\gtfs\de\vrs.zip"

Get-Item data\gtfs\de\hvv.zip, data\gtfs\de\mvv.zip, data\gtfs\de\vrs.zip | Select-Object Name, Length
```

If a URL fails (the provider sometimes changes the link): HVV has a stable
fallback at `https://mobilitydatabase.org/feeds/mdb-3362` (the page with a
"Download" link); MVV and VRS have operator pages
(`mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/opendata/`,
`vrsinfo.de/fahrplan/oepnv-daten-fuer-webentwickler.html`) where the current
link is always available.

## 2. Import into a NEW volume (separate port 8082—not the `motis-main` on 8080)

OSM is already on disk (`data/osm/poland-germany-latest.osm.pbf`, merged in
PR #46)—this import does **not** need to be repeated; only add the 3 new GTFS
datasets to the config. The new config
(`motis/config.de-full-city-gtfs.yml`) and compose file
(`docker-compose.de-full-city-gtfs.yml`) are already in the repository (this PR).

```powershell
cd "<katalog-projektu>"
docker compose -f docker-compose.de-full-city-gtfs.yml --profile import-city-gtfs run --rm motis-import-city-gtfs
```

**Memory requirement**—an estimate, NOT measured (this container cannot access
your Docker): the WSL2 limit is already raised to **10 GB** (PR #46). The
PL+DE serving container alone (without cities) used ~5,3 GB (~4,1 GB spare).
The 3 new GTFS files total ~40-100 MB compressed—much smaller than all-Germany
OSM (7 GB input)—so the import will **probably fit in 10 GB**, but the earlier
OSM import failed with OOM at the default limit, so **watch `docker stats`
during import**. If it fails with OOM:
```
# %USERPROFILE%\.wslconfig
[wsl2]
memory=12GB
```
then run `wsl --shutdown`, restart Docker Desktop, and repeat the import. After
the import, the limit can return to 10 GB (serving should use about the same,
possibly slightly more—three extra feed indexes in RAM, but far less data than
OSM).

## 3. Parallel test on port 8082 (does NOT touch production 8080)

```powershell
docker compose -f docker-compose.de-full-city-gtfs.yml up -d motis-city-gtfs
```

Check in a browser/curl that the server starts:
```powershell
curl http://localhost:8082/api/v1/geocode?text=Hauptbahnhof+Hamburg
```

**The test that actually matters** (I could not do this from the current
session—live MOTIS is required): a route with a local segment in each of the
three cities, for example through `demo.py`/`app.py` pointed at port 8082, or
directly through the MOTIS API:
- Hamburg: `Hauptbahnhof Hamburg` → `Landungsbrücken` (short local HVV segment)
- Munich: `Marienplatz München` → `Hauptbahnhof München` (MVV)
- Cologne: `Köln Hauptbahnhof` → `Köln Deutz` (VRS/KVB)

Check that the returned route has `agencyName`/stop names containing "HVV"/"Hamburg",
"MVV"/"München", or "VRS"/"Köln"—`routing/pricing.py::price_bus_leg()` (around
lines ~353-366) matches these keywords (already loaded, PR #42/#49; no code
change is needed), so if the names match, the price should come from the
HVV/MVV/kvb.py calculator rather than the fallback. If matching fails (the
data uses different names from the assumed keywords), extend
`HVV_KEYWORDS`/`MVV_KEYWORDS`/`VRS_KOLN_KEYWORDS` in `routing/pricing.py` with
the actual names—this can only be determined from a real MOTIS response, so a
live Docker session must perform this step.

## 4. Switching to production port 8080—DONE (2026-10-10)

Status: **DONE by Ksavi through RC, verified**—`motis-main` on port 8080 serves
data from volume `multimodalnawyszukiwarka_motis-data-de-full-city-gtfs` (the
volume name with the `docker compose` project prefix, not
`motis-data-de-full-city-gtfs` as in the bare `docker run` below—if reproducing
manually without compose, check `docker volume ls` and use the exact name shown).
Hamburg geocoding at `http://localhost:8080` was confirmed (the first curl after
startup returned "Empty reply from server"—the server was still warming up/loading
indexes; a second curl a few seconds later worked normally—this is startup time,
not an error).

Analogously to the PL+NRW -> PL+DE switch in PR #46:

```powershell
docker stop motis-city-gtfs   # albo nazwa z `docker compose ps`, np. multimodalnawyszukiwarka-motis-city-gtfs-1
docker rm motis-city-gtfs
docker stop motis-main
docker run -d --name motis-main -p 8080:8080 `
  -v multimodalnawyszukiwarka_motis-data-de-full-city-gtfs:/data `
  -v "<katalog-projektu>\motis\config.de-full-city-gtfs.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
docker update --restart unless-stopped motis-main
```

The old container/volume `motis-main`+`amazing-sammet-2e5029_motis-data-de-full`
(PL+DE **without** cities) is **not deleted**—it remains as a backup/rollback,
as in the earlier PL+NRW→PL+DE switch.

## 5. Rollback (if something does not work)

```powershell
docker stop motis-main
docker rm motis-main
docker run -d --name motis-main -p 8080:8080 `
  -v amazing-sammet-2e5029_motis-data-de-full:/data `
  -v "<katalog-projektu>\motis\config.de-full.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
docker update --restart unless-stopped motis-main
```

## What this change does NOT cover (RC must still verify)

- Downloading the files, import, routing test, and switch—**DONE** by Ksavi through RC
  (2026-10-10); steps 1–4 passed and production on 8080 runs with new HVV/MVV/VRS data.
- MVV M-6/M-12 zone prices (see PR #49, `verification/hvv-mvv-vrs-ulgi-transport-2026-10-10.md`)—independent of this task and still awaiting browser confirmation.
- Keyword matching in `routing/pricing.py` **WORKED** on real data (test
  `scripts/test_local_transit_hvv_mvv_vrs.py` on port 8082, all 3 cities
  `oficjalna_taryfa`)—no code fix needed.
