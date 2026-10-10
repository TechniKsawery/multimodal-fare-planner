# OSM całych Niemiec — zaimportowane i połączone w 1 system (port 8080)

Status: **zaimportowane, przetestowane, połączone w jeden system**. Port
8080 serwuje teraz PL+DE (kontener `motis-main`). Stary wolumen `motis-data`
(PL+NRW) zachowany jako backup/rollback, nie usunięty.

## Co zrobiono

1. Pobrano `poland-latest.osm.pbf` + `germany-latest.osm.pbf` z Geofabrik
   (ten sam moment, żeby uniknąć konfliktów węzłów na granicy) do
   `data/osm/`.
2. Scalono je przez `osmium merge` → `data/osm/poland-germany-latest.osm.pbf`
   (7,0 GB). Oryginalne pliki PL/DE osobno **usunięte** po scaleniu (nie są
   już potrzebne, merge jest deterministyczny — w razie czego można je
   ściągnąć ponownie i scalić od nowa).
3. Zaimportowano do osobnego wolumenu Dockera (`amazing-sammet-2e5029_motis-data-de-full`,
   13,6 GB) przez `docker-compose.de-full.yml` + `motis/config.de-full.yml`,
   najpierw równolegle na porcie 8081, stary demo na 8080 nietknięty.
4. Import wymagał podniesienia limitu RAM dla Dockera/WSL2 — zobacz niżej.
5. Po potwierdzeniu, że działa (testy niżej), **połączono w jeden system**:
   - zatrzymany stary kontener `multimodalnawyszukiwarka-motis-1` (wolumen
     `motis-data` z PL+NRW **zachowany**, nie usunięty — to backup),
   - usunięty eksperymentalny kontener z portu 8081 (jego wolumen,
     `amazing-sammet-2e5029_motis-data-de-full`, **został**),
   - uruchomiony nowy kontener `motis-main` na porcie **8080**, na tym
     samym wolumenie co wyżej:
     ```powershell
     docker run -d --name motis-main -p 8080:8080 `
       -v amazing-sammet-2e5029_motis-data-de-full:/data `
       -v "<ścieżka repo>\motis\config.de-full.yml:/data/config.yml:ro" `
       ghcr.io/motis-project/motis:latest
     ```
   - ponownie zweryfikowano na 8080 (adresy, trasa Warszawa → Berlin).

## Ważne: limit RAM Dockera

Import **padał na OOM** przy domyślnym limicie WSL2 (7,18 GB — to połowa
RAM tego hosta, ~14,8 GB, nikt tego nie ustawiał świadomie). Podniesiony
do **10 GB** w `%USERPROFILE%\.wslconfig`:

```
[wsl2]
memory=10GB
```

**Zostaje tak na razie.** Pojedynczy kontener (po połączeniu, bez
drugiego obok) zużywa ~5,3 GB — 4,1 GB zapasu w limicie 10 GB, zero
ryzyka. Limit to tylko pułap (nie rezerwacja), więc nie kosztuje nic przy
obecnym zużyciu. Obniżanie go wymagałoby kolejnego restartu WSL/Dockera
bez realnej korzyści.

**Żeby wrócić do domyślnego limitu Dockera** (gdyby jednak było trzeba):
```
del %USERPROFILE%\.wslconfig
wsl --shutdown
```
(potem uruchom Docker Desktop normalnie, i ręcznie odpal `motis-main` —
patrz niżej).

## Uwaga: `motis-main` nie ma restart policy

Kontener wystartował zwykłym `docker run` bez `--restart`, więc **po
restarcie Windows/Dockera/WSL trzeba go odpalić ręcznie jeszcze raz**:
```
docker start motis-main
```
(kontener i jego dane zostają, nie trzeba nic przebudowywać). Żeby to
zautomatyzować na stałe: `docker update --restart unless-stopped motis-main`.

## Jak wrócić do samego PL+NRW (rollback)

Stary wolumen (`motis-data`, dane PL+NRW) nie został usunięty. Żeby
przywrócić stare demo na 8080:
```
docker stop motis-main
docker run -d --name motis-1 -p 8080:8080 `
  -v multimodalnawyszukiwarka_motis-data:/data `
  -v "<ścieżka repo>\motis\config.yml:/data/config.yml:ro" `
  ghcr.io/motis-project/motis:latest
```
(albo po prostu `docker compose up -d motis` z głównego checkoutu, jeśli
`docker-compose.yml` tam nadal wskazuje na wolumen `motis-data`).

## Testy, które przeszły

- Geokodowanie adresów (nie tylko nazw stacji) poza NRW: `Reeperbahn 1
  Hamburg`, `Buerer Straße 8 Gelsenkirchen`, `Skubiszewskiego 22 Lublin` —
  wszystkie zwracają `type: ADDRESS` z poprawnymi współrzędnymi. Stare demo
  (PL+NRW) dla adresów poza PL+NRW zwracało co najwyżej zgadywankę po
  nazwie najbliższej stacji (`type: STOP`), nie prawdziwy adres.
- Trasa Warszawa → Berlin (po adresie/nazwie miasta): działa, ~5h40m,
  pociąg Warszawa Centralna → Berlin-Lichtenberg + metro.
- Pełna trasa demo Skubiszewskiego 22 Lublin → Buerer Straße 8
  Gelsenkirchen przez aplikację Streamlit (`app.py`): **17 zbudowanych
  wariantów** (wcześniej na starym OSM trasa by się nie zbudowała w ogóle
  dla adresu docelowego). 4 pominięte warianty to sprawy niezwiązane z
  OSM (fizycznie niewykonalna przesiadka, brak tokena Travelpayouts do
  lotów).
- Wszystko powyższe zweryfikowane dwa razy: najpierw na porcie 8081
  (test równoległy), potem ponownie na 8080 po połączeniu w jeden system
  (te same dane, inny port/kontener).

## Jeszcze niesprawdzone

- Ceny/ulgi (PR #44/#45: PKP, BahnCard, VRR itd.) na nowych danych —
  logika po stronie aplikacji się nie zmieniła, powinna działać
  identycznie jak wcześniej, ale nie klikane ręcznie.
- Loty / FlixBus na nowych danych.

## Pliki

- `docker-compose.de-full.yml` — compose użyty do importu (import +
  serwer eksperymentalny na 8081, już nieużywany, ale zostawiony do
  wglądu/powtórzenia importu)
- `motis/config.de-full.yml` — config wskazujący na scalony plik OSM,
  używany teraz przez `motis-main`
- `data/osm/poland-germany-latest.osm.pbf` — scalone dane wejściowe (poza
  gitem, `.gitignore` wyklucza `/data/`)
