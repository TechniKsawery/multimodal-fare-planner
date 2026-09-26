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
| `data/osm/poland-latest.osm.pbf` | Geofabrik |
| `data/osm/nordrhein-westfalen-latest.osm.pbf` | Geofabrik |

Potem sprawdza sumy MD5 plików OSM i waliduje feedy GTFS (`scripts/check_gtfs.py`):
kompletność archiwum, wymagane pliki, liczby przystanków i kursów, zakres dat,
spójność kluczy. Raport ląduje w `data/gtfs/REPORT.txt`.

## Sesja 2: routing (MOTIS)

Silnik routingu [MOTIS](https://github.com/motis-project/motis) uruchamiany w Dockerze,
skonfigurowany w `motis/config.yml` (trzy feedy GTFS jako oddzielne datasety: `pl`, `defv`, `derv`).
OSM nie jest na razie wczytywany — routing kolejowy działa wyłącznie na rozkładach GTFS,
zapytania podaje się przez `stopId` (`<dataset>_<id z stops.txt>`) lub współrzędne.

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
