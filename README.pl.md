# Multimodalna wyszukiwarka

🇺🇸 [English version → README.md](README.md) · 🇵🇱 Polska wersja (ten plik)

Wyszukiwarka połączeń kolejowych PL + DE (np. Lublin → Gelsenkirchen) z szacunkiem cen.

## Stan projektu

> **Projekt portfolio / prototyp, nie produkt komercyjny.** Ostatnia aktualizacja repozytorium:
> **2026-11-12** (porządki przed publikacją); ostatnie zmiany funkcjonalne: 2026-11-09.

- **Zakres:** routing PL + DE (kolej, część autobusów i lotów) oparty o silnik MOTIS i otwarte
  feedy GTFS, plus warstwa szacunku cen z uwzględnieniem ulg i kart. Ceny to **szacunki**,
  nie oferta sprzedaży i bez gwarancji poprawności; zakup biletów nie jest zaimplementowany.
- **Dane i ich aktualność:** feedy GTFS i OSM są pobierane skryptami (nie są w repozytorium) i
  mają daty ważności. Według notatek z 2026-10-12 feedy używane na produkcji lokalnej były ważne
  do 2026-11-09 (Warszawa do 2026-11-11), więc **trzeba je odświeżyć przed użyciem**
  (`scripts/README-refresh.md`, `scripts/check_gtfs_freshness.py`). Rekordy cen mają pola
  `zrodlo_url`, `data_weryfikacji` i `price_verified`; pozycje z `price_verified: false` nie
  zostały potwierdzone w źródle. Weryfikacje wykonywano głównie w październiku 2026.
- **Użycie AI:** kod, testy, tłumaczenia, część researchu źródeł i komunikaty commitów powstały
  przy dużym udziale narzędzi AI (Claude, Gemini). Dane z researchu AI oznaczono jako
  „wg Gemini, niezweryfikowane niezależnie”, dopóki nie sprawdzono ich w źródle pierwotnym.
- **Licencja kodu:** All Rights Reserved (patrz [`LICENSE`](LICENSE)): kod można oglądać w celu oceny
  portfolio, nie wolno go kopiować, modyfikować, redystrybuować ani używać komercyjnie bez zgody autora.
  Dane zewnętrzne zostają na swoich licencjach ([`DATA_SOURCES.md`](DATA_SOURCES.md)).
- **Licencje danych:** feedy i dane zewnętrzne mają własne licencje (m.in. CC BY 4.0,
  DL-DE-BY-2.0, ODbL dla OSM); zobacz sekcję „Sesja 1: dane”. Repozytorium nie zawiera
  oryginałów PDF cenników przewoźników; źródła są podane linkami.


## Odtworzenie środowiska od zera (krok po kroku)

Wymagania: Python 3.11+, Docker Desktop (z WSL2 na Windows), git, **min. 40 GB wolnego dysku**,
**RAM: ok. 10 GB dla WSL2/Dockera** (import OSM przy domyślnym limicie padał na brak pamięci;
przykład `.wslconfig` w `motis/DE-FULL-CITY-GTFS-NOTES.md`). Pobranie danych to kilka GB (OSM Polski
i NRW; pełne Niemcy ok. 7 GB tylko w wariancie `docker-compose.de-full*.yml`).

1. `python -m venv venv`, aktywacja, `pip install -r requirements.txt` (do testów też `requirements-dev.txt`).
2. `python scripts/fetch_data.py`: pobiera feedy GTFS i pliki OSM do `data/` (lista źródeł i licencji:
   [`DATA_SOURCES.md`](DATA_SOURCES.md)). Jeśli któryś adres przestał działać, sprawdź go w tym pliku.
3. `scripts/merge_osm.sh`: skleja OSM Polski i NRW w `data/osm/poland-nrw-latest.osm.pbf`, którego
   oczekuje `motis/config.yml` (wymaga `osmium-tool` lub Dockera; wariant z Dockerem niesprawdzony).
4. `scripts/run_motis.sh import` (Windows: `scripts\run_motis.ps1 import`): budowa indeksu MOTIS w
   wolumenie Dockera, zwykle od kilkudziesięciu minut do ponad godziny. Potem
   `scripts/run_motis.sh server` (API MOTIS na `http://localhost:8080`).
