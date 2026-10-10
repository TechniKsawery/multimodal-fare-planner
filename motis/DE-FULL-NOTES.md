# OSM całych Niemiec — osobny test (port 8081)

Status: **zaimportowane i przetestowane, działa**. Demo na porcie 8080
(`multimodalnawyszukiwarka-motis-1`, wolumen `motis-data`) nie było tknięte.

## Co zrobiono

1. Pobrano `poland-latest.osm.pbf` + `germany-latest.osm.pbf` z Geofabrik
   (ten sam moment, żeby uniknąć konfliktów węzłów na granicy) do
   `data/osm/`.
2. Scalono je przez `osmium merge` → `data/osm/poland-germany-latest.osm.pbf`
   (7,0 GB). Oryginalne pliki PL/DE osobno **usunięte** po scaleniu (nie są
   już potrzebne, merge jest deterministyczny — w razie czego można je
   ściągnąć ponownie i scalić od nowa).
3. Nowy, osobny `docker-compose.de-full.yml` + `motis/config.de-full.yml`:
   osobny wolumen (`motis-data-de-full`), osobny port (**8081**), osobny
   kontener. Istniejący `docker-compose.yml`/wolumen `motis-data` na porcie
   8080 — nietknięte.
4. Import wymagał podniesienia limitu RAM dla Dockera/WSL2 — zobacz niżej.

## Ważne: limit RAM Dockera

Import **padał na OOM** przy domyślnym limicie WSL2 (7,18 GB — to połowa
RAM tego hosta, ~14,8 GB, nikt tego nie ustawiał świadomie). Podniesiony
do **10 GB** w `%USERPROFILE%\.wslconfig`:

```
[wsl2]
memory=10GB
```

**Serwowanie** gotowych danych (nie import) jest dużo lżejsze: po imporcie
oba kontenery naraz (demo 8080 + test 8081) zużywały ~6,3 GB RAM w sumie
— mieści się nawet w oryginalnym limicie 7,18 GB, ale z niedużym zapasem
(~0,8 GB), więc pod większym obciążeniem może być ciasno.

**Żeby wrócić do domyślnego limitu Dockera:**
```
del %USERPROFILE%\.wslconfig
wsl --shutdown
```
(potem uruchom Docker Desktop normalnie — odpali silnik z domyślnym
limitem). Jeśli po powrocie do domyślnego limitu oba kontenery na raz
będą się zacinać/restartować, zostaw plik `.wslconfig` z wyższym limitem
na stałe, albo trzymaj włączony tylko jeden kontener naraz.

## Jak przełączyć się na pełne Niemcy (zamienić demo)

Dopóki to tylko test równoległy — nic nie trzeba przełączać, serwer na
8081 działa obok demo na 8080.

Żeby **zastąpić** demo na 8080 danymi PL+DE (gdy uznasz, że wynik jest
dobry):

```
docker compose down                         # zatrzymaj stary kontener/serwer
docker compose -f docker-compose.de-full.yml --profile import-de-full \
  run --rm motis-import-de-full             # (jeśli trzeba przebudować)
```

Prościej — podmień `osm:` w `motis/config.yml` na
`/input/osm/poland-germany-latest.osm.pbf`, zrób `docker compose --profile
import run --rm motis-import` (nadpisze stary wolumen `motis-data` nowym
importem PL+DE), potem `docker compose up -d motis`. To nieodwracalne bez
ponownego importu PL+NRW — rozważ, czy wolisz trzymać oba osobno (tańsze w
testach, droższe w RAM jak chodzą razem) czy podmienić na stałe.

## Jak wrócić do samego PL+NRW (gdyby trzeba było cofnąć)

Nic nie trzeba cofać — oryginalny kontener/wolumen (`motis-data`,
port 8080) nie był ruszany. Żeby usunąć eksperymentalny:

```
docker compose -f docker-compose.de-full.yml down
docker volume rm amazing-sammet-2e5029_motis-data-de-full
```

(nazwa wolumenu zależy od nazwy katalogu/worktree — sprawdź `docker volume
ls`).

## Testy, które przeszły (port 8081)

- Geokodowanie adresów (nie tylko nazw stacji) poza NRW: `Reeperbahn 1
  Hamburg`, `Buerer Straße 8 Gelsenkirchen`, `Skubiszewskiego 22 Lublin` —
  wszystkie zwracają `type: ADDRESS` z poprawnymi współrzędnymi. Stare demo
  (8080) dla adresów poza PL+NRW zwracało co najwyżej zgadywankę po nazwie
  najbliższej stacji (`type: STOP`), nie prawdziwy adres.
- Trasa Warszawa → Berlin (po adresie/nazwie miasta): działa, ~5h40m,
  pociąg Warszawa Centralna → Berlin-Lichtenberg + metro.
- Pełna trasa demo Skubiszewskiego 22 Lublin → Buerer Straße 8
  Gelsenkirchen przez aplikację Streamlit (`app.py`, `MOTIS_BASE_URL=
  http://localhost:8081`): **17 zbudowanych wariantów** (wcześniej na
  starym OSM trasa by się nie zbudowała w ogóle dla adresu docelowego).
  4 pominięte warianty to sprawy niezwiązane z OSM (fizycznie niewykonalna
  przesiadka, brak tokena Travelpayouts do lotów).

## Pliki

- `docker-compose.de-full.yml` — osobny compose (import + serwer)
- `motis/config.de-full.yml` — config wskazujący na scalony plik OSM
- `data/osm/poland-germany-latest.osm.pbf` — scalone dane wejściowe (poza
  gitem, `.gitignore` wyklucza `/data/`)
