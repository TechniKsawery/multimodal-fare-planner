Polski | English: [English version](PL-CITIES-GTFS-NOTES.md)

# Warszawa i Kraków (lokalne GTFS) w MOTIS + odświeżanie feedów

Status: **konfiguracja przygotowana, import i test na żywo robi sesja Remote Control** (kontener chmurowy blokuje hosty `mkuran.pl`/`gtfs.ztp.krakow.pl`, sprawdzone 2026-10-11: proxy 403). Produkcja (`multimodalnawyszukiwarka_motis-data-de-full-city-gtfs`, port 8080) i rollback nietknięte. Test: osobny wolumen `motis-data-pl-cities`, port 8082.

## Źródła (sprawdzone 2026-10-11)

| Miasto | Plik | Licencja | Uwagi |
|---|---|---|---|
| Warszawa | https://mkuran.pl/gtfs/warsaw.zip | Warunki ZTM Warszawa + ODbL dla shapes autobusów (https://mkuran.pl/gtfs/) | Atrybucja wymagana: ZTM Warszawa, Mikołaj Kuranowski, współtwórcy OpenStreetMap (zob. `attributions.txt` w zipie). Częstotliwość aktualizacji niepodana. |
| Kraków | https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip, `_M.zip`, `_T.zip` | **NIEZNANA** — strona ZTP nie podaje licencji, Mobility Database odsyła tylko do https://ztp.krakow.pl | Znaczenie liter A/M/T niepotwierdzone (A = autobus wg Mobility Database mdb-1326). Aktualizacja plików 2026-10-08/10-11. |

**Do decyzji Ksaviego:** licencja Krakowa jest niepotwierdzona. Do czasu sprawdzenia regulaminu ZTP (lub pytania do ZTP) feed jest używany tylko do testu, nie do produkcji.

Atrybucja do README/stopki: `Dane GTFS Warszawa: ZTM Warszawa, przetworzone przez M. Kuranowskiego (mkuran.pl), shapes © współtwórcy OpenStreetMap (ODbL).`

## Uruchomienie testu (PC, PowerShell)

```powershell
python scripts\fetch_data.py          # dociąga warsaw do data\gtfs\pl; Kraków tylko z: python scripts\fetch_data_extended.py --krakow (config.pl-cities-krakow-test.yml)
docker compose -f docker-compose.pl-cities.yml --profile import-pl-cities run --rm motis-import-pl-cities
docker compose -f docker-compose.pl-cities.yml up -d motis-pl-cities
```
Uwaga na miejsce na C: (ok. 12 GB wolnego) i RAM importu (`docker stats`).

## Odświeżanie

- `.github/workflows/gtfs_freshness.yml` — codziennie pobiera wszystkie feedy z `scripts/fetch_data.py`, liczy ważność (`scripts/check_gtfs_freshness.py`) i otwiera/uzupełnia issue z etykietą `gtfs-expiry`, gdy któryś wygasa za <3 dni lub nie da się go pobrać.
- `scripts/refresh_motis.ps1` — odświeżenie danych i import do wolumenu testowego; można wpiąć w Harmonogram zadań Windows (komenda w nagłówku skryptu). Przełączenie produkcji dopiero po zgodzie.
- Darmowy gtfs.de ma ważność 7 dni, więc odświeżanie co najmniej raz w tygodniu.

## Licencja Krakowa: co sprawdzono (2026-10-11)

Nic jednoznacznego o GTFS. Sprawdzone strony (bez żadnej klauzuli licencyjnej dla GTFS): https://gtfs.ztp.krakow.pl/ , https://ztp.krakow.pl/dane-otwarte (tylko stopka "© 2021–2026 ZTP Kraków"), https://ztpk-gmk-2.hub.arcgis.com/ (ArcGIS Hub, bez treści licencji), komunikat https://convention.krakow.pl/english/news/284578,2357,komunikat,_bus_stops__bicycle_infrastructure_and_p+r_sites___open_data_published_by_the_public_transport_authority.html (mówi o GTFS i danych do "analiz i badań", licencji nie podaje), Mobility Database mdb-1326 (odsyła do https://ztp.krakow.pl).
Jedyny trop: katalog MSIP https://msip.krakow.pl/dataset/2963 ("ZTP - Komunikacja Miejska i Rowerowa") pisze "Wykorzystanie danych zgodne z regulaminem MSIP" — bez nazwanej licencji; sam regulamin (zarządzenie Prezydenta, BIP: https://bip.krakow.pl/zarzadzenie/2025/1742/w_sprawie_zasad_funkcjonowania_Miejskiego_Systemu_Informacji_Przestrzennej_Miasta_Krakowa.html) nie został przeczytany, a nie ma pewności, że obejmuje GTFS. Transitland nie dało się odczytać (robots).
Wniosek: licencja i zgoda na użycie komercyjne NIEPOTWIERDZONE. Zostaje pytanie do ZTP.