5. API: `uvicorn api.main:app --reload`; interfejs: `python -m streamlit run app.py`
   (`http://localhost:8501`); wersja konsolowa: `python demo.py`.
6. Testy: `pytest` (nie wymagają Dockera ani tokena; testy z MOTIS pomijają się same).
7. **Odświeżanie danych:** feedy GTFS wygasają (gtfs.de po kilku dniach, inne po tygodniach/miesiącach).
   `python scripts/check_gtfs_freshness.py` sprawdza daty ważności; odświeżenie MOTIS na Windows:
   `scripts\refresh_prod.ps1` (instrukcja: [`scripts/README-refresh.md`](scripts/README-refresh.md)).
   Ceny i ulgi w `fares/data/*.json` poprawia się ręcznie wg pól `zrodlo_url` i `data_weryfikacji`.
8. **Wersje i powtarzalność:** `docker-compose*.yml` mają obraz MOTIS przypięty do digestu (pobrany
   2026-11-12): `ghcr.io/motis-project/motis@sha256:594eff881d4319549387563a28dffb2ac48650df5422325a44a6c2f69f79e9b9`. Własny obraz: zmienna `MOTIS_IMAGE` w `.env`.
   Aktualizacja przypięcia: `docker pull ghcr.io/motis-project/motis:latest`, potem
   `docker image inspect ghcr.io/motis-project/motis:latest --format "{{index .RepoDigests 0}}"` i podmiana
   digestu w `docker-compose*.yml` (szukaj `MOTIS_IMAGE`).

## Czego repozytorium NIE zawiera

Repozytorium jest jedynym źródłem prawdy; wszystko poniżej odtwarza się z niego.

| Rzecz | Status | Jak odtworzyć |
|---|---|---|
| `.env` i tokeny (`TRAVELPAYOUTS_TOKEN`) | **Nie do odzyskania**: sekretów się nie commituje | Wygeneruj nowy token Travelpayouts, wpisz do `.env` (wzór: `.env.example`); opcjonalne, bez niego brak wariantów z lotem |
| Dane GTFS i OSM (`data/`) | Pobierane, nie przechowywane | `python scripts/fetch_data.py` (+ `scripts/fetch_data_extended.py`); feedy to „latest”, więc **poprzednich wersji nie da się odtworzyć**, a link HVV (migawka z datą) może wymagać podmiany |
| Zbudowany indeks MOTIS (wolumeny Dockera) | Odtwarzany, nie przechowywany | `scripts\run_motis.ps1 import` (albo `docker compose` dla używanego wariantu); od kilkudziesięciu minut do ponad godziny |
| Kontenery i wolumeny prod/rollback (`motis-main`, `motis-main-old`, `mw_motis_refresh_*`) | Tylko lokalnie, niepotrzebne | Tworzy je od nowa `scripts\refresh_prod.ps1` z repo; dane ze starego komputera nie są potrzebne |
| PDF-y cenników i snapshoty stron | Usunięte (prawa autorskie) | Źródła są linkowane w `fares/data/*.json` (`zrodlo_url`); ceny weryfikuje się ręcznie |
| Historia PR-ów i issues, komentarze | Nie przeniesione do tego repozytorium | brak |
| Nieoficjalny serwis cen DB (`tools/db-vendo-service`) | Opcjonalny | `npm install && npm start`; DB może go blokować; bez tokena |
| Ludzka weryfikacja cen | Ma datę, starzeje się | `data_weryfikacji` w rekordzie; `price_verified: false` = niezweryfikowane |

### Wariant „produkcyjny” (feedy miejskie Warszawy/Krakowa/Hamburga/Monachium/Kolonii, OSM całych Niemiec)

```
python scripts/fetch_data.py
python scripts/fetch_data_extended.py        # OSM Niemiec + feedy HVV/MVV/VRS (kilka GB)
bash scripts/merge_osm.sh germany            # -> data/osm/poland-germany-latest.osm.pbf (~7 GB)
docker compose -f docker-compose.pl-cities.yml --profile import-pl-cities run --rm motis-import-pl-cities
docker compose -f docker-compose.pl-cities.yml up motis-pl-cities     # MOTIS na http://localhost:8082
```

