# Data sources and licences / Źródła danych i licencje

The source code is **All Rights Reserved** (see [LICENSE](LICENSE)). The data below is **not** covered by
that licence; each source keeps its own terms. Data files are downloaded by scripts, not stored in the repo.
Kod jest objęty „All Rights Reserved”; poniższe dane mają własne licencje i są pobierane skryptami.

| Data | Source (URL) | Licence / terms | Fetched by |
|---|---|---|---|
| Polish rail GTFS | https://mkuran.pl/gtfs/polish_trains.zip | PKP PLK and Koleje Mazowieckie public-sector data terms (Polish), see https://mkuran.pl/gtfs/ (read 2026-11-12; linked terms not reviewed in full) | `scripts/fetch_data.py` |
| German long-distance GTFS (FV) | https://download.gtfs.de/germany/fv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| German regional GTFS (RV) | https://download.gtfs.de/germany/rv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| German local GTFS (NV) | https://download.gtfs.de/germany/nv_free/latest.zip | CC BY 4.0 (gtfs.de) | `scripts/fetch_data.py` |
| ZTM Lublin GTFS | https://mkuran.pl/gtfs/lublin.zip | CC0 | `scripts/fetch_data.py` |
| ZTM Warszawa GTFS | https://mkuran.pl/gtfs/warsaw.zip | ZTM terms + ODbL (see `motis/PL-CITIES-GTFS-NOTES.md`) | `scripts/fetch_data.py` |
| ZTP Kraków GTFS | https://gtfs.ztp.krakow.pl/ | licence unconfirmed: test only, do not redistribute; NOT downloaded by default | opt-in: `scripts/fetch_data_extended.py --krakow` |
| Hamburg / Munich / Cologne GTFS | see `motis/DE-FULL-CITY-GTFS-NOTES.md` | DL-DE-BY-2.0 / CC BY 4.0 / CC BY 4.0 | manual (notes) |
| OpenStreetMap extracts | https://download.geofabrik.de/ | ODbL, © OpenStreetMap contributors | `scripts/fetch_data.py` |
| Fares, discounts, attractions, city cards | per-record `zrodlo_url` + `data_weryfikacji` in `fares/data/*.json`, `attractions/data/*.json` | facts with source links; operators' terms apply; entries with `price_verified: false` are unverified estimates | maintained by hand |
| PKP Intercity "Super Promo International" prices | URL in `fares/data/pkp_spi_pl_de.json` (`_zrodlo_url`) | only numbers/rules are stored; full price-list text and PDF are not in the repo | maintained by hand |

Some research notes were produced with AI assistance and are marked "per Gemini, not independently verified"
until checked against the primary source.

## Attribution required by the licences above

- OpenStreetMap: "© OpenStreetMap contributors" linked to https://www.openstreetmap.org/copyright (ODbL), wherever routing results or maps are shown publicly.
- Warsaw GTFS: ZTM Warszawa, Mikołaj Kuranowski, OpenStreetMap contributors (see `attributions.txt` in the feed).
- gtfs.de feeds: CC BY 4.0 (credit "gtfs.de"); HVV: DL-DE-BY-2.0; MVV, VRS: CC BY 4.0.
