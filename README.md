# Multimodalna wyszukiwarka

Wyszukiwarka połączeń kolejowych PL + DE (np. Lublin → Gelsenkirchen) z szacunkiem cen.

## Sesja 1: dane

```
python scripts/fetch_data.py
```

Pobiera do `data/` (katalog jest w `.gitignore`):

| Ścieżka | Źródło |
|---|---|
| `data/gtfs/pl/polish_trains.zip` | PolishTrainsGTFS, mkuran.pl |
| `data/gtfs/de/de_fv.zip` | gtfs.de, ruch dalekobieżny (FV) |
| `data/gtfs/de/de_rv.zip` | gtfs.de, koleje regionalne (RV, całe Niemcy z NRW) |
| `data/gtfs/pl/lublin.zip` | ZTM Lublin (ZDiTM), mkuran.pl, CC0 |
| `data/osm/poland-latest.osm.pbf` | Geofabrik |
| `data/osm/nordrhein-westfalen-latest.osm.pbf` | Geofabrik |

Potem sprawdza sumy MD5 plików OSM i waliduje feedy GTFS (`scripts/check_gtfs.py`):
kompletność archiwum, wymagane pliki, liczby przystanków i kursów, zakres dat,
spójność kluczy. Raport ląduje w `data/gtfs/REPORT.txt`.

## Sesja 2: routing (MOTIS)

