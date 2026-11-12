#!/usr/bin/env bash
# Skleja pliki OSM w jeden (MOTIS przyjmuje tylko jeden plik `osm:` w konfiguracji):
#   scripts/merge_osm.sh          -> data/osm/poland-nrw-latest.osm.pbf (dla motis/config.yml;
#                                    po `python scripts/fetch_data.py`)
#   scripts/merge_osm.sh germany  -> data/osm/poland-germany-latest.osm.pbf (dla config.pl-cities.yml /
#                                    config.de-full*.yml; po `python scripts/fetch_data_extended.py`) Wymaga osmium-tool (https://osmcode.org/osmium-tool/)
# albo Dockera. Wariant z Dockerem (obraz iboates/osmium) sprawdzony na Windows 2026-11-12 (wariant domyślny, NRW).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "germany" ]; then SECOND=germany-latest.osm.pbf; OUTF=poland-germany-latest.osm.pbf
else SECOND=nordrhein-westfalen-latest.osm.pbf; OUTF=poland-nrw-latest.osm.pbf; fi
OUT=data/osm/$OUTF
if command -v osmium >/dev/null 2>&1; then
  osmium merge data/osm/poland-latest.osm.pbf "data/osm/$SECOND" -o "$OUT" --overwrite
else
  docker run --rm -v "$PWD/data/osm:/osm" iboates/osmium:latest \
    merge /osm/poland-latest.osm.pbf "/osm/$SECOND" -o "/osm/$OUTF" --overwrite
fi
echo "Zapisano $OUT"
