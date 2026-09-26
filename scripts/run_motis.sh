#!/usr/bin/env bash
# Uruchamia silnik routingu MOTIS (motis-project/motis) na feedach GTFS z data/.
# Użycie: scripts/run_motis.sh import   -- zbuduj dane (config.yml -> motis/data/)
#         scripts/run_motis.sh server   -- uruchom serwer HTTP na porcie 8080
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  import)
    mkdir -p motis/data
    cp motis/config.yml motis/data/config.yml
    docker compose --profile import run --rm motis-import
    ;;
  server)
    docker compose up motis
    ;;
  *)
    echo "Użycie: $0 {import|server}" >&2
    exit 1
    ;;
esac
