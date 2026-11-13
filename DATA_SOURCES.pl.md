Polski | English: [English version](DATA_SOURCES.md)

# Źródła danych i licencje

Oryginalny kod i dokumentacja są objęte licencją
[PolyForm Noncommercial License 1.0.0](LICENSE). Poniższe dane nie są objęte
licencją projektu; każde źródło zachowuje własne warunki. Pliki danych są
pobierane przez skrypty, a nie przechowywane w repozytorium.

| Dane | Źródło (URL) | Licencja / warunki | Pobierane przez |
|---|---|---|---|
| Polski GTFS kolejowy | https://mkuran.pl/gtfs/polish_trains.zip | Warunki wykorzystania danych sektora publicznego PKP PLK i Kolei Mazowieckich (po polsku), zob. https://mkuran.pl/gtfs/ (odczyt 2026-11-12; powiązane warunki nie zostały w całości przeanalizowane) | `scripts/fetch_data.py` |
| Niemiecki GTFS dalekobieżny (FV) | https://download.gtfs.de/germany/fv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| Niemiecki GTFS regionalny (RV) | https://download.gtfs.de/germany/rv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| Niemiecki GTFS lokalny (NV) | https://download.gtfs.de/germany/nv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| GTFS ZTM Lublin | https://mkuran.pl/gtfs/lublin.zip | CC0 | `scripts/fetch_data.py` |
| GTFS ZTM Warszawa | https://mkuran.pl/gtfs/warsaw.zip | Warunki ZTM + ODbL (zob. `motis/PL-CITIES-GTFS-NOTES.md`) | `scripts/fetch_data.py` |
| GTFS ZTP Kraków | https://gtfs.ztp.krakow.pl/ | licencja niepotwierdzona: tylko testy, nie redystrybuować; domyślnie NIE jest pobierany | opcjonalnie: `scripts/fetch_data_extended.py --krakow` |
| GTFS Hamburg / Monachium / Kolonii | zob. `motis/DE-FULL-CITY-GTFS-NOTES.md` | DL-DE-BY-2.0 / CC BY 4.0 / CC BY 4.0 | ręcznie (notatki) |
| Wyciągi OpenStreetMap | https://download.geofabrik.de/ | ODbL, © współtwórcy OpenStreetMap | `scripts/fetch_data.py` |
| Taryfy, zniżki, atrakcje, karty miejskie | według rekordu: `zrodlo_url` + `data_weryfikacji` w `fares/data/*.json`, `attractions/data/*.json` | fakty ze źródłami; obowiązują warunki operatorów; wpisy z `price_verified: false` to niezweryfikowane szacunki | utrzymywane ręcznie |
| Ceny PKP Intercity „Super Promo International” | URL w `fares/data/pkp_spi_pl_de.json` (`_zrodlo_url`) | przechowywane są tylko liczby i zasady; pełny tekst cennika oraz PDF nie znajdują się w repozytorium | utrzymywane ręcznie |

Niektóre notatki badawcze powstały z pomocą AI i są oznaczone jako „wg Gemini, niezweryfikowane
niezależnie” do czasu sprawdzenia ich w źródle pierwotnym.

## Wymagane przypisanie autorstwa według powyższych licencji

- OpenStreetMap: „© współtwórcy OpenStreetMap” z odnośnikiem do https://www.openstreetmap.org/copyright (ODbL), wszędzie tam, gdzie publicznie prezentowane są wyniki trasowania lub mapy.
- GTFS Warszawy: ZTM Warszawa, Mikołaj Kuranowski, współtwórcy OpenStreetMap (zob. `attributions.txt` w feedzie).
- Feedy gtfs.de: CC BY 4.0 (podziękowanie „gtfs.de”); HVV: DL-DE-BY-2.0; MVV, VRS: CC BY 4.0.
