#!/usr/bin/env bash
# Skleja data/osm/poland-latest.osm.pbf i data/osm/nordrhein-westfalen-latest.osm.pbf w
# data/osm/poland-nrw-latest.osm.pbf (motis/config.yml przyjmuje tylko jeden plik OSM).
# Uruchom po `python scripts/fetch_data.py`. Wymaga osmium-tool (https://osmcode.org/osmium-tool/)
# albo Dockera. UWAGA: wariant z Dockerem (obraz iboates/osmium) NIE był sprawdzony na żywo.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/osm/poland-nrw-latest.osm.pbf
if command -v osmium >/dev/null 2>&1; then
  osmium merge data/osm/poland-latest.osm.pbf data/osm/nordrhein-westfalen-latest.osm.pbf -o "$OUT" --overwrite
else
  docker run --rm -v "$PWD/data/osm:/osm" iboates/osmium:latest \
    merge /osm/poland-latest.osm.pbf /osm/nordrhein-westfalen-latest.osm.pbf -o /osm/poland-nrw-latest.osm.pbf --overwrite
fi
echo "Zapisano $OUT"