Aplikację kierujesz na ten MOTIS zmienną `MOTIS_BASE_URL=http://localhost:8082` (PowerShell: `$env:MOTIS_BASE_URL="http://localhost:8082"`).
Późniejsze odświeżenia: `scripts\refresh_prod.ps1` (zob. `scripts/README-refresh.md`).

## Test end-to-end na czystej maszynie

1. Nowy folder: `git clone <repo>`, `cd`, `python -m venv .venv`, aktywacja, `pip install -r requirements.txt -r requirements-dev.txt`.
2. `pytest -q` (oczekiwane ok. 2079 passed, 12 skipped, bez Dockera).
3. `python scripts/fetch_data.py`, potem `bash scripts/merge_osm.sh` (domyślny wariant NRW).
4. Czysty stan Dockera: `docker volume ls` nie powinno listować wolumenu tego projektu (`<folder>_motis-data`); potem `scripts\run_motis.ps1 import`.
5. `scripts\run_motis.ps1 server` (port 8080; zatrzymaj inny kontener na tym porcie).
6. Jedno zapytanie o trasę z datą w okresie ważności feedów: `python demo.py --from "Lublin Dworzec Główny" --to "Gelsenkirchen Hbf" --date <data w ciągu najbliższego tygodnia> --age 25`.
7. Opcjonalnie: `python -m streamlit run app.py` i `uvicorn api.main:app --port 8010`.
8. Jeśli to wszystko działa, nic z oryginalnego komputera nie jest potrzebne.

## Szybki start (od zera)

Pełna instrukcja postawienia projektu lokalnie, krok po kroku. Wymagania: Python 3.11+,
Docker Desktop, git.

1. **Sklonuj repozytorium i wejdź do folderu:**

   ```
   git clone https://github.com/techniksawery/multimodal-fare-planner.git
   cd multimodal-fare-planner
   ```

2. **Stwórz i aktywuj wirtualne środowisko:**

   ```
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Zainstaluj zależności** (plus `pytest` i `httpx`, które nie są w `requirements.txt`, ale są
   potrzebne do odpalenia testów — `httpx` tylko dla `tests/test_api.py`, patrz sekcja "API"):

   ```
   pip install -r requirements.txt
   pip install pytest httpx
   ```

4. **(Opcjonalnie) skonfiguruj token do cen lotów** — skopiuj `.env.example` do `.env` i wpisz
   własny `TRAVELPAYOUTS_TOKEN` (zob. [`flights/README.md`](flights/README.md)). Bez tego kroku
   wszystko inne działa, warianty z lotem po prostu się nie pojawią.

5. **Ściągnij dane GTFS/OSM** (Sesja 1 poniżej):

   ```
   python scripts/fetch_data.py
   ```

   Na Windows, jeśli skrypt zgłasza błąd kodowania, odpal go z `PYTHONIOENCODING=utf-8`. Skrypt
   sam dogrywa nagłówek `User-Agent` wymagany przez mkuran.pl — nie trzeba niczego dodawać
   ręcznie.

6. **Postaw silnik routingu MOTIS w Dockerze** (Sesja 2 poniżej; wymaga uruchomionego Docker
   Desktop):

   ```
   scripts/run_motis.sh import   # Git Bash / WSL — buduje dane w wolumenie Dockera
   scripts/run_motis.sh server   # startuje serwer HTTP na http://localhost:8080
   ```

   W czystym PowerShell użyj `scripts\run_motis.ps1 import` / `server` (ten sam dwuetapowy
   schemat: najpierw `import`, potem `server`).

7. **Uruchom testy** (opcjonalnie, ale warto sprawdzić, że wszystko jest poskładane):

   ```
   pytest
   ```

   Testy `routing`/`fares`/`flights` mockują zewnętrzne usługi (MOTIS, Travelpayouts), więc
   przechodzą bez uruchomionego Dockera i bez tokena.

8. **Odpal aplikację** — przy działającym MOTIS z kroku 6, w nowym terminalu (z aktywnym
   `venv`):

   ```
   python -m streamlit run app.py
   ```

   Otworzy się w przeglądarce (domyślnie `http://localhost:8501`). Alternatywnie, demo z linii
   komend bez frontendu:

   ```
   python demo.py
   ```

