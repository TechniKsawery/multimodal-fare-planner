<#
.SYNOPSIS
  Bezpieczne odświeżenie feedów GTFS na produkcji (motis-main, port 8080) z automatycznym rollbackiem.

.DESCRIPTION
  Kroki: sprawdzenie miejsca i ważności feedów -> pobranie -> import do NOWEGO wolumenu ->
  test na osobnym porcie (domyślnie 8083) -> przełączenie (motis-main -> motis-main-old) ->
  sprawdzenie po przełączeniu -> przy błędzie automatyczny rollback.

  Gwarancje: skrypt przerywa na pierwszym błędzie. Nigdy nie wykonuje `docker volume rm/prune`,
  `docker system prune` ani nie kasuje kontenerów produkcyjnych/rollbackowych. Kasuje wyłącznie
  własny kontener testowy (motis-refresh-test) i ewentualnie świeżo utworzony, nieudany motis-main.
  Stare wolumeny (prod, rollback, poprzednie importy) zostają — sprzątanie robi człowiek.

.PARAMETER TestPort      Port kontenera testowego (domyślnie 8083; 8082 bywa zajęty przez stary test).
.PARAMETER MinFreeGB     Minimum wolnego miejsca na dysku z repo (domyślnie 40 GB).
.PARAMETER MinDays       Minimalna liczba dni ważności każdego feedu (domyślnie 3).
.PARAMETER SkipFetch     Pomiń pobieranie (użyj plików już leżących w data\).
.PARAMETER NoSwitch      Zrób wszystko do testu włącznie, ale NIE przełączaj produkcji.
.PARAMETER SeedFromProd  Przed importem skopiuj dane obecnej produkcji do nowego wolumenu (kopia TYLKO CZYTA prod:
                 wolumen prod jest montowany :ro). Przy tym samym pliku OSM MOTIS powinien pominac najdluzsze
                 etapy (osr, adr) i przeliczyc glownie rozklady. Dzialanie NIEZWERYFIKOWANE na zywo.
                 Uruchamiaj, gdy nikt nie szuka tras (kopia zywych plikow w trakcie zapisu mogla by byc niespojna).
.PARAMETER SwitchOnly    Bez pobierania i importu: przelacz prod na JUZ zaimportowany wolumen podany w -Volume.
                 Przed zamiana: walidacja wolumenu, sprawdzenie ze feedy/OSM/config nie zmienily sie od utworzenia
                 wolumenu, ponowny test na porcie testowym. Potem normalne kroki 4-5 z automatycznym rollbackiem.
.PARAMETER Volume        Nazwa wolumenu dla -SwitchOnly (musi miec prefiks mw_motis_refresh_).
.PARAMETER WarmupMinutes Ile minut czekać na start MOTIS (domyślnie 10).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -SwitchOnly -Volume mw_motis_refresh_20261012-1606
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1
  powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -NoSwitch
#>
[CmdletBinding()]
param(
    [int]$TestPort = 8083,
    [int]$MinFreeGB = 40,
    [int]$MinDays = 3,
    [switch]$SkipFetch,
    [switch]$NoSwitch,
    [switch]$SeedFromProd,
    [switch]$SwitchOnly,
    [string]$Volume = "",
    [int]$WarmupMinutes = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- stałe -----------------------------------------------------------------
$ProdName    = "motis-main"
$OldName     = "motis-main-old"
$TestName    = "motis-refresh-test"
$ProdPort    = 8080
$Image       = "ghcr.io/motis-project/motis:latest"
# Wolumeny, których skrypt nie rusza pod żadnym pozorem (informacyjnie + sprawdzenie, że nowy wolumen to nie one):
$Protected   = @(
    "plcities-test_motis-data-pl-cities",
    "amazing-sammet-2e5029_motis-data-de-full",
    "multimodalnawyszukiwarka_motis-data-de-full-city-gtfs",
    "multimodalnawyszukiwarka_motis-data"
)
$Repo        = Split-Path $PSScriptRoot -Parent
$ConfigFile  = Join-Path $Repo "motis\config.pl-cities.yml"
$Stamp       = Get-Date -Format "yyyyMMdd-HHmm"
$NewVolume   = "mw_motis_refresh_$Stamp"
$LogDir      = Join-Path $Repo "data\logs"

if ($SwitchOnly) {
    if (-not $Volume) { throw "-SwitchOnly wymaga -Volume <nazwa>." }
    if ($NoSwitch)    { throw "-SwitchOnly i -NoSwitch wykluczaja sie." }
    if ($SeedFromProd -or $SkipFetch) { throw "-SwitchOnly nie laczy sie z -SeedFromProd/-SkipFetch (nic nie pobiera ani nie importuje)." }
    $NewVolume = $Volume
}

Set-Location $Repo
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir "refresh_prod-$Stamp.log") | Out-Null

