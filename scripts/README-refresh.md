English | Polski: [wersja polska](README-refresh.pl.md)

# Refreshing production data (GTFS)—instructions without AI assistance

Script: `scripts\refresh_prod.ps1`. It does everything automatically and **deletes nothing**. On failure it returns to the previous version.

## Before you start
1. Start Docker Desktop and wait until it is "running".
2. Check that `motis-main` is running: `docker ps` (it should use port 8080 and the page should work).
3. Free disk space: at least 40 GB (the script checks this and stops if there is less).

## Running
```powershell
cd "<katalog-projektu>"
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1
```
It usually takes from several dozen minutes to over an hour (import). Do not close the window. The log is also written to `data\logs\refresh_prod-<data>.log`.

For a safe first run (everything except switching production), add `-NoSwitch`.

## Faster mode: `-SeedFromProd` (NOT LIVE-VERIFIED)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -SeedFromProd
```
Before importing, it copies the current production data to a new volume (production is mounted read-only and is not changed). The idea is that, with the same MOTIS OSM file, MOTIS skips the longest stages (`osr`, `adr`) and mainly recalculates timetables. This is inferred from logs and has not yet been live-tested; if it does not help, the import still runs, only for longer.
- Do this when **nobody is searching for routes** (copying files while they are being written could produce an inconsistent copy).
- The script runs `docker pull alpine:3`; if it fails (no internet), run `docker pull alpine:3` manually or run without `-SeedFromProd`.
- It requires additional disk space (a copy of the entire production volume) and downloading the small `alpine:3` image.

## Switching a ready volume: `-SwitchOnly` (without importing again)
When a run with `-NoSwitch` has completed and you have tested volume `mw_motis_refresh_<data>`:
```powershell
docker volume ls     # znajdź nazwę wolumenu mw_motis_refresh_...
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -SwitchOnly -Volume mw_motis_refresh_20261012-1606
```
The script checks that the volume exists and is not the current production volume, **blocks the switch** if any GTFS feed, OSM file, or config is newer than the volume (the data could be mismatched), checks feed freshness, tests the volume on port 8083, and only then replaces production (`motis-main` → `motis-main-old`) and tests port 8080. If the post-switch test fails, it returns to the old version automatically. The safeguard uses file modification times (not hashes), so downloading the same files again also blocks the switch; in that case, perform a normal run.

## What it does (in order)
1. Checks Docker, disk space, and whether production is alive.
2. Downloads feeds and checks freshness (at least 3 days).
3. Imports into a NEW volume `mw_motis_refresh_<data>`.
4. Runs a test on port 8083 (Warsaw, Kraków, Hamburg, Lublin → Gelsenkirchen route).
5. Stops `motis-main`, renames it to `motis-main-old`, and starts the new `motis-main` on port 8080.
6. Repeats the tests on port 8080. If one fails, it **automatically returns** to the old version.

Green `READY` = everything works. Red `ERROR` = read the message; the script has already protected the production state.

## Files this script does NOT refresh

`scripts\fetch_data.py` downloads only the domestic/NRW feeds and Warsaw/Kraków. The script checks that these files exist and stops with a clear error BEFORE downloading/importing if any is missing—but it does not know how to download/refresh them:
- `data\osm\poland-germany-latest.osm.pbf` (merged Poland and all-Germany OSM)
- `data\gtfs\de\hvv.zip` (Hamburg), `mvv.zip` (Munich), `vrs.zip` (Cologne/Bonn)

These files must be supplied/refreshed manually (the same way they were originally created—see `motis\PL-CITIES-GTFS-NOTES.md`). These three cities' GTFS feeds also expire over time like the rest—`scripts\check_gtfs_freshness.py` (called by this script) sees and warns about them, but nobody refreshes them automatically.

## What you must NEVER do manually
- Do not delete volumes: `plcities-test_motis-data-pl-cities` (current production), `amazing-sammet-2e5029_motis-data-de-full` (rollback), `multimodalnawyszukiwarka_motis-data-de-full-city-gtfs`, `multimodalnawyszukiwarka_motis-data`.
- Do not run `docker volume prune` or `docker system prune`.
- Delete old `mw_motis_refresh_*` volumes and the `motis-main-old` container only after several days of stable operation.

## Manual rollback (if the script fails halfway)
```powershell
docker ps -a                       # zobacz, jakie kontenery motis-* istnieją
docker stop motis-main             # jeśli stoi nowy, zepsuty
docker rename motis-main motis-main-zepsuty
docker rename motis-main-old motis-main
docker update --restart unless-stopped motis-main
docker start motis-main
```
Then wait about a minute and check `http://localhost:8080`. If there is no `motis-main-old` container, look for `motis-main-old-<data>` (`docker ps -a`).

## Common problems
- "Not enough space"—free disk space and run again. Nothing was changed.
- "Container motis-refresh-test already exists"—left over from an interrupted test: `docker rm -f motis-refresh-test`.
- Import fails with OOM—raise the WSL2 memory limit in `%USERPROFILE%\.wslconfig` (`memory=12GB`), run `wsl --shutdown`, start Docker, and run the script again.
- Feed expires too soon—the source has not published a fresh version; try later.
