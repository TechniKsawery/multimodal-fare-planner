Polski | English: [English version](DE-FULL-CITY-GTFS-NOTES.md)

# Lokalny transport miejski HVV/MVV/VRS w MOTIS — do zrobienia przez RC na PC

Status: **PRZYGOTOWANE, NIE WYKONANE**. Ten kontener (sesja w chmurze) nie ma dostępu do
Twojego Dockera ani do hostów `mvv-muenchen.de`/`vrsinfo.de`/`mobilitydatabase.org` — pobieranie
i `docker compose`/`docker run` musi zrobić sesja Remote Control na Twoim PC. Poniżej są gotowe
komendy do wklejenia, w kolejności. Nic z tego nie zostało jeszcze odpalone.

Kontynuacja PR #46 (OSM całych Niemiec, `motis-main` na porcie 8080) — **OSM zostaje bez zmian**,
dociągamy tylko 3 nowe pliki GTFS dla lokalnego transportu Hamburga, Monachium i Kolonii/Bonn,
żeby kalkulatory `fares/hvv.py`/`mvv.py`/`kvb.py` (PR #42, #49) miały realne trasy do wyceniania,
nie tylko sztywną cenę bez odcinka.

## 0. Skąd te pliki i jaka licencja (research, zob. pamięć projektu)

| Związek | URL | Licencja | Rozmiar (ZIP / rozpakowane) |
|---|---|---|---|
| HVV (Hamburg) | https://files.mobilitydatabase.org/mdb-3362/mdb-3362-202607201528/mdb-3362-202607201528.zip | **DL-DE-BY-2.0** (https://www.govdata.de/dl-de/by-2-0) — wystarczy atrybucja | ~38-41 MB / ~275-280 MB |
| MVV (Monachium) | https://www.mvv-muenchen.de/fileadmin/mediapool/developer/opendata/gesamt_gtfs.zip | **CC BY 4.0** | nieujawniony |
| VRS (Kolonia/Bonn, zawiera też SPNV) | http://download.vrsinfo.de/gtfs/GTFS_VRS_mit_SPNV.zip | **CC BY 4.0** | nieujawniony |

Atrybucja do dopisania w README/stopce aplikacji (jeśli jeszcze nie ma — sprawdź
`fares/README.md`/`attractions/README.md` czy jest już sekcja atrybucji danych):

```
Dane GTFS: Hamburger Verkehrsverbund GmbH (HVV), licencja DL-DE-BY-2.0 — https://www.govdata.de/dl-de/by-2-0
Dane GTFS: Münchner Verkehrs- und Tarifverbund GmbH (MVV), licencja CC BY 4.0
Dane GTFS: Verkehrsverbund Rhein-Sieg GmbH (VRS), licencja CC BY 4.0
```

HVV i MVV są aktualizowane raz na jakiś czas (miesięcznie), VRS **codziennie w nocy** — jeśli to
zostanie na stałe, warto docelowo zautomatyzować pobieranie VRS (poza zakresem tego PR-a).

## 1. Pobranie 3 plików GTFS (PowerShell, z katalogu repo głównego checkoutu)

```powershell
cd "<katalog-projektu>"
New-Item -ItemType Directory -Force -Path data\gtfs\de | Out-Null

Invoke-WebRequest -Uri "https://files.mobilitydatabase.org/mdb-3362/mdb-3362-202607201528/mdb-3362-202607201528.zip" -OutFile "data\gtfs\de\hvv.zip"
Invoke-WebRequest -Uri "https://www.mvv-muenchen.de/fileadmin/mediapool/developer/opendata/gesamt_gtfs.zip" -OutFile "data\gtfs\de\mvv.zip"
Invoke-WebRequest -Uri "http://download.vrsinfo.de/gtfs/GTFS_VRS_mit_SPNV.zip" -OutFile "data\gtfs\de\vrs.zip"

Get-Item data\gtfs\de\hvv.zip, data\gtfs\de\mvv.zip, data\gtfs\de\vrs.zip | Select-Object Name, Length
```

Jeśli któryś URL nie zadziała (producent czasem zmienia link): HVV ma stabilny fallback na
`https://mobilitydatabase.org/feeds/mdb-3362` (strona z linkiem "Download"), MVV i VRS mają
swoje strony operatora (`mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/opendata/`,
`vrsinfo.de/fahrplan/oepnv-daten-fuer-webentwickler.html`) — tam zawsze jest aktualny link.

## 2. Import do NOWEGO wolumenu (osobny port 8082 — nie dotyka `motis-main` na 8080)

OSM jest już na dysku (`data/osm/poland-germany-latest.osm.pbf`, scalony w PR #46) — tego
importu **nie trzeba powtarzać**, tylko dodać 3 nowe datasety GTFS do konfigu. Nowy plik configu
(`motis/config.de-full-city-gtfs.yml`) i compose (`docker-compose.de-full-city-gtfs.yml`) są już
w repo (ten PR).

```powershell
cd "<katalog-projektu>"
docker compose -f docker-compose.de-full-city-gtfs.yml --profile import-city-gtfs run --rm motis-import-city-gtfs
```

**Zapotrzebowanie na pamięć** — oszacowanie, NIE zmierzone (ten kontener nie ma dostępu do
Twojego Dockera): limit WSL2 jest już podniesiony do **10 GB** (PR #46). Sam serwujący kontener
PL+DE (bez miast) zużywał ~5,3 GB (~4,1 GB zapasu). 3 nowe pliki GTFS to razem ~40-100 MB
spakowane — rząd wielkości mniejszy niż OSM całych Niemiec (7 GB wejścia) — więc **sam import
prawdopodobnie zmieści się w 10 GB**, ale import wcześniej (OSM) padał na OOM przy domyślnym
limicie, więc **obserwuj `docker stats` podczas importu**. Jeśli padnie na OOM:
```
# %USERPROFILE%\.wslconfig
[wsl2]
memory=12GB
```
potem `wsl --shutdown` i uruchom Docker Desktop ponownie, powtórz import. Po zakończeniu importu
można wrócić do 10 GB (serwowanie samo powinno zużywać podobnie jak teraz, może nieco więcej —
nowe indeksy w RAM dla 3 dodatkowych feedów, ale to dużo mniej danych niż OSM).

## 3. Test równoległy na porcie 8082 (NIE dotyka produkcyjnego 8080)

```powershell
docker compose -f docker-compose.de-full-city-gtfs.yml up -d motis-city-gtfs
```

Sprawdź w przeglądarce/curl, że serwer wstał:
```powershell
curl http://localhost:8082/api/v1/geocode?text=Hauptbahnhof+Hamburg
```

**Test, który faktycznie ma znaczenie** (tego nie mogłem zrobić z tej sesji — potrzeba żywego
MOTIS): trasa z lokalnym odcinkiem w każdym z 3 miast, np. przez `demo.py`/`app.py` wskazane na
port 8082, albo bezpośrednio przez API MOTIS:
- Hamburg: `Hauptbahnhof Hamburg` → `Landungsbrücken` (krótki odcinek lokalny HVV)
- Monachium: `Marienplatz München` → `Hauptbahnhof München` (MVV)
- Kolonia: `Köln Hauptbahnhof` → `Köln Deutz` (VRS/KVB)

Sprawdź, że zwrócona trasa ma `agencyName`/nazwy przystanków zawierające "HVV"/"Hamburg",
"MVV"/"München" albo "VRS"/"Köln" — `routing/pricing.py::price_bus_leg()` (linie ~353-366)
dopasowuje po tych słowach kluczowych (już wgrane, PR #42/#49, nic nie trzeba zmieniać w
kodzie), więc jeśli nazwy się zgadzają, cena powinna wyjść z kalkulatora HVV/MVV/kvb.py, nie
z fallbacku. Jeśli dopasowanie nie zadziała (inne nazewnictwo w danych niż założone słowa
kluczowe), trzeba poszerzyć `HVV_KEYWORDS`/`MVV_KEYWORDS`/`VRS_KOLN_KEYWORDS` w
`routing/pricing.py` o rzeczywiste nazwy z danych — da się to ustalić tylko patrząc na prawdziwą
odpowiedź MOTIS, stąd ten krok musi zrobić sesja z żywym dostępem do Twojego Dockera.

## 4. Przełączenie na produkcyjny port 8080 — WYKONANE (2026-10-10)

Status: **ZROBIONE przez Ksaviego przez RC, zweryfikowane** — `motis-main` na porcie 8080 serwuje
dane z wolumenu `multimodalnawyszukiwarka_motis-data-de-full-city-gtfs` (nazwa wolumenu z prefiksem
projektu `docker compose`, nie `motis-data-de-full-city-gtfs` jak w gołym `docker run` poniżej —
jeśli odtwarzasz ten krok ręcznie bez przechodzenia przez compose, sprawdź `docker volume ls` i
użyj dokładnej nazwy, którą tam widzisz). Geocoding Hamburga na `http://localhost:8080` potwierdzony
(pierwszy curl po starcie dał "Empty reply from server" — serwer jeszcze się rozgrzewał/ładował
indeksy, drugi curl kilka sekund później zadziałał normalnie — to nie błąd, tylko czas startu).

Analogicznie do przełączenia PL+NRW -> PL+DE w PR #46:

```powershell
docker stop motis-city-gtfs   # albo nazwa z `docker compose ps`, np. multimodalnawyszukiwarka-motis-city-gtfs-1
docker rm motis-city-gtfs
docker stop motis-main
docker run -d --name motis-main -p 8080:8080 `
  -v multimodalnawyszukiwarka_motis-data-de-full-city-gtfs:/data `
  -v "<katalog-projektu>\motis\config.de-full-city-gtfs.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
docker update --restart unless-stopped motis-main
```

Stary kontener/wolumen `motis-main`+`amazing-sammet-2e5029_motis-data-de-full` (PL+DE **bez**
miast) **nie jest usuwany** — zostaje jako backup/rollback, tak jak przy wcześniejszym
przełączeniu PL+NRW→PL+DE.

## 5. Rollback (gdyby coś nie zagrało)

```powershell
docker stop motis-main
docker rm motis-main
docker run -d --name motis-main -p 8080:8080 `
  -v amazing-sammet-2e5029_motis-data-de-full:/data `
  -v "<katalog-projektu>\motis\config.de-full.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
docker update --restart unless-stopped motis-main
```

## Co NIE jest zrobione przez tę zmianę (zostaje do zweryfikowania przez RC)

- Pobranie plików, import, test routingu i przełączenie — **WYKONANE** przez Ksaviego przez RC
  (2026-10-10), kroki 1-4 zaliczone, produkcja na 8080 działa na nowych danych z HVV/MVV/VRS.
- Ceny MVV strefy M-6/M-12 (zob. PR #49, `verification/hvv-mvv-vrs-ulgi-transport-2026-10-10.md`)
  — niezależne od tego zadania, zostają do potwierdzenia w przeglądarce.
- Dopasowanie słów kluczowych w `routing/pricing.py` ZADZIAŁAŁO na rzeczywistych danych (test
  `scripts/test_local_transit_hvv_mvv_vrs.py` na porcie 8082, wszystkie 3 miasta `oficjalna_taryfa`)
  — nic do poprawki w kodzie.
