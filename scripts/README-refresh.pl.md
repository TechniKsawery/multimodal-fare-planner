Polski | English: [English version](README-refresh.md)

# Odświeżanie danych (GTFS) na produkcji — instrukcja bez pomocy AI

Skrypt: `scripts\refresh_prod.ps1`. Robi wszystko sam i **niczego nie kasuje**. Przy błędzie wraca do poprzedniej wersji.

## Zanim zaczniesz
1. Uruchom Docker Desktop i poczekaj, aż będzie "running".
2. Sprawdź, że `motis-main` działa: `docker ps` (ma być na porcie 8080, strona działa).
3. Wolne miejsce na dysku: min. 40 GB (skrypt sprawdzi sam i się zatrzyma, jeśli jest mniej).

## Uruchomienie
```powershell
cd "<katalog-projektu>"
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1
```
Trwa zwykle od kilkudziesięciu minut do ponad godziny (import). Nie zamykaj okna. Log leci też do `data\logs\refresh_prod-<data>.log`.

Bezpieczny pierwszy raz (wszystko poza przełączeniem produkcji): dodaj `-NoSwitch`.

## Szybsza wersja: `-SeedFromProd` (NIEZWERYFIKOWANE na żywo)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -SeedFromProd
```
Przed importem kopiuje dane obecnej produkcji do nowego wolumenu (prod jest montowany tylko do odczytu, nic w nim się nie zmienia). Pomysł: przy tym samym pliku OSM MOTIS pomija najdłuższe etapy (`osr`, `adr`) i przelicza głównie rozkłady. To wnioskowanie z logów, jeszcze nie sprawdzone na żywo; jeśli nie przyspieszy, import i tak się wykona, tylko dłużej.
- Rób to, gdy **nikt nie szuka tras** (kopiowanie plików w trakcie zapisu mogłoby dać niespójną kopię).
- Skrypt sam robi `docker pull alpine:3`; gdy się nie uda (brak internetu), pobierz ręcznie `docker pull alpine:3` albo uruchom bez `-SeedFromProd`.
- Wymaga dodatkowego miejsca na dysku (kopia całego wolumenu prod) i pobrania małego obrazu `alpine:3`.

## Przełączenie gotowego wolumenu: `-SwitchOnly` (bez ponownego importu)
Gdy bieg z `-NoSwitch` już przeszedł i masz przetestowany wolumen `mw_motis_refresh_<data>`:
```powershell
docker volume ls     # znajdź nazwę wolumenu mw_motis_refresh_...
powershell -ExecutionPolicy Bypass -File scripts\refresh_prod.ps1 -SwitchOnly -Volume mw_motis_refresh_20261012-1606
```
Skrypt: sprawdza, że wolumen istnieje i nie jest obecnym prod, **blokuje przełączenie**, jeśli któryś feed GTFS, plik OSM lub config jest nowszy niż wolumen (dane mogłyby nie pasować), sprawdza ważność feedów, testuje wolumen na porcie 8083, dopiero potem zamienia prod (`motis-main` → `motis-main-old`) i testuje 8080. Przy błędzie po zamianie sam wraca do starej wersji. Zabezpieczenie opiera się na czasach modyfikacji plików (nie na hashach), więc ponowne pobranie tych samych plików też zablokuje przełączenie; wtedy zrób zwykły bieg.

## Co robi (po kolei)
1. Sprawdza Docker, miejsce na dysku, czy produkcja żyje.
2. Pobiera feedy i sprawdza ważność (min. 3 dni).
3. Importuje do NOWEGO wolumenu `mw_motis_refresh_<data>`.
4. Odpala test na porcie 8083 (Warszawa, Kraków, Hamburg, trasa Lublin → Gelsenkirchen).
5. Zatrzymuje `motis-main`, zmienia mu nazwę na `motis-main-old` i startuje nowy `motis-main` na 8080.
6. Powtarza testy na 8080. Jeśli któryś padnie — **sam wraca** do starej wersji.

Komunikat `GOTOWE` na zielono = wszystko działa. Komunikat `BŁĄD` na czerwono = przeczytaj, co pisze; skrypt już zadbał o stan produkcji.

## Pliki, których ten skrypt NIE odświeża

`scripts\fetch_data.py` pobiera tylko feedy krajowe/NRW oraz Warszawę/Kraków. Skrypt sam sprawdzi
ich obecność i zatrzyma się z czytelnym błędem PRZED pobraniem/importem, jeśli ich nie znajdzie —
ale nie wie, jak je pobrać/odświeżyć:
- `data\osm\poland-germany-latest.osm.pbf` (scalony OSM Polski i całych Niemiec)
- `data\gtfs\de\hvv.zip` (Hamburg), `mvv.zip` (Monachium), `vrs.zip` (Kolonia/Bonn)

Te pliki trzeba dostarczyć/odświeżyć ręcznie (ten sam sposób, jakim powstały pierwotnie —
zob. `motis\PL-CITIES-GTFS-NOTES.md`). Feedy GTFS tych trzech miast też wygasają z czasem jak
reszta — `scripts\check_gtfs_freshness.py` (wywoływany przez ten skrypt) je widzi i ostrzeże,
ale nikt ich automatycznie nie odświeża.

## Czego NIGDY nie robić ręcznie
- Nie kasuj wolumenów: `plcities-test_motis-data-pl-cities` (obecna produkcja), `amazing-sammet-2e5029_motis-data-de-full` (rollback), `multimodalnawyszukiwarka_motis-data-de-full-city-gtfs`, `multimodalnawyszukiwarka_motis-data`.
- Żadnych `docker volume prune` ani `docker system prune`.
- Stare wolumeny `mw_motis_refresh_*` i kontener `motis-main-old` kasuj dopiero po kilku dniach spokojnej pracy.

## Rollback ręczny (gdyby skrypt się wysypał w połowie)
```powershell
docker ps -a                       # zobacz, jakie kontenery motis-* istnieją
docker stop motis-main             # jeśli stoi nowy, zepsuty
docker rename motis-main motis-main-zepsuty
docker rename motis-main-old motis-main
docker update --restart unless-stopped motis-main
docker start motis-main
```
Potem poczekaj ok. minuty i sprawdź `http://localhost:8080`. Jeśli kontenera `motis-main-old` nie ma, szukaj `motis-main-old-<data>` (`docker ps -a`).

## Najczęstsze problemy
- "Za mało miejsca" — zwolnij dysk, uruchom ponownie. Nic nie zostało zmienione.
- "Kontener motis-refresh-test istnieje" — pozostałość po przerwanym teście: `docker rm -f motis-refresh-test`.
- Import pada na OOM — podnieś limit pamięci WSL2 w `%USERPROFILE%\.wslconfig` (`memory=12GB`), `wsl --shutdown`, uruchom Dockera i skrypt ponownie.
- Feed wygasa za krótko — źródło nie wydało świeżej wersji; spróbuj później.
