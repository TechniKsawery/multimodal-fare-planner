"""Dociąga dane wymagane przez wariant "produkcyjny" (motis/config.pl-cities.yml, docker-compose.pl-cities.yml,
scripts/refresh_prod.ps1), których NIE pobiera scripts/fetch_data.py:
  - OSM całych Niemiec (Geofabrik) -> data/osm/germany-latest.osm.pbf (potem: scripts/merge_osm.sh germany
    skleja z poland-latest.osm.pbf w data/osm/poland-germany-latest.osm.pbf, ok. 7 GB),
  - GTFS HVV (Hamburg), MVV (Monachium), VRS (Kolonia/Bonn) -> data/gtfs/de/{hvv,mvv,vrs}.zip.

Uruchomienie (po `python scripts/fetch_data.py`):  python scripts/fetch_data_extended.py [--krakow] [katalog_data]
  --krakow: dodatkowo GTFS ZTP Kraków (licencja NIEPOTWIERDZONA, tylko test lokalny, bez redystrybucji);
  używa motis/config.pl-cities-krakow-test.yml zamiast config.pl-cities.yml.
Licencje: HVV = DL-DE-BY-2.0, MVV i VRS = CC BY 4.0 (zob. DATA_SOURCES.md, motis/DE-FULL-CITY-GTFS-NOTES.md).
UWAGA: adres HVV wskazuje migawkę z mobilitydatabase z 2026-07-20 i może przestać działać; wtedy znajdź
aktualny feed HVV (np. na https://mobilithek.info lub https://mobilitydatabase.org) i podmień URL poniżej.
"""
import sys
from pathlib import Path

KRAKOW = {
    "gtfs/pl/krakow_a.zip": "https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip",
    "gtfs/pl/krakow_m.zip": "https://gtfs.ztp.krakow.pl/GTFS_KRK_M.zip",
    "gtfs/pl/krakow_t.zip": "https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip",
}
WITH_KRAKOW = "--krakow" in sys.argv
if WITH_KRAKOW:
    sys.argv.remove("--krakow")

sys.path.insert(0, str(Path(__file__).parent))
import fetch_data  # noqa: E402

EXTRA = {
    "osm/germany-latest.osm.pbf": "https://download.geofabrik.de/europe/germany-latest.osm.pbf",
    "gtfs/de/hvv.zip": "https://files.mobilitydatabase.org/mdb-3362/mdb-3362-202607201528/mdb-3362-202607201528.zip",
    "gtfs/de/mvv.zip": "https://www.mvv-muenchen.de/fileadmin/mediapool/developer/opendata/gesamt_gtfs.zip",
    "gtfs/de/vrs.zip": "http://download.vrsinfo.de/gtfs/GTFS_VRS_mit_SPNV.zip",
}

if __name__ == "__main__":
    for rel, url in {**EXTRA, **(KRAKOW if WITH_KRAKOW else {})}.items():
        fetch_data.download(url, fetch_data.DATA / rel)
    print("\nGotowe. Dalej: bash scripts/merge_osm.sh germany")
