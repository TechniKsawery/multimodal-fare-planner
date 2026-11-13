English | Polski: [wersja polska](DE-FULL-NOTES.pl.md)

# All-Germany OSM—imported and joined into one system (port 8080)

Status: **imported, tested, and joined into one system**. Port
8080 now serves PL+DE (container `motis-main`). The old `motis-data` volume
(PL+NRW) is retained as a backup/rollback and was not deleted.

## What was done

1. Downloaded `poland-latest.osm.pbf` + `germany-latest.osm.pbf` from Geofabrik
   (at the same time, to avoid border node conflicts) into
   `data/osm/`.
2. Merged them with `osmium merge` → `data/osm/poland-germany-latest.osm.pbf`
   (7,0 GB). The original PL/DE files were **deleted** separately after merging
   (they are no longer needed; the merge is deterministic—if necessary, they
   can be downloaded and merged again).
3. Imported into a separate Docker volume (`amazing-sammet-2e5029_motis-data-de-full`,
   13,6 GB) using `docker-compose.de-full.yml` + `motis/config.de-full.yml`,
   first in parallel on port 8081, leaving the old demo on 8080 untouched.
4. The import required increasing Docker/WSL2 RAM limits—see below.
5. After confirming that it worked (tests below), **joined it into one system**:
   - stopped the old container `multimodalnawyszukiwarka-motis-1` (volume
     `motis-data` with PL+NRW **retained**, not deleted—it is the backup),
   - removed the experimental container on port 8081 (its volume,
     `amazing-sammet-2e5029_motis-data-de-full`, **was retained**),
   - started the new container `motis-main` on port **8080**, using the same
     volume as above:
     ```powershell
     docker run -d --name motis-main -p 8080:8080 `
       -v amazing-sammet-2e5029_motis-data-de-full:/data `
       -v "<ścieżka repo>\motis\config.de-full.yml:/data/config.yml:ro" `
       ghcr.io/motis-project/motis:latest
     ```
   - re-verified on 8080 (addresses, Warsaw → Berlin route).

## Important: Docker RAM limit

The import **failed with OOM** at the default WSL2 limit (7,18 GB—half of this
host's RAM, ~14,8 GB; nobody configured it deliberately). It was raised to
**10 GB** in `%USERPROFILE%\.wslconfig`:

```
[wsl2]
memory=10GB
```

**Leave it this way for now.** A single container (after joining, with no second
one alongside it) uses ~5,3 GB—4,1 GB remains within the 10 GB limit, with zero
risk. The limit is only a ceiling (not a reservation), so it costs nothing at
current usage. Lowering it would require another WSL/Docker restart without
any real benefit.

**To return to Docker's default limit** (if necessary):
```
del %USERPROFILE%\.wslconfig
wsl --shutdown
```
(then start Docker Desktop normally and start `motis-main` manually—see below).

## Note: `motis-main` has no restart policy

The container was started with ordinary `docker run` without `--restart`, so
**after a Windows/Docker/WSL restart it must be started manually again**:
```
docker start motis-main
```
(the container and its data remain; nothing needs rebuilding). To automate this
permanently: `docker update --restart unless-stopped motis-main`.

## Returning to PL+NRW only (rollback)

The old volume (`motis-data`, PL+NRW data) was not deleted. To restore the old
demo on 8080:
```
docker stop motis-main
docker run -d --name motis-1 -p 8080:8080 `
  -v multimodalnawyszukiwarka_motis-data:/data `
  -v "<ścieżka repo>\motis\config.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
```
(or simply `docker compose up -d motis` from the main checkout, if
`docker-compose.yml` there still points to volume `motis-data`).

## Tests that passed

- Address geocoding (not just station names) outside NRW: `Reeperbahn 1
  Hamburg`, `Buerer Straße 8 Gelsenkirchen`, `Skubiszewskiego 22 Lublin`—
  all return `type: ADDRESS` with correct coordinates. The old demo (PL+NRW)
  returned at most a guess based on the nearest station name for addresses
  outside PL+NRW (`type: STOP`), not a real address.
- Warsaw → Berlin route (by address/city name): works, ~5h40m,
  Warsaw Centralna → Berlin-Lichtenberg + metro.
- Full demo route Skubiszewskiego 22 Lublin → Buerer Straße 8
  Gelsenkirchen through Streamlit (`app.py`): **17 variants built** (on the old
  OSM, a route for the destination address could not be built at all). The 4
  skipped variants are unrelated to OSM (physically impossible transfer,
  missing Travelpayouts token for flights).
- Everything above was verified twice: first on port 8081 (parallel test), then
  again on 8080 after joining into one system (same data, different
  port/container).

## Not yet checked

- Prices/discounts (PR #44/#45: PKP, BahnCard, VRR, etc.) on the new data—the
  application logic did not change and should work identically, but it was not
  clicked through manually.
- Flights / FlixBus on the new data.

## Files

- `docker-compose.de-full.yml`—compose file used for import (import +
  experimental server on 8081, no longer used but retained for
  inspection/repeating the import)
- `motis/config.de-full.yml`—config pointing to the merged OSM file, now used
  by `motis-main`
- `data/osm/poland-germany-latest.osm.pbf`—merged input data (outside git,
  `.gitignore` excludes `/data/`)