### Języki interfejsu

Interfejs `app.py` jest dostępny po polsku (domyślnie), angielsku, niemiecku, hiszpańsku,
francusku i holendersku; język przełączasz przełącznikiem nad tytułem. Teksty UI siedzą w
słownikach `i18n/<kod>.py` (`t("klucz", pole=…)`); `tests/test_i18n.py` pilnuje kompletu kluczy
i spójnych pól `{…}` we wszystkich językach. Nowy język = nowy plik w `i18n/` + wpis w
`i18n/__init__.py`. Tłumaczona jest tylko warstwa prezentacji (ceny i taryfy się nie zmieniają);
teksty generowane przez moduły domenowe (ostrzeżenia dla cudzoziemców, podpowiedzi BahnCard,
powody przesiadek, nazwy atrakcji i ich opisy, nazwy wariantów) zostają po polsku.

### Pola „Skąd” i „Dokąd”: podpowiedzi i nazwy miejsc w każdym języku

Podpowiedzi pojawiają się podczas pisania (komponent `streamlit-searchbox`: natywny `st.selectbox`
filtruje tylko gotową listę i nie przekazuje wpisywanego tekstu do serwera). Geokoder MOTIS dostaje
zapytanie dopiero od 3 znaków, po 300 ms od ostatniego znaku, a ten sam tekst jest pamiętany przez
5 minut. Przycisk „Szukaj połączeń” działa też bez wybrania podpowiedzi (bierze najlepsze
dopasowanie).

Miasta mają nazwy w PL/EN/DE/ES/FR/NL w `places/aliases.json`: wpisanie dowolnej z nich znajduje to
samo miejsce, a w podpowiedziach i nagłówku wyniku widać nazwę w języku interfejsu i lokalną obok
(„Cologne · Köln”). MOTIS nie zwraca nazw alternatywnych (odpowiedź `/api/v1/geocode` ma jedno pole
`name`; parametr `language` zmienia tylko język tej jednej nazwy), dlatego jest własna tablica.
Plik jest oznaczony jako niezweryfikowany, dopóki `python scripts/build_place_aliases.py --check`
(potrzebny dostęp do query.wikidata.org) nie potwierdzi go wobec Wikidata; `--write` zapisuje QID
i status.

Szczegóły każdego kroku, w tym pełna lista źródeł danych, pochodzenie cen i znane ograniczenia,
są rozpisane w sekcjach „Sesja 1–6” poniżej.

## API (FastAPI)

Logika routingu i taryf (`routing/`, `fares/`) jest też dostępna jako samodzielne REST API w
`api/`, niezależne od Streamlita — żeby dało się podłączyć inny frontend (appkę mobilną, inny
klient webowy) bez przepisywania silnika. `app.py` (Streamlit) woła tę samą logikę przez import
(`routing/search_service.py`), nie przez HTTP — to jedna implementacja, dwie fasady.

Uruchomienie (wymaga działającego MOTIS z kroku 6 powyżej):

```
uvicorn api.main:app --reload
```

