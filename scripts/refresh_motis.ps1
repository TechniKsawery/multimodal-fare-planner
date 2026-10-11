# Odświeżenie feedów GTFS i import do NOWEGO wolumenu testowego (port 8082). NIE przełącza produkcji.
# Uruchamiać ręcznie lub z Harmonogramu zadań Windows (np. co tydzień, czwartek 06:00):
#   schtasks /Create /SC WEEKLY /D THU /ST 06:00 /TN MW-refresh /TR "powershell -File <repo>\scripts\refresh_motis.ps1"
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python scripts\fetch_data.py
python scripts\check_gtfs_freshness.py --min-days 3
docker compose -f docker-compose.pl-cities.yml --profile import-pl-cities run --rm motis-import-pl-cities
docker compose -f docker-compose.pl-cities.yml up -d motis-pl-cities
Write-Host "Gotowe: test na http://localhost:8082. Przełączenie produkcji (8080) tylko po zgodzie."
