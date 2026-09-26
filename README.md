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
OSM nie jest na razie wczytywany — routing działa wyłącznie na rozkładach GTFS.
Geocoding (`geocoding: true`) działa mimo braku OSM, bo podpowiedzi budowane są z nazw
przystanków GTFS — w UI (`http://localhost:8080`) wpisanie np. "Lublin" pokazuje listę stacji
kolejowych, a np. "Krakowskie Przedmieście" pokazuje przystanek ZTM. Zapytania do API można też
podawać wprost przez `stopId` (`<dataset>_<id z stops.txt>`) lub współrzędne. ID przystanków/tras
między feedami GTFS się powtarzają (np. `route_id` `7` istnieje w kilku feedach) — MOTIS je
rozróżnia dzięki prefiksowi datasetu, więc to nie jest błąd.

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
