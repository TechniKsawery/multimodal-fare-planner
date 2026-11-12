# Uruchamia silnik routingu MOTIS (motis-project/motis) na feedach GTFS+OSM z data/.
# Dane wyjsciowe (motis/data) trzymane sa w nazwanym wolumenie Dockera, nie w
# bind moncie -- patrz komentarz w docker-compose.yml (resize error na Windows).
# Uzycie: scripts\run_motis.ps1 import   -- zbuduj dane
#         scripts\run_motis.ps1 server   -- uruchom serwer HTTP na porcie 8080
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("import", "server")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

switch ($Mode) {
    "import" {
        docker compose --profile import run --rm motis-import
    }
    "server" {
        # Port 8080 zajety = kontener startuje bez opublikowanego portu (trzeba by go odtwarzac); lepiej przerwac.
        if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
            throw "Port 8080 jest zajety. Zatrzymaj proces/kontener, ktory go uzywa (docker ps; docker stop <nazwa>), i uruchom ponownie."
        }
        docker compose up motis
    }
}