Silnik routingu [MOTIS](https://github.com/motis-project/motis) uruchamiany w Dockerze,
skonfigurowany w `motis/config.yml` (cztery feedy GTFS jako oddzielne datasety: `pl` (PKP),
`defv`, `derv` (DE), `ztml` (komunikacja miejska ZTM Lublin — autobusy i tramwaje)).
Od Sesji 4b silnik ma też wczytane dane OSM (patrz niżej) — geocoding i routing obsługują
też dokładne adresy/ulice, nie tylko nazwy przystanków. Zapytania do API można podawać przez
`stopId` (`<dataset>_<id z stops.txt>`) albo przez współrzędne (`lat,lon`, np. z geocodingu
adresu). ID przystanków/tras między feedami GTFS się powtarzają (np. `route_id` `7` istnieje w
kilku feedach) — MOTIS je rozróżnia dzięki prefiksowi datasetu, więc to nie jest błąd.

Wymaga uruchomionego Docker Desktop. W Git Bash / WSL:

```
scripts/run_motis.sh import   # buduje dane w motis/data/
scripts/run_motis.sh server   # startuje serwer HTTP na http://localhost:8080
```

W czystym PowerShell (skrypt .sh się tam nie uruchomi):

```
powershell -File scripts\run_motis.ps1 import
powershell -File scripts\run_motis.ps1 server
```

Przykładowe zapytanie (Lublin Główny → Gelsenkirchen Hbf):

```
curl "http://localhost:8080/api/v6/plan?fromPlace=pl_50500&toPlace=derv_344028&time=2026-09-28T06:00:00Z&maxTransfers=4"
```

Zwraca m.in. połączenie IC Lublin→Warszawa Wschodnia → EIC do Berlina →
S-Bahn → ICE do Gelsenkirchen Hbf (~12h15min, 3 przesiadki).

`motis/data/` (wygenerowane dane binarne) nie jest w repo — buduje się je lokalnie
poleceniem `import` powyżej.

## Sesja 3: moduł taryf

Moduł `fares/` szacuje cenę pojedynczego segmentu podróży: PKP Intercity, DB (Flexpreis)
i VRR (eezy.nrw). Pasma cenowe i ulgi PKP Intercity oraz taryfa eezy.nrw VRR pochodzą teraz
z **oficjalnych, aktualnych cenników** (research w built-in browser); DB Flexpreis **nadal jest
szacunkiem** (mnożniki BahnCard są oficjalne, ale DB nie publikuje tabeli cena-za-km — patrz
[`fares/README.md`](fares/README.md) po pełną listę źródeł i ograniczeń).

```python
from fares import estimate_price
from fares.model import Carrier, DiscountProfile, Segment

result = estimate_price(Segment(
    carrier=Carrier.PKP_INTERCITY,
    origin="Lublin", destination="Warszawa Wschodnia",
    distance_km=170,
    discounts=DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"),
))
```

Testy: `pytest tests/test_fares.py`.

## Sesja 3b: moduł cen lotów

Moduł `flights/` szacuje cenę segmentu lotu: cena biletu z
[Travelpayouts Data API](https://www.travelpayouts.com/programs/100/tools/api) (dane z cache,
mogą być nieaktualne o kilka dni) + bagaż + dojazd na lotnisko + transfer z lotniska do miasta
docelowego (osobne, konfigurowalne składniki). Wymaga darmowego tokena API w zmiennej
środowiskowej `TRAVELPAYOUTS_TOKEN` — szczegóły konfiguracji i struktura są w
[`flights/README.md`](flights/README.md). Każdy wynik oznaczony jako `PriceType.ESTIMATE`
("szacunek"), tak jak w module `fares/`.

```python
from flights import FlightSegment, estimate_price

result = estimate_price(FlightSegment(
    origin="WAW", destination="DUS", depart_date="2026-11-15", currency="PLN",
))
```

Testy (mockują API, nie wymagają tokena): `pytest tests/test_flights.py`.

## Sesja 4: silnik optymalizacji trasy

Moduł `routing/` łączy routing MOTIS (Sesja 2) z modułami taryf `fares/`/`flights/`
(Sesja 3/3b) w kilka wariantów podróży dla jednej pary miast/daty: liczy dla każdego cenę,
czas i liczbę przesiadek, sprawdza bezpieczeństwo przesiadek (czy jest wystarczająco czasu na
zmianę pociągu/lotu) i wybiera 4 rekomendacje (najtańsza, najszybsza, najmniej przesiadek,
najlepszy stosunek cena/czas). Szczegóły metody, ograniczenia zakresu i założenia —
[`routing/README.md`](routing/README.md).

```
python demo.py
```

Wymaga uruchomionego MOTIS (Sesja 2). Warianty z lotem wymagają `TRAVELPAYOUTS_TOKEN`
(Sesja 3b) — bez tokena zostaną pominięte, reszta demo i tak zadziała.

Testy (mockują MOTIS i flights, nie wymagają żadnych zewnętrznych usług):
`pytest tests/test_routing.py`.

## Sesja 4b: wyszukiwanie po adresach (OSM)

Do MOTIS-a dograno dane OSM (Polska + Nadrenia Płn.-Westfalia z Geofabrik, scalone jednym
plikiem narzędziem `osmium merge`, bo MOTIS przyjmuje tylko jeden plik `osm:` w konfiguracji) —
`street_routing: true` i `osr_footpath: true` w `motis/config.yml` włączają routing pieszy po
sieci ulic, a `geocoding`/`reverse_geocoding` teraz podpowiadają też konkretne adresy, nie tylko
przystanki. Dzięki temu trasę można zaplanować od/do dowolnego adresu (np. konkretnej ulicy w
Lublinie), z automatycznym dojściem pieszym do najbliższego przystanku ZTM/PKP/VRR — dokładnie
jak w DB Navigatorze.

```
curl "http://localhost:8080/api/v1/geocode?text=Krakowskie+Przedmie%C5%9Bcie+50%2C+Lublin"
curl "http://localhost:8080/api/v1/plan?fromPlace=51.247737,22.5591905&toPlace=51.5060792,7.1016332&time=2026-09-28T06:00:00Z&maxTransfers=4"
```

Druga komenda (adres w Lublinie → adres na Bahnhofstraße w Gelsenkirchen) zwraca trasę: pieszo
do przystanku ZTM „Ogród Saski” → autobus do Lublina Głównego → pociąg do Warszawy Wschodniej →
pociąg do Berlina → pociąg do Gelsenkirchen Hbf → pieszo do adresu docelowego.

**Ważne — `motis/data` to teraz nazwany wolumen Dockera, nie folder na dysku.** Import OSM
buduje duże memory-mapped pliki, które w locie się powiększają (resize) — bind mounty Docker
Desktop na Windows (gRPC-FUSE/VirtioFS) tego nie obsługują i import kończył się błędem
`unable to import: resize error`. Rozwiązanie: `docker-compose.yml` mapuje `/data` na wolumen
`motis-data`, a `motis/config.yml` jest osobno bind-mountowany jako pojedynczy plik tylko do
odczytu. `scripts/run_motis.sh`/`.ps1 import` działają bez zmian w użyciu.

Import z OSM (scalony plik ~2.8 GB) trwał na tym sprzęcie około 15–20 minut (samo scalanie PL+NRW
narzędziem `osmium merge` to dodatkowe ~4 minuty, jednorazowo). `pytest tests/test_routing.py`
(30 testów) przechodzi bez zmian — moduł `routing/` operuje na zamockowanym MOTIS-ie, więc nie
zależy od danych OSM ani identyfikatorów przystanków.
