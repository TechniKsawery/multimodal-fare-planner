English | Polski: [wersja polska](PL-CITIES-GTFS-NOTES.pl.md)

# Warsaw and Kraków (local GTFS) in MOTIS + feed refresh

Status: **configuration prepared; import and live test are performed by the Remote Control session** (the cloud container blocks `mkuran.pl`/`gtfs.ztp.krakow.pl`, checked 2026-10-11: proxy 403). Production (`multimodalnawyszukiwarka_motis-data-de-full-city-gtfs`, port 8080) and rollback are untouched. Test: separate volume `motis-data-pl-cities`, port 8082.

## Sources (checked 2026-10-11)

| City | File | Licence | Notes |
|---|---|---|---|
| Warsaw | https://mkuran.pl/gtfs/warsaw.zip | ZTM Warsaw terms + ODbL for bus shapes (https://mkuran.pl/gtfs/) | Attribution required: ZTM Warsaw, Mikołaj Kuranowski, OpenStreetMap contributors (see `attributions.txt` in the zip). Update frequency not stated. |
| Kraków | https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip, `_M.zip`, `_T.zip` | **UNKNOWN**—the ZTP site does not state a licence; Mobility Database only points to https://ztp.krakow.pl | Meaning of A/M/T not confirmed (A = bus according to Mobility Database mdb-1326). Files updated 2026-10-08/10-11. |

**For Ksaviy to decide:** Kraków's licence is unconfirmed. Until the ZTP terms are checked (or ZTP is asked), the feed is for testing only, not production.

Attribution for README/footer: `Dane GTFS Warszawa: ZTM Warszawa, przetworzone przez M. Kuranowskiego (mkuran.pl), shapes © współtwórcy OpenStreetMap (ODbL).`

## Running the test (PC, PowerShell)

```powershell
python scripts\fetch_data.py          # dociąga warsaw do data\gtfs\pl; Kraków tylko z: python scripts\fetch_data_extended.py --krakow (config.pl-cities-krakow-test.yml)
docker compose -f docker-compose.pl-cities.yml --profile import-pl-cities run --rm motis-import-pl-cities
docker compose -f docker-compose.pl-cities.yml up -d motis-pl-cities
```
Watch disk space on C: (about 12 GB free) and import memory (`docker stats`).

## Refresh

- `.github/workflows/gtfs_freshness.yml`—daily downloads all feeds using `scripts/fetch_data.py`, calculates freshness (`scripts/check_gtfs_freshness.py`), and opens/updates an issue labelled `gtfs-expiry` when a feed expires in <3 days or cannot be downloaded.
- `scripts/refresh_motis.ps1`—refreshes data and imports into the test volume; it can be scheduled in Windows Task Scheduler (command in the script header). Switch production only after approval.
- Free gtfs.de feeds are valid for 7 days, so refresh at least weekly.

## Kraków licence: what was checked (2026-10-11)

Nothing unambiguous about GTFS. Checked pages (without any GTFS licence clause): https://gtfs.ztp.krakow.pl/ , https://ztp.krakow.pl/dane-otwarte (only footer “© 2021–2026 ZTP Kraków”), https://ztpk-gmk-2.hub.arcgis.com/ (ArcGIS Hub, no licence text), announcement https://convention.krakow.pl/english/news/284578,2357,komunikat,_bus_stops__bicycle_infrastructure_and_p+r_sites___open_data_published_by_the_public_transport_authority.html (mentions GTFS and data for “analysis and research”, does not state a licence), and Mobility Database mdb-1326 (points to https://ztp.krakow.pl).
The only lead is the MSIP catalogue https://msip.krakow.pl/dataset/2963 (“ZTP - Komunikacja Miejska i Rowerowa”), which says “Use of the data in accordance with the MSIP regulations”—without naming a licence; the regulations themselves (Mayor's order, BIP: https://bip.krakow.pl/zarzadzenie/2025/1742/w_sprawie_zasad_funkcjonowania_Miejskiego_Systemu_Informacji_Przestrzennej_Miasta_Krakowa.html) were not read, and it is not certain that they cover GTFS. Transitland could not be read (robots).
Conclusion: licence and permission for commercial use are **UNCONFIRMED**. The next step is to ask ZTP.