# --- pomocnicze ------------------------------------------------------------
function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Fail($msg) { throw $msg }

# Uruchamia program natywny i przerywa, gdy kod wyjścia != 0. Zwraca wyjście jako tekst.
function Run {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host "> $Exe $($Arguments -join ' ')" -ForegroundColor DarkGray
    # Windows PowerShell 5.1: stderr natywnego programu (np. "Unable to find image ... locally" od docker run)
    # przy $ErrorActionPreference = "Stop" konczy skrypt bledem mimo kodu wyjscia 0. O sukcesie decyduje
    # wylacznie kod wyjscia, wiec na czas wywolania przelaczamy na "Continue" (jak w TryRun).
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    if ($code -ne 0) { Fail "Komenda '$Exe $($Arguments -join ' ')' zwróciła kod $code`n$($out -join "`n")" }
    return ($out -join "`n")
}
# To samo, ale bez przerywania (do rollbacku i sprawdzania istnienia). Zwraca $true/$false.
# UWAGA: pod Windows PowerShell 5.1 (powershell.exe) kazda linia stderr z natywnego programu,
# przy globalnym $ErrorActionPreference = "Stop", przerywa wykonanie jako blad koncowy - NAWET
# gdy wynik jest przechwytywany do $null. Przez to TryRun (majacy z definicji NIGDY nie przerywac)
# rzucal wyjatkiem dla kazdego "nie istnieje" (np. VolumeExists nieistniejacego wolumenu), co
# lamalo caly wzorzec sprawdzania istnienia w tym skrypcie. Lokalne przelaczenie na "Continue"
# na czas samego wywolania (i przywrocenie w finally) naprawia to bez zmiany zachowania Run.
function TryRun {
    param([string]$Exe, [string[]]$Arguments)
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & $Exe @Arguments 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}
function ContainerExists($name) { TryRun "docker" @("container", "inspect", $name) }
function VolumeExists($name)    { TryRun "docker" @("volume", "inspect", $name) }

function Get-Json($url) {
    Invoke-RestMethod -Uri $url -TimeoutSec 60
}

# Czeka aż API odpowie na geokodowanie. Zwraca $true/$false.
function Wait-Motis([int]$Port, [int]$Minutes) {
    $deadline = (Get-Date).AddMinutes($Minutes)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Get-Json "http://localhost:$Port/api/v1/geocode?text=Warszawa"
            if ($null -ne $r) { return $true }
        } catch { }
        Start-Sleep -Seconds 10
    }
    return $false
}

# Zestaw testów dymnych na danym porcie. Rzuca wyjątek przy pierwszej porażce.
function Test-Motis([int]$Port) {
    $base = "http://localhost:$Port/api/v1"
    foreach ($q in @("Warszawa Centralna", "Kraków Główny", "Hamburg Hauptbahnhof")) {
        $r = @(Get-Json ("$base/geocode?text=" + [uri]::EscapeDataString($q)))
        if ($r.Count -lt 1) { Fail "Geokodowanie '$q' na porcie $Port nie zwróciło wyników." }
        Write-Host "  OK geokodowanie: $q ($($r.Count) wyników)"
    }
    # Demo: Lublin Główny -> Gelsenkirchen Hbf, jutro w południe (UTC).
    $time = (Get-Date).ToUniversalTime().Date.AddDays(1).AddHours(10).ToString("yyyy-MM-ddTHH:mm:ssZ")
    $url = "$base/plan?fromPlace=51.2318,22.5670&toPlace=51.5046,7.1022&time=$([uri]::EscapeDataString($time))&numItineraries=3"
    $p = Get-Json $url
    $n = @($p.itineraries).Count
    if ($n -lt 1) { Fail "Demo Lublin -> Gelsenkirchen na porcie $Port nie zwróciło żadnego połączenia." }
    Write-Host "  OK demo Lublin -> Gelsenkirchen ($n połączeń)"
}

