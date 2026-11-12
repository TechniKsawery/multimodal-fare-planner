# Multimodal Fare Planner

🇵🇱 Polska wersja · 🇺🇸 [English version → README.md](README.md)

**Projekt portfolio do wyszukiwania multimodalnych podróży między Polską a Niemcami i szacowania ich rzeczywistego kosztu.**

Aplikacja łączy publiczne dane rozkładowe, trasy piesze, taryfy kolejowe i miejskie, profile pasażerów, ulgi, karty miejskie, atrakcje, autobusy oraz opcjonalne loty. Zamiast zwracać wyłącznie trasę, pokazuje szacowany koszt i założenia użyte do jego obliczenia.

> **Prototyp portfolio — nie jest komercyjnym serwisem rezerwacyjnym.** Ceny są szacunkami, a nie ofertami. Przed zakupem zawsze sprawdź końcową cenę u przewoźnika.

## Co pokazuje projekt

- projektowanie aplikacji Python z backendem FastAPI i interfejsem Streamlit
- routing multimodalny z użyciem open-source'owego silnika [MOTIS](https://github.com/motis-project/motis)
- pobieranie, walidacja i odświeżanie danych GTFS oraz OpenStreetMap
- modelowanie taryf kolejowych, komunikacji regionalnej i miejskiej, ulg oraz profili pasażerów
- rozdzielenie routingu, wyceny, źródeł danych i warstwy prezentacji
- powtarzalna infrastruktura lokalna oparta na Dockerze
- testy automatyczne i weryfikacja end-to-end

## Aktualny zakres

| Obszar | Uwzględniono | Istotne ograniczenie |
|---|---|---|
| Geografia | Polska i Niemcy | Inne kraje nie mają obecnie danych rozkładowych ani taryf |
| Transport | Kolej, wybrana komunikacja miejska, FlixBus i opcjonalne loty | Zakres zależy od dostępnych feedów i API |
| Ceny | PKP Intercity, wybrane taryfy polskie i niemieckie, taryfy miejskie, ulgi i karty | Szacunki mogą być niepełne lub nieaktualne |
| Profile pasażerów | Dorosły, student, senior, dziecko oraz wybrane opcje BahnCard/PKP/VRR | Wielu pasażerów i część kart nie jest modelowana |
| Dodatki | Wybrane karty miejskie i 82 atrakcje w 10 miastach | Ceny są orientacyjne i nie zawsze niezależnie zweryfikowane |
| Rezerwacja | Wyszukiwanie trasy i szacowanie ceny | Zakup i płatność nie są zaimplementowane |

