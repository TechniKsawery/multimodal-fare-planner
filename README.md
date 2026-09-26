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