function Start-Motis([string]$Name, [string]$Volume, [int]$HostPort, [switch]$Restart) {
    $a = @("run", "-d", "--name", $Name, "-p", "${HostPort}:8080",
           "-v", "${Volume}:/data",
           "-v", "${ConfigFile}:/data/config.yml:ro")
    if ($Restart) { $a += @("--restart", "unless-stopped") }
    $a += $Image
    $null = Run "docker" $a
}

# --- stan do rollbacku -----------------------------------------------------
$switched      = $false   # czy motis-main zostało już przemianowane
$renamedOldTo  = $null    # pod jaką nazwą zachowano poprzedni motis-main
$prevRestart   = "unless-stopped"

function Invoke-Rollback {
    Write-Host "`n!!! ROLLBACK: przywracam poprzedni $ProdName !!!" -ForegroundColor Red
    # Usuwamy WYŁĄCZNIE nowo utworzony kontener motis-main (nowy wolumen zostaje do diagnozy).
    # Kontener o nazwie motis-main kasujemy tylko, gdy stoi na NOWYM wolumenie (inaczej to jeszcze stara produkcja).
    if (ContainerExists $ProdName) {
        $mountsJson = (& docker inspect -f '{{json .Mounts}}' $ProdName 2>$null) -join ""
        $vol = [string](try { $mounts2 = $mountsJson | ConvertFrom-Json; ($mounts2 | Where-Object { $_.Destination -eq "/data" } | Select-Object -First 1 -ExpandProperty Name) } catch { "" })
        if ($vol.Trim() -eq $NewVolume) {
            $null = TryRun "docker" @("stop", $ProdName)
            $null = TryRun "docker" @("rm", $ProdName)
        }
    }
    if ((ContainerExists $ProdName)) {
        # stara produkcja nie została przemianowana — wystarczy ją uruchomić
        $null = TryRun "docker" @("start", $ProdName)
        if (Wait-Motis $ProdPort 10) { Write-Host "Rollback zakończony: $ProdName działa." -ForegroundColor Yellow }
        else { Write-Host "!!! $ProdName nie odpowiada — docker logs $ProdName" -ForegroundColor Red }
    } elseif ($renamedOldTo -and (ContainerExists $renamedOldTo)) {
        $null = TryRun "docker" @("rename", $renamedOldTo, $ProdName)
        $null = TryRun "docker" @("update", "--restart", $prevRestart, $ProdName)
        if (-not (TryRun "docker" @("start", $ProdName))) {
            Write-Host "!!! Nie udało się wystartować poprzedniego $ProdName — zrób to ręcznie: docker start $ProdName" -ForegroundColor Red
        } elseif (Wait-Motis $ProdPort 10) {
            Write-Host "Rollback zakończony: poprzedni $ProdName działa na porcie $ProdPort." -ForegroundColor Yellow
        } else {
            Write-Host "!!! Poprzedni $ProdName wystartował, ale nie odpowiada — sprawdź: docker logs $ProdName" -ForegroundColor Red
        }
    } else {
        Write-Host "!!! Brak kontenera do przywrócenia ($renamedOldTo). Ratunek: docs w scripts\README-refresh.md, sekcja Rollback ręczny." -ForegroundColor Red
    }
}