Konfiguracja domyślna obejmuje polską kolej, niemiecką kolej dalekobieżną i regionalną, Lublin oraz NRW. Wariant zbliżony do produkcyjnego dodaje Warszawę, Hamburg, Monachium i Kolonię/Bonn. Lista feedów, licencji i informacji o aktualności znajduje się w [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Architektura

```text
Interfejs Streamlit / CLI
          ↓
Serwis FastAPI
          ↓
Routing i normalizacja połączeń
          ↓
MOTIS + GTFS + OpenStreetMap
          ↓
Kalkulatory taryf + ulgi + karty miejskie
```

Mapa repozytorium:

- `routing/` — klient MOTIS, przetwarzanie połączeń i orkiestracja wyceny
- `fares/` — kalkulatory taryf, ulgi i dane ze źródłami
- `attractions/` i `places/` — atrakcje, karty miejskie i wybór miejsc
- `api/` — aplikacja FastAPI
- `app.py` — interfejs Streamlit
- `motis/` — konfiguracja silnika i notatki wdrożeniowe
- `scripts/` — pobieranie danych, walidacja, odświeżanie i narzędzia powtarzalności
- `tests/` — testy jednostkowe, integracyjne i API

## Szybki start

### Wymagania

Python 3.11+, Docker Desktop, git oraz co najmniej 40 GB wolnego miejsca. Pełny import wymaga około 10 GB pamięci dostępnej dla Dockera/WSL2.

```bash
git clone https://github.com/TechniKsawery/multimodal-fare-planner.git
cd multimodal-fare-planner
python -m venv .venv
```

Aktywuj środowisko i zainstaluj zależności:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt -r requirements-dev.txt
```

Pobierz aktualne dane GTFS i OSM, zbuduj indeks MOTIS i uruchom usługi:

```bash
python scripts/fetch_data.py
bash scripts/merge_osm.sh
bash scripts/run_motis.sh import
bash scripts/run_motis.sh server
```

W osobnych terminalach:

```bash
uvicorn api.main:app --reload
python -m streamlit run app.py
```

Interfejs jest dostępny pod `http://localhost:8501`, API pod `http://localhost:8000`, a MOTIS pod `http://localhost:8080`.

Na Windows użyj odpowiedników PowerShell z katalogu `scripts/`. Dla większej konfiguracji Polska + miasta zobacz `docker-compose.pl-cities.yml` oraz szczegółową instrukcję odświeżania w `scripts/README-refresh.md`.

### Opcjonalne ceny lotów

Skopiuj `.env.example` do `.env` i ustaw `TRAVELPAYOUTS_TOKEN`. Bez tokena pozostałe funkcje działają, a warianty z lotami są pomijane.

### Testy

```bash
pytest -q
```

Testy nie wymagają Dockera ani tokena API; testy wymagające uruchomionego MOTIS-a pomijają się automatycznie.

## Aktualność danych i powtarzalność

Pliki GTFS i OSM są pobierane lokalnie i celowo nie są commitowane. Feedy wygasają, dlatego przed użyciem aplikacji odśwież dane:

```bash
python scripts/check_gtfs_freshness.py
```

Rekordy taryf zawierają `zrodlo_url`, `data_weryfikacji` i `price_verified`. Wartość `price_verified: false` oznacza, że taryfa nie została potwierdzona w źródle pierwotnym. Repozytorium nie zawiera PDF-ów cenników przewoźników, kopii feedów, wycinków OSM ani zbudowanego indeksu MOTIS.

Weryfikacja end-to-end na czystej maszynie została wykonana 2026-11-12 na Windows/Python 3.13 i obejmowała testy, walidację danych, scalenie OSM, import MOTIS, zapytania API oraz wyszukiwanie w Streamlit. Konkretna migawka danych nie jest trwała — aktualne feedy trzeba pobierać ponownie.

## Informacje prawne i licencje

- To niezależny projekt, niepowiązany z PKP Intercity, Deutsche Bahn, FlixBus, VRR, HVV, MVV, VRS, ZTM ani operatorami atrakcji.
- Ceny, ulgi i rozkłady są szacunkami i mogą być błędne lub nieaktualne. Oprogramowanie nie sprzedaje ani nie rezerwuje biletów.
- Dane OpenStreetMap wymagają atrybucji zgodnie z [ODbL](https://www.openstreetmap.org/copyright). Dostawcy GTFS zachowują własne licencje; szczegóły są w [`DATA_SOURCES.md`](DATA_SOURCES.md).
- Kod projektu jest objęty licencją **All Rights Reserved**. Oglądanie go w celu oceny portfolio jest dozwolone, ale kopiowanie, modyfikowanie, redystrybucja lub użycie komercyjne wymagają pisemnej zgody. Zobacz [`LICENSE`](LICENSE).
- Opcjonalne nieoficjalne interfejsy przewoźników są domyślnie wyłączone i należy ich używać wyłącznie do prywatnych testów, jeśli pozwalają na to regulaminy.
- Kod, testy, tłumaczenia i część researchu powstały przy znaczącym wsparciu narzędzi AI. Research wygenerowany przez AI uznawano za niezweryfikowany do czasu sprawdzenia w źródłach pierwotnych.

W sprawach bezpieczeństwa zobacz [`SECURITY.md`](SECURITY.md).