- `GET /health` — health-check, nie dotyka MOTIS.
- `POST /route` — wyszukuje warianty trasy adres → adres + rekomendacje. Przykład:

  ```
  curl -X POST http://localhost:8000/route -H "Content-Type: application/json" -d '{
    "origin": "Krakowskie Przedmieście 50, Lublin",
    "destination": "Bahnhofstraße, Gelsenkirchen",
    "date": "2026-10-05",
    "discounts": {"bahncard": "50", "pkp_ulga_kod": "ulgowy"}
  }'
  ```

  Gdy w dniu zapytania nic nie jedzie, a MOTIS ma połączenia tylko w innych dniach, odpowiedź ma
  puste `built`/`recommendations` i listę `other_day_variants` (maks. 3 warianty, do 3 dni od
  zapytanej daty; każdy z `date`, `days_offset` i `label` „… to NIE jest dzień zapytania”) —
  patrz [`routing/README.md`](routing/README.md#najbliższe-połączenia-w-innym-dniu-pusty-wynik).

- `GET /attractions` — katalog rekomendowanych miejsc i atrakcji (parametry opcjonalne: `city`, `category`).
- `GET /city-cards` — karty miejskie dla danego miasta (parametr opcjonalny: `city`).
- `POST /city-cards/evaluate` — kalkulator opłacalności kart miejskich dla wskazanych atrakcji i szacowanego kosztu transportu.

Interaktywna dokumentacja (Swagger UI) pod `http://localhost:8000/docs` po starcie serwera.

Testy (mockują MOTIS na poziomie `routing/variants.py`, nie wymagają działającego serwera):
`pytest tests/test_api.py tests/test_other_day.py`.


### Ponowne uruchomienie (po pierwszym razie)

Jeśli dane GTFS/OSM i wolumen MOTIS-a (`motis-data`) już istnieją, nie trzeba powtarzać całego
setupu — wystarczy:

1. **Aktywuj wirtualne środowisko** (w folderze repo):

   ```
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

2. **Odpal Docker Desktop** (jeśli nie działa) i uruchom serwer MOTIS — bez kroku `import`,
   dane z poprzedniego importu są już w wolumenie Dockera:

   ```
   scripts/run_motis.sh server   # Git Bash / WSL
   # albo w PowerShell:
   powershell -File scripts\run_motis.ps1 server
   ```

3. **W nowym terminalu** (z aktywnym `venv`) odpal frontend:

   ```
   python -m streamlit run app.py
   ```

Krok `import` (ponowne ściąganie danych, `fetch_data.py`) jest potrzebny tylko wtedy, gdy
chcesz odświeżyć dane GTFS/OSM albo zmieniłeś `motis/config.yml`.

**Wygląd.** Styl interfejsu wg `research/ui-styl.md` (wersja 2) siedzi w `.streamlit/config.toml`
(kolory motywu) i `ui_style.py` (CSS: plakietki statusu ceny, karty, przycisk „Szukaj połączeń”).
Jasna paleta jest podstawą, ciemna jest do wyboru w menu ⋮ w prawym górnym rogu
(System / Light / Dark); przy ustawieniu „System” ciemny system operacyjny daje ciemną paletę.
Motyw wymaga Streamlita z sekcjami `[theme.dark]` i CSS `light-dark()` (sprawdzone na 1.65).

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
| `data/gtfs/pl/warsaw.zip` | ZTM Warszawa, mkuran.pl, warunki ZTM + ODbL (atrybucja: zob. `motis/PL-CITIES-GTFS-NOTES.md`) |
| `data/gtfs/pl/krakow_{a,m,t}.zip` | ZTP Kraków, licencja niepotwierdzona (tylko test) |
| `data/osm/poland-latest.osm.pbf` | Geofabrik |
| `data/osm/nordrhein-westfalen-latest.osm.pbf` | Geofabrik |

Potem sprawdza sumy MD5 plików OSM i waliduje feedy GTFS (`scripts/check_gtfs.py`):
kompletność archiwum, wymagane pliki, liczby przystanków i kursów, zakres dat,
spójność kluczy. Raport ląduje w `data/gtfs/REPORT.txt`.

**Lokalny transport miejski Hamburga (HVV), Monachium (MVV) i Kolonii (VRS)** — dociągnięcie
tych feedów do MOTIS NIE jest (jeszcze) częścią `scripts/fetch_data.py`, bo wymaga pełnego OSM
Niemiec (PR #46) i osobnego importu. Komendy do pobrania/importu/przełączenia (z licencjami:
HVV = DL-DE-BY-2.0, MVV i VRS = CC BY 4.0) są w
[`motis/DE-FULL-CITY-GTFS-NOTES.md`](motis/DE-FULL-CITY-GTFS-NOTES.md).

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
("szacunek"), tak jak w module `fares/`. Jako lot bezpośredni liczy się tylko wpis z kluczem "0"
(liczba przesiadek) w `/v1/prices/cheap`; gdy go brak, cena to zgrubny szacunek z dopiskiem
"cena niepotwierdzona", a nie bilet z przesiadkami (szczegóły i stan weryfikacji dokumentacji w
[`flights/README.md`](flights/README.md)).

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
zmianę pociągu/lotu) i wybiera rekomendacje (najtańsza, najszybsza, najmniej przesiadek,
najlepszy stosunek cena/czas, najlepszy kompromis, najszybsza z Twoimi ulgami — każda też w
wersji bezpiecznej, bez ryzykownych przesiadek). Szczegóły metody, ograniczenia zakresu i
założenia —
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

## Sesja 1c: transport lokalny NRW (gtfs.de nv_free)

Feed RV jest w 100% kolejowy, więc adresy z dala od stacji (np. Gelsenkirchen-Buer) dawały tylko
długi marsz. Dodano `gtfs/de/de_nv.zip` (gtfs.de `nv_free`, 287 MB: tramwaje, Stadtbahn/U-Bahn,
autobusy całych Niemiec) jako dataset `denv` w `motis/config.yml`. Po zmianie trzeba powtórzyć
`scripts/run_motis.ps1 import` (import z tym feedem trwa dłużej niż wcześniej).

## Sesja 6: alternatywne węzły przesiadkowe/miasta

Silnik potrafi teraz jawnie sprawdzić trasy kolejowe przez alternatywne miasto graniczne/węzeł
(zamiast polegać wyłącznie na tym, co MOTIS zwróci dla jednego zapytania origin→destination)
oraz warianty zaczynające/kończące się na innym dworcu w tym samym mieście. Huby lot↔kolej były
już listą kandydatów od Sesji 4 — dodanie alternatywnego lotniska to tylko dopisanie kolejnego
`HubConfig`. Szczegóły i nowe API (`AlternativeStop`, `via_hub_stops`,
`alternative_origin_stops`/`alternative_destination_stops` w `generate_variants`) —
[`routing/README.md`](routing/README.md#alternatywne-huby-węzły-przesiadkowe-sesja-6).
Konkretne `stopId` dla alternatyw trzeba dobrać ręcznie (np. geocodingiem MOTIS) — to nie jest
jeszcze podłączone do `demo.py`/`app.py` z gotowymi przykładami, bo wymaga zweryfikowania
prawdziwych identyfikatorów przystanków na uruchomionym lokalnie MOTIS.

Testy: `pytest tests/test_routing.py` (nowe przypadki dla `build_rail_via_stop_variant` i
dedup w `generate_variants`).

## Sesja 7: atrakcje i karty miejskie (City Cards)

Moduł `attractions/` integruje katalog rekomendowanych miejsc z podziałem na kategorie
(sport i stadiony, turystyka i zabytki, rozrywka, gastronomia, natura) dla miast docelowych
(m.in. Berlin, Gelsenkirchen & Zagłębie Ruhry, Kraków, Lublin) oraz kalkulator opłacalności
zakupu oficjalnych kart miejskich (Berlin WelcomeCard, WelcomeCard Ruhr, Kraków Card).

Silnik ocenia, czy zakup karty zwraca się przy wybranym zestawie atrakcji oraz darmowym
transporcie miejskim (np. VRR / Berlin AB / Kraków strefa I+II), wyliczając realne oszczędności netto.

Zniżka karty > 0% jest liczona tylko z polem źródła (`source_url` + `verified_date`); zniżka bez źródła
= 0% + flaga niezweryfikowanej zniżki w wycenie (zniżki bez źródła w 6 miastach wyzerowano 2026-10-12;
10 z nich przywrócono ze źródłem wg raportu `research/zrodla-znizek-kart.md`, 6 zostaje 0% — patrz
`attractions/README.md`). Źródła strefy C (BER) w `fares/data/bvg_berlin.json` (`zrodlo_strefa_c_ber`:
bvg.de i vbb.de, 2026-10-12). Wszystkie te źródła są wg Gemini, niezweryfikowane niezależnie.

Szczegóły: [`attractions/README.md`](attractions/README.md).

Testy: `pytest tests/test_attractions.py tests/test_znizki_bez_zrodla.py`.

## Code style


Formatowanie: `black` (line length 100), lint: `ruff` (reguły i wyjątki w `pyproject.toml`).

```
pip install -r requirements-dev.txt
black .
ruff check . --fix
pytest
```

Opcjonalnie pre-commit (odpala black+ruff automatycznie przy każdym commicie):

```
pre-commit install
```
