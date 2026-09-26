# Uruchamia silnik routingu MOTIS (motis-project/motis) na feedach GTFS z data/.
# Uzycie: scripts\run_motis.ps1 import   -- zbuduj dane (config.yml -> motis/data/)
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
        New-Item -ItemType Directory -Force -Path "motis\data" | Out-Null
        Copy-Item "motis\config.yml" "motis\data\config.yml" -Force
        docker compose --profile import run --rm motis-import
    }
    "server" {
        docker compose up motis
    }
}