# --- główny przebieg -------------------------------------------------------
try {
    Step "0. Sprawdzenia wstępne"
    $null = Run "docker" @("info", "--format", "{{.ServerVersion}}")
    if (-not (Test-Path $ConfigFile)) { Fail "Brak pliku konfiguracji: $ConfigFile" }
    if (-not (ContainerExists $ProdName)) { Fail "Nie ma kontenera '$ProdName' — to skrypt do ODŚWIEŻANIA istniejącej produkcji." }
    if ((Run "docker" @("inspect", "-f", "{{.State.Running}}", $ProdName)).Trim() -ne "true") {
        Fail "Kontener '$ProdName' nie działa. Najpierw ustal dlaczego (docker logs $ProdName); skrypt nie odświeża zepsutej produkcji."
    }
    $prevRestart = (Run "docker" @("inspect", "-f", "{{.HostConfig.RestartPolicy.Name}}", $ProdName)).Trim()
    if (-not $prevRestart -or $prevRestart -eq "no") { $prevRestart = "unless-stopped" }

    $mountsJson = Run "docker" @("inspect", "-f", '{{json .Mounts}}', $ProdName)
    # UWAGA: `ConvertFrom-Json | Where-Object` scalone w JEDNYM potoku zawodzi pod Windows
    # PowerShell 5.1 (`powershell.exe`, w przeciwienstwie do pwsh) dla tablic JSON - Where-Object
    # nie filtruje poprawnie, gdy od razu dostaje wyjscie ConvertFrom-Json w tym samym potoku.
    # Rozdzielenie na dwa kroki (najpierw zmienna, potem filtr) dziala poprawnie w obu.
    $mounts = $mountsJson | ConvertFrom-Json
    $prodVolume = ($mounts | Where-Object { $_.Destination -eq "/data" } | Select-Object -First 1 -ExpandProperty Name)
    Write-Host "Obecny wolumen produkcji: $prodVolume (NIE ruszamy)"
    if ($SwitchOnly) {
        if ($NewVolume -notmatch '^mw_motis_refresh_[0-9]{8}-[0-9]{4}$') { Fail "-Volume musi miec postac mw_motis_refresh_RRRRMMDD-GGMM (dostalem '$NewVolume')." }
        if (-not (VolumeExists $NewVolume)) { Fail "Wolumen $NewVolume nie istnieje (docker volume ls)." }
        if ($NewVolume -eq $prodVolume) { Fail "Wolumen $NewVolume to juz obecna produkcja." }
    }
    elseif (VolumeExists $NewVolume) { Fail "Wolumen $NewVolume już istnieje — poczekaj minutę albo użyj innej godziny." }
    if ($Protected -contains $NewVolume) { Fail "Nazwa nowego wolumenu koliduje z chronionym." }
    if ($TestPort -eq $ProdPort) { Fail "Port testowy nie może być portem produkcji." }
    if (ContainerExists $TestName) { Fail "Kontener '$TestName' istnieje (pozostałość po przerwanym teście). Sprawdź go: docker ps -a; usuń ręcznie: docker rm -f $TestName" }

    foreach ($v in @("plcities-test_motis-data-pl-cities", "amazing-sammet-2e5029_motis-data-de-full")) {
        if (-not (VolumeExists $v)) { Write-Warning "Chroniony wolumen '$v' nie istnieje na tym Dockerze — sprawdź, czy to ta maszyna." }
    }

    $drive = Get-PSDrive -Name ((Get-Item $Repo).PSDrive.Name)
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    Write-Host "Wolne miejsce na $($drive.Name): $freeGB GB (min. $MinFreeGB GB)"
    if ($freeGB -lt $MinFreeGB) { Fail "Za mało miejsca na dysku ($freeGB GB < $MinFreeGB GB). Nic nie zostało zmienione. Zwolnij miejsce ręcznie (np. zbędne stare wolumeny mw_motis_refresh_*) i uruchom ponownie." }
    Write-Host "Uwaga: wolumeny Dockera leżą w dysku WSL2 — jeśli Docker Desktop ma osobny limit/dysk, sprawdź też: docker system df"

    
    # scripts\fetch_data.py pobiera tylko feedy krajowe/NRW (historyczny zakres) + Warszawe/Krakow -
    # NIE pobiera hvv.zip/mvv.zip/vrs.zip (Hamburg/Monachium/Kolonia) ani scalonego OSM calych Niemiec
    # (poland-germany-latest.osm.pbf), ktore motis\config.pl-cities.yml wymaga. Te pliki trzeba
    # dostarczyc recznie (zob. scripts\README-refresh.md) - sprawdzamy ich obecnosc TU, zanim
    # zaczniemy pobieranie/import, zeby nie wypalic kilkunastu-kilkudziesieciu minut na import,
    # ktory i tak padnie z powodu brakujacego pliku.
    $RequiredInputs = @(
        "data\osm\poland-germany-latest.osm.pbf",
        "data\gtfs\de\hvv.zip",
        "data\gtfs\de\mvv.zip",
        "data\gtfs\de\vrs.zip"
    )
    $missingInputs = $RequiredInputs | Where-Object { -not (Test-Path (Join-Path $Repo $_)) }
    if ($missingInputs) {
        Fail ("Brak plikow wejsciowych wymaganych przez motis\config.pl-cities.yml, ktorych scripts\fetch_data.py nie pobiera: " + ($missingInputs -join ', ') + ". Dostarcz je recznie przed ponownym uruchomieniem (zob. README-refresh.md).")
    }
    if ($SwitchOnly) {
        Step "1-2. Tryb -SwitchOnly: sprawdzam zgodnosc wolumenu $NewVolume z biezacymi danymi"
        $created = [datetime]::Parse((Run "docker" @("volume", "inspect", "-f", "{{.CreatedAt}}", $NewVolume)).Trim()).ToUniversalTime()
        Write-Host "Wolumen utworzony (UTC): $created"
        # Import startuje PO utworzeniu wolumenu, wiec kazdy plik wejsciowy zmieniony po tej chwili
        # mogl nie trafic do wolumenu (albo trafic w polowie). Wtedy blokujemy - bezpieczny kierunek bledu.
        $inputs = @(Get-ChildItem (Join-Path $Repo "data\gtfs") -Recurse -File -Filter *.zip) +
                  @(Get-Item (Join-Path $Repo "data\osm\poland-germany-latest.osm.pbf"), $ConfigFile)
        $changed = $inputs | Where-Object { $_.LastWriteTimeUtc -gt $created }
        if ($changed) {
            Fail ("Pliki zmienione PO utworzeniu wolumenu (dane mogą nie pasować do wolumenu): " + (($changed | ForEach-Object { $_.FullName }) -join ', ') + ". Przelaczenie ZABLOKOWANE. Zrob zwykly bieg bez -SwitchOnly.")
        }
        Write-Host "OK: zadne feedy/OSM/config nie sa nowsze niz wolumen ($($inputs.Count) plikow sprawdzonych)."
        Write-Host (Run "python" @("scripts\check_gtfs_freshness.py", "--min-days", "$MinDays"))
    }
    else {
    Step "1. Pobranie i sprawdzenie ważności feedów"
    if ($SkipFetch) { Write-Host "Pominięto pobieranie (-SkipFetch)." }
    else { $null = Run "python" @("scripts\fetch_data.py") }
    Write-Host (Run "python" @("scripts\check_gtfs_freshness.py", "--min-days", "$MinDays"))

    Step "2. Import do NOWEGO wolumenu $NewVolume (kilkadziesiąt minut)"
    $null = Run "docker" @("volume", "create", $NewVolume)
    if ($SeedFromProd) {
        Step "2a. Kopia danych prod -> $NewVolume (prod tylko do odczytu)"
        if (-not $prodVolume) { Fail "-SeedFromProd: prod nie uzywa nazwanego wolumenu pod /data, nie mam skad kopiowac." }
        Write-Warning "Kopiowanie zywych plikow: rob to, gdy nikt nie szuka tras. Opcja niezweryfikowana na zywo."
        # jawne pobranie obrazu, zeby docker run nie pobieral go "w locie" (komunikaty na stderr)
        try { $null = Run "docker" @("pull", "alpine:3") }
        catch { Fail "Nie udalo sie pobrac obrazu alpine:3 (internet/Docker Hub?). Pobierz recznie: docker pull alpine:3, albo uruchom bez -SeedFromProd. Szczegoly: $($_.Exception.Message)" }
        # wolumen prod montowany :ro, kopiujemy do NOWEGO wolumenu; obraz alpine tylko do cp
        $null = Run "docker" @("run", "--rm",
            "-v", "${prodVolume}:/src:ro",
            "-v", "${NewVolume}:/dst",
            "alpine:3", "sh", "-c", "cp -a /src/. /dst/ && ls -A /dst | head -1 | grep -q .")
        Write-Host "Kopia gotowa; import ponizej powinien pominac etapy, ktorych wejscia sie nie zmienily."
    }
    $null = Run "docker" @("run", "--rm", "--entrypoint", "/motis",
        "-v", "$(Join-Path $Repo 'data\osm'):/input/osm:ro",
        "-v", "$(Join-Path $Repo 'data\gtfs'):/input/gtfs:ro",
        "-v", "${NewVolume}:/data",
        "-v", "${ConfigFile}:/data/config.yml:ro",
        $Image, "import", "-d", "/data", "-c", "/data/config.yml")
    }

    Step "3. Test na osobnym porcie $TestPort (produkcja dalej działa)"
    Start-Motis -Name $TestName -Volume $NewVolume -HostPort $TestPort
    if (-not (Wait-Motis $TestPort $WarmupMinutes)) { Fail "Kontener testowy nie odpowiada po $WarmupMinutes min (docker logs $TestName)." }
    Test-Motis $TestPort
    $null = Run "docker" @("stop", $TestName)
    $null = Run "docker" @("rm", $TestName)

    if ($NoSwitch) {
        Write-Host "`n-NoSwitch: test zaliczony, produkcja NIETKNIĘTA. Nowy wolumen: $NewVolume" -ForegroundColor Green
        Stop-Transcript | Out-Null
        return
    }

    Step "4. Przełączenie produkcji"
    if (ContainerExists $OldName) {
        $archive = "$OldName-$Stamp"
        Write-Host "Istnieje już $OldName — zachowuję go pod nazwą $archive (nic nie kasuję)."
        $null = Run "docker" @("rename", $OldName, $archive)
    }
    $renamedOldTo = $OldName
    $switched = $true
    $null = Run "docker" @("stop", $ProdName)
    $null = Run "docker" @("rename", $ProdName, $OldName)
    # stary kontener nie może sam wstać po restarcie Dockera i zająć portu 8080
    $null = Run "docker" @("update", "--restart", "no", $OldName)
    Start-Motis -Name $ProdName -Volume $NewVolume -HostPort $ProdPort -Restart

    Step "5. Sprawdzenie po przełączeniu (port $ProdPort)"
    if (-not (Wait-Motis $ProdPort $WarmupMinutes)) { Fail "Nowy $ProdName nie odpowiada na porcie $ProdPort." }
    Test-Motis $ProdPort

    Write-Host "`nGOTOWE. Produkcja działa na nowym wolumenie $NewVolume." -ForegroundColor Green
    Write-Host "Rollback (poprzednia wersja) czeka jako kontener $OldName. Nic nie zostało skasowane."
    Write-Host "Stare wolumeny (sprzątać dopiero po kilku dniach spokojnej pracy i za zgodą właściciela):"
    Write-Host (Run "docker" @("volume", "ls", "--format", "{{.Name}}"))
}
catch {
    Write-Host "`nBŁĄD: $($_.Exception.Message)" -ForegroundColor Red
    if ($switched) { Invoke-Rollback }
    else {
        Write-Host "Produkcja nie była jeszcze ruszana — nic do przywracania." -ForegroundColor Yellow
        if (ContainerExists $TestName) {
            Write-Host "Usuwam własny kontener testowy $TestName (zgodnie z gwarancją skryptu)." -ForegroundColor Yellow
            $null = TryRun "docker" @("stop", $TestName)
            if (-not (TryRun "docker" @("rm", $TestName))) { Write-Host "!!! Nie udało się usunąć $TestName — usuń ręcznie: docker rm -f $TestName" -ForegroundColor Red }
        }
        if (VolumeExists $NewVolume)  { Write-Host "Częściowy wolumen $NewVolume zostaje — usuń go ręcznie, gdy zbędny: docker volume rm $NewVolume" }
    }
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null