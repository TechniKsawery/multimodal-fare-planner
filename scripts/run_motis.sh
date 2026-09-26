#!/usr/bin/env bash
# Uruchamia silnik routingu MOTIS (motis-project/motis) na feedach GTFS+OSM z data/.
# Dane wyjściowe (motis/data) trzymane są w nazwanym wolumenie Dockera, nie w
# bind moncie — patrz komentarz w docker-compose.yml (resize error na Windows).
# Użycie: scripts/run_motis.sh import   -- zbuduj dane
#         scripts/run_motis.sh server   -- uruchom serwer HTTP na porcie 8080
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  import)
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
