# Audyt kalkulatora cen DB i tłumaczeń

Data audytu: 2026-10-14. Stan repozytorium: `main` @ `8c3d62d`. Zakres: `fares/` (kod i `fares/data/*.json`),
`routing/pricing.py`, `routing/card_suggestions.py`, `app.py`, `ui_helpers.py`, `i18n/`, `attractions/`, `places/`.

**Metoda.** Audyt jest statyczny: czytanie kodu i danych oraz liczenie skryptami (parser AST i `json`) na plikach z repo.
Niczego nie zmieniałem w kodzie ani w danych. Nie sprawdzałem aktualnych cen na bahn.de ani na innych stronach
przewoźników, bo audyt dotyczy tylko tego, co jest w repo. Daty weryfikacji pochodzą z pól w plikach JSON,
z `fares/README.md` albo z docstringów. "Ma test" oznacza, że w `tests/` jest test danego zachowania.
Testów nie uruchamiałem: w środowisku audytu nie ma `pytest` ani `streamlit`.
Gdzie czegoś nie ma w kodzie ani w danych, wpisuję **brak**.

Oznaczenia cen w UI (`ui_helpers.py::leg_price_status`): `OFFICIAL` = plakietka "OFICJALNA TARYFA", `ESTIMATE` = "SZACUNEK",
`NO_PRICE` = "BRAK CENY". `OFFICIAL` wymaga jednocześnie `price_type == "oficjalna_taryfa"` i `price_verified`.

---

## Tabela 1. Poziomy cen (rodzaje biletów DB)

| Rodzaj biletu | Obsługiwany? | Skąd kwota | Data weryfikacji lub informacja o szacunku | Oznaczenie w wyniku i UI |
|---|---|---|---|---|
| **Super Sparpreis** (krajowy) | **Nie.** Brak kalkulatora i brak kwot. Nazwa występuje tylko w tekstach `_sprawdzono_*` w `fares/data/db_flexpreis.json` (m.in. "Super Sparpreis Young od 4,99 EUR", "Super Sparpreis Senioren 65+ od 15,99 EUR"). Kod z tych kwot nie korzysta. | Brak. Jedyna ścieżka do ceny w okolicy Sparpreis to opcjonalne `UNOFFICIAL_PRICES=1`: `fares/db.py::_unofficial_estimate` bierze z `tools/db-vendo-service` najtańszą cenę (`bestprice: true`) dla daty. Rodzaju taryfy w odpowiedzi nie zapisujemy. | Brak. Ścieżka domyślnie wyłączona (`fares/_unofficial.py::enabled`). | Wyłączona: nie dotyczy. Włączona: `ESTIMATE`, `breakdown["zrodlo"]="nieoficjalne_db_vendo"`, UI "SZACUNEK". Test: `test_db_nieoficjalne_*` (3 testy w `tests/test_fares.py`). |
| **Sparpreis** (krajowy) | **Nie.** 0 trafień w `fares/*.py` i `fares/data/*.json` poza wzmianką tekstową w `_sprawdzono_*`. | Brak | Brak | Brak ceny. Segment DB dostaje cenę Flexpreis, patrz niżej. |
| **Flexpreis** (krajowy, 2. klasa) | **Tak, jako "górna granica".** `fares/db.py`, 10 pasm odległości w `db_flexpreis.json`: do 50 km 25 EUR, do 100 km 38, do 150 km 55, do 200 km 80, do 300 km 97, do 400 km 114, do 500 km 131, do 600 km 148, do 800 km 182, powyżej 800 km 182. Wybór DB tylko po nazwie agencji z MOTIS: `infer_rail_carrier` rozpoznaje "pkp intercity", "db fernverkehr", "deutsche bahn" i dokładnie "db". | **Szacunek własny.** Pasma to przybliżenie regresją `46 + 0,17 EUR/km` na 4 próbkach z blogów i raportu vzbv (`probki`). Pasma ≤ 150 km nie wynikają z tej formuły (150 km: tabela 55 EUR, formuła 71,50 EUR). Plik sam to nazywa ekstrapolacją. Mnożniki BahnCard 25/50 (0,75 i 0,5) pochodzą z bahn.de/faq/pk/angebot/flexpreis. Mnożnik BahnCard 100 (0,0) jest opisany jako "ogólnie znana zasada", bez URL. | Pole ze źródłem **bez daty weryfikacji** (`db_flexpreis.json` ma tylko `okres` przy próbkach). `fares/README.md` podaje sekcję "Stan danych po researchu (2026-09-26 …)". | `PriceType.ESTIMATE`. W `breakdown` nie ma `price_verified`, więc `PricedLeg.price_verified == False`. UI: "SZACUNEK" i dopisek "cena niepotwierdzona". Testy: `test_db_flexpreis_bez_bahncard`, `test_db_flexpreis_z_bahncard25`, `test_db_flexpreis_miesci_sie_w_realnych_przedzialach` (4 przedziały). Brak testu na BahnCard 50 i 100 przy cenie krajowej. |
| **Flexpreis 1. klasa** | **Nie.** Tylko `klasa: 2`. `tools/db-vendo-service/server.mjs` zna parametr `first=1`, ale klient Pythona (`fares/_db_vendo_api.py`) go nie przekazuje. | Brak | Brak | Brak |
| **Super Sparpreis Europa** (PL↔DE) | **Tak.** `fares/international.py`, 3 progi odległości (linia prosta): do 350 km 19,99 EUR, do 525 km 29,99 EUR, powyżej 39,99 EUR. Cena "od". Wykrywanie granicy: `routing/pricing.py::is_cross_border_pl_de`, geograficznie. | Ceny "od": bahn.de (Super Sparpreis Europa Polen) i int.bahn.de. **Progi km to szacunek własny**, dopasowany do 3 przykładów z bahn.de. DB nie publikuje tabeli relacja→kategoria. | Ceny: sprawdzone **2026-09-29** (`fares/README.md`). Progi km: szacunek, bez daty. | `PriceType.ESTIMATE` zawsze. UI: "SZACUNEK" i "cena niepotwierdzona", mimo że kwota "od" jest oficjalna. Testy: `test_krotka/srednia/dluga_relacja_cena_od_*` (3), BahnCard (5). |
| **Super Sparpreis Europa Young** (15–26 lat) | **Tak.** Jedna cena 18,99 EUR dla wszystkich relacji. | bahn.de (Super Sparpreis Europa Young Polen) i FAQ. Cena "od", DB nie podaje górnej granicy. | **2026-10-07** (`_zrodlo_young`) | `ESTIMATE`. Testy: parametryzowane wiek 15/20/26 oraz 14/27/60 (patrz tabela 2). |
| **Sparpreis Europa** (nie "Super") | **Nie.** Obsługiwana jest tylko ścieżka "Super Sparpreis Europa". | Brak | Brak | Brak |
| **Oferta PKP "Polska-Niemcy"** i **PKP Super Promo International** (ta sama relacja co DB) | **Tak** (dodatek do wyniku PL↔DE): `fares/international_pkp.py`, `fares/data/international_pl_de_pkp.json` (cena regularna np. 69 EUR) i `fares/data/pkp_spi_pl_de.json` (przedział poziom I–V). `routing/pricing.py::_with_pkp_alternative` bierze tańszą z dwóch ofert. | Cennik PKP IC "Oferta Polska-Niemcy" od 19.08.2026 i cennik SPI od 19.08.2026 (PDF-y w `verification/zrodla-pdf/`) | Oferta: sprawdzona **2026-10-09** (`_zrodlo`). SPI: **2026-10-11** (`verification/spi-cennik-weryfikacja-2026-10-11.md`). Poziomu SPI na konkretny dzień nie modelujemy. | `ESTIMATE`. Zakres cen pokazany w `breakdown["zakres_cen"]` i w `price.range`. Testy: `test_spi_range_*`, `test_dane_spi_zgodne_z_tekstem_cennika_pdf` i inne w `tests/test_international.py`. |
| **Deutschlandticket** | **Nie w kodzie.** Plik `fares/data/deutschlandticket.json` istnieje: 63,00 EUR/mies. od 2026-01-01 oraz historia cen 49 → 58 → 63 EUR. **Żaden moduł `.py` go nie ładuje** (0 trafień w kodzie i w testach), nie ma wpisu w `Carrier`. | Źródło wtórne: iamexpat.de (artykuł o podwyżce), do tego "Wikipedia, ogólnie znane" | `_data_sprawdzenia` **2026-09-27** | Nie występuje w wynikach. Odcinki regionalne dostają inne taryfy albo szacunek PLN/km. |
| **Bilety regionalne DB (RE/RB, DB Regio)** | **Nie.** `infer_rail_carrier` zwraca `None` dla DB Regio i S-Bahn. Cenę odcinka wyznacza geografia: taryfa miejska BVG/HVV/MVV/VRS (`_DE_CITY_RAIL_CARRIERS`), eezy.nrw (VRR) w NRW, a poza nimi `_fallback_priced_leg`. | Fallback: stała **0,35 PLN/km** (`GENERIC_FALLBACK_PLN_PER_KM`), bez źródła | Brak | `price_type="szacunek"`, `price_verified=False`. UI: "SZACUNEK" i "cena niepotwierdzona (powód w `powod_szacunku`)". |
| **Länder-Tickets** (Bayern-Ticket, Sachsen-Ticket, Quer-durchs-Land, Schönes-Wochenende itd.) | **Nie.** Jedyne wzmianki: "Brandenburg-Berlin-Ticket" i "Schönes-Wochenende-Ticket" w `bilet_graniczny_zasieki_forst.json` jako bilety honorowane na odcinku Zasieki–Forst bez dopłaty 5 zł. To tekst w `notes` jednej relacji, bez cen. | Brak | Brak | Brak |
| **Bilety lokalne i związkowe w DE** (nie DB, ale w tym samym silniku) | **Tak:** VRR eezy.nrw, BVG/VBB, HVV, MVV, VRS/Köln, ZVON Görlitz–Zgorzelec. Pliki `vrr_eezy.json`, `bvg_berlin.json`, `hvv.json`, `mvv.json`, `vrs_koln.json`, `zvon_gorlitz.json`. | Oficjalne cenniki związków, URL-e w polach `_zrodlo*` i w `fares/data/.snapshots/` (hashe stron dla watchera) | Wg `fares/README.md`: VRR Stand 01.06.2026; BVG od 01.01.2026 (strefa C BER 2026-10-12); HVV i MVV 2026-10-09 i 2026-10-10; VRS 2026-10-11; ZVON 2026-10-13 | `OFFICIAL` (VRS: oficjalne po poprawce z 2026-10-11). Kalkulator zawsze liczy najniższą strefę (brak mapowania przystanek→strefa), więc relacje poza nią wychodzą taniej niż w rzeczywistości. |
| **BahnCard** (produkt, `fares/cards.py` + `bahncard.json`) | **Tak, jako sugestia zakupu.** BC25 62,90 EUR; BC50 244,00 EUR; My BC25 39,90 i My BC50 79,90 (19–26 lat); Jugend BC25 7,90 EUR, a w oknie 2026-10-07…2026-12-12 cena 0,00 EUR (6–18 lat). **BahnCard 100 i wersje 1. klasy: brak** (mnożnik 0,0 jest w cenie biletu, ale karty nie ma w `bahncard.json`). | Strony bahn.de/angebot/bahncard (4 URL-e w `_zrodlo`) | `_data_sprawdzenia` **2026-10-11** | Nie ma `PriceType`. To `CardSuggestion` z tekstem `opis` po polsku. Testy: `test_bahncard_*` (11 testów w `tests/test_fares.py`) i `tests/test_card_suggestions.py`. |
| **Inne produkty DB** (City-Ticket, rezerwacja miejsca, Flexpreis Young −20%, Super Sparpreis Senioren, Sparpreis Gruppe) | **Nie.** City-Ticket: 0 trafień. Young −20% i Senioren są tylko opisane w `_sprawdzono_*`, bez kwot w kodzie. | Brak | Brak | Brak |

---

## Tabela 2. Ulgi wiekowe i karty

Skróty: **DB-kraj** = `fares/db.py` (Flexpreis), **DB-PL↔DE** = `fares/international.py`, **PKP-kraj** = `fares/pkp.py`,
**PKP-PL↔DE** = `fares/international_pkp.py`. Pole `DiscountProfile.age` jest używane tylko w `international.py`,
`international_pkp.py`, w kalkulatorach HVV/MVV/VRS/Zasieki/ZVON/Lublin oraz w `fares/cards.py` (wariant My/Jugend).
**`fares/db.py` i `fares/pkp.py` w ogóle nie czytają wieku** (0 trafień `age`).

| Grupa | Obsługiwana? | Reguła | Źródło i data | Test |
|---|---|---|---|---|
| **Dzieci do 5/6 lat** | **DB-kraj: nie.** Dziecko płaci pełny Flexpreis. **DB-PL↔DE: tak.** **PKP-PL↔DE: tak.** **PKP-kraj: tak, ale ręcznie** (kod `dzieci_do_4_lat`, 100%, wybór w selectboxie, nie z wieku). HVV, MVV, VRS Köln: tak. Zasieki–Forst: tak. | DB-PL↔DE: `age < 6` (`dziecko_bezplatnie_wiek_max = 6`) → 0,00 EUR, przed wszystkim innym. PKP-PL↔DE: `age < 6` → −100%. PKP-kraj: ulga 100% dla "do 4 lat". Progi w repo są niespójne (4 w PKP-kraj, 6 w pozostałych), każdy ze swoim źródłem. HVV/MVV/VRS: `age < 6` → 0,00 (`fares/_dzieci_do_6.py`). | DB-PL↔DE: bahn.de Super Sparpreis Europa Polen, sprawdzone **2026-10-09**. PKP-kraj: "Tabele ulg ustawowych 11.02.2026". HVV/MVV/VRS: pola `dzieci_ponizej_6_lat_bezplatnie` z cytatem, **2026-10-11**. | DB-PL↔DE: `test_dziecko_do_5_lat_zawsze_gratis` (0, 3, 5). PKP-PL↔DE: `test_ponizej_6_lat_przejazd_bezplatny`, `test_price_rail_leg_dziecko_ponizej_6_lat_oba_kanaly_gratis_remis_na_rzecz_pkp`. HVV/MVV/VRS: `test_dziecko_ponizej_6_lat_bezplatnie_granice_wieku`. **PKP-kraj: brak testu kodu `dzieci_do_4_lat`** (`test_i18n.py` sprawdza tylko klucz tłumaczenia). |
| **Dzieci 6–14 lat** | **DB-kraj: nie.** **DB-PL↔DE: tak** (z opiekunem gratis, samodzielnie −50%). PKP-PL↔DE: tak (−50%). Kindertarif VRR, HVV, MVV, VRS: tak (checkbox, domyślnie zaznaczony dla 6–14). BVG: ulgowy 6–14 (patrz uwaga niżej). | DB-PL↔DE z opiekunem (`child_with_guardian`, domyślnie `False`): 0,00 EUR. Samodzielnie: −50% **tylko na niemiecki odcinek** (rabat × `german_portion_fraction`), BahnCard pominięta. Polskiego odcinka nie modelujemy: bahn.de podaje −50% dla 4–11 lat, bez danych dla 12–14 (`_uwaga_dziecko`). PKP-PL↔DE: 6–14 lat → −50%. | bahn.de Super Sparpreis Europa Polen, "NA ŻYWO **2026-10-09**" (`_zrodlo_dziecko`) | DB-PL↔DE: `test_dziecko_6_14_lat_z_opiekunem_gratis` (6, 10, 14), `…samodzielnie_bez_wspolrzednych_50_procent_fallback`, `…domyslnie_bez_opiekuna`, `…z_wspolrzednymi_liczy_proporcjonalnie`. PKP-PL↔DE: `test_dziecko_6_14_lat_dostaje_50_procent_rabatu`. Kindertarif: `test_vrr_kindertarif_*` (2), `test_hvv/mvv/vrs_*_dziecko`. **API: pola `child_with_guardian` nie ma w `api/schemas.py::DiscountProfileIn`**, więc przez API nie da się go ustawić (jest w `DiscountProfile` i w UI). |
| **Młodzież 15–17** | **DB-kraj: nie.** **DB-PL↔DE: tak, w ramach "Young" 15–26.** **PKP-PL↔DE: nie.** Cennik PKP ma ulgę "Młodzież −25%" bez granic wieku, więc jej nie modelujemy. **Jugend BahnCard 25 (6–18)** tylko jako sugestia karty. | DB-PL↔DE: 15 ≤ age ≤ 26 → 18,99 EUR. Jugend BC: `wiek_min 6`, `wiek_max 18`. UI: dla miast PL i Berlina checkbox "ulgowy" ma domyślnie `wiek < 18`. | bahn.de Young 2026-10-07; Jugend BC 2026-10-11 | Young: `test_wiek_w_przedziale_young_…` (15, 20, 26), `test_wiek_poza_przedzialem_…` (14, 27, 60). Jugend BC: 3 testy (w trakcie promocji, po niej, przed nią). PKP "Młodzież": brak (nie modelujemy). |
| **Young / 18–26 lat** | **DB-kraj: nie** (Flexpreis Young −20% i Super Sparpreis Young tylko opisane w `_sprawdzono_*`). **DB-PL↔DE: tak** (Young 18,99 EUR). **My BahnCard 19–26: tak** (sugestia). **PKP-kraj: tak, ręcznie** (student do 26 lat, 51%). | Young: wiek decyduje w pierwszym dniu podróży. My BC: `wiek_min 19`, `wiek_max 26`. PKP-kraj: kod `student_do_26_lat_doktorant_do_35_lat` (51%). | bahn.de 2026-10-07 i 2026-10-11; PKP: tabela ulg 11.02.2026 | `test_bahncard_mloda_osoba_19_26_widzi_tansze_warianty_my_bahncard`, `test_pkp_z_ulga_studencka_51`, `tests/test_foreigner_eligibility.py` (ostrzeżenia dla cudzoziemców). |
| **Dorośli (27–64)** | **Tak.** DB-kraj: tabela Flexpreis. DB-PL↔DE: progi 19,99/29,99/39,99. PKP-kraj: 76 pasm TLK/IC (2. klasa). | Brak ulg | Patrz tabela 1. PKP-kraj: `data_weryfikacji = null`, czyli **brak zapisu, kiedy ktoś porównał pasma z PDF-em** (cennik obowiązuje od 23.07.2026). | `test_pkp_bez_ulgi`, `test_db_flexpreis_*`, `test_*_relacja_cena_od_*`. |
| **Seniorzy 65+ / 60+** | **DB: nie** (dla żadnej oferty). **PKP-kraj: tak, ręcznie** (kod `emeryci_rencisci_2_przejazdy_rok`, 37%). **PKP-PL↔DE: nie.** Lokalnie: Lublin 65+ i Wrocław 65+ (bezpłatnie), Warszawa, Kraków i Poznań 70+ (bezpłatnie). | DB: "Super Sparpreis Senioren" (65+, od 15,99 EUR, wybrane trasy) jest opisany, ale celowo niemodelowany, bo to osobny produkt, nie mnożnik. Karty BahnCard dla seniorów 60+ w `bahncard.json`: **brak**. PKP-kraj: ulga dla emerytów/rencistów bez progu wieku w kodzie. | bahn.de/angebot/sparpreise/super-sparpreis-senioren, **2026-10-10** i **2026-10-09** (docstring `international.py`). Lokalne: `fares/data/ztm_*.json`, `mpk_*.json` (2026-10-10, Lublin 2026-10-13). | `test_wiek_poza_przedzialem_…` (wiek 60 → taryfa normalna). Lokalne: m.in. `test_ztm_poznan_bilet_bezplatny_senior_70_plus`. **DB Senioren i PKP-kraj senior: brak testu.** |
| **BahnCard 25 / 50 / 100** | **DB-kraj: tak** (mnożniki 0,75 / 0,5 / 0,0 na Flexpreis). **DB-PL↔DE: tak, ale 25% dla każdego poziomu**, naliczane proporcjonalnie do szacowanego udziału niemieckiego odcinka (`german_portion_fraction`). Bez współrzędnych stacji: 25% od całości (zawyża rabat). **Sugestie zakupu:** BC25, BC50, My BC25/50, Jugend BC25. **BC100 i 1. klasa: brak.** | Mnożniki: `db_flexpreis.json::bahncard_mnoznik`. PL↔DE: `international_pl_de.json::bahncard_rabat_procent`. Podział PL/DE jest szacunkiem (linia prosta + 6 stałych punktów przejść granicznych). | bahn.de/faq/pk/angebot/flexpreis. PL↔DE: dwa niezależne cytaty, **2026-09-29**. Ceny kart: **2026-10-11**. | DB-kraj: tylko BC25 (`test_db_flexpreis_z_bahncard25`). **BC50 i BC100 przy cenie krajowej: brak testu.** PL↔DE: BC25, BC50, BC100 (3 testy), rabat proporcjonalny (2 testy), Young + BC (3 testy). Sugestie: 11 testów `test_bahncard_*` + `tests/test_card_suggestions.py`. |
| **Rodzina** | **DB-kraj: nie.** **DB-PL↔DE: tylko "dziecko 6–14 z opiekunem gratis"** (`child_with_guardian`). PKP: **brak**. Rabaty rodzinne w repo istnieją wyłącznie w module atrakcji (`family_price` w `attractions.json`), nie w taryfach transportu. | Brak reguły rodzinnej w `fares/` | Brak | Brak (poza testami `child_with_guardian` wyżej). |
| **Grupy** | **Nie.** 0 reguł grupowych w `fares/*.py`. W `fares/data/*.json` słowo "grupa" pojawia się tylko jako klucz `schuelergruppe_ermaessigt` w `zvon_gorlitz.json` (cena dla uczniów, nie taryfa grupowa). | Brak | Brak | Brak |

**Uwagi do tabeli 2** (sprzeczności i luki wewnątrz repo):

1. `app.py:754` ustawia `bvg_berlin_ulgowy` domyślnie na `wiek < 18`, a `fares/eligibility_info.py` i `form.kinder_other` mówią, że ulga BVG dotyczy dzieci 6–14 lat ("od 15 lat obowiązuje bilet normalny"). Dla wieku 0–5 i 15–17 checkbox jest więc zaznaczony wbrew własnemu opisowi.
2. `app.py:789` ma `value=wiek <= 7 or wiek <= 21 or wiek >= 65` (pierwszy człon jest zbędny). To tylko podpowiedź domyślna.
3. Ulgi PKP-kraj (9 kodów w `pkp_intercity.json`) wybiera się ręcznie. Wiek nigdy nie ustawia ich automatycznie. Testy kodu: `brak`, `student_do_26_lat_doktorant_do_35_lat`, nieznany kod. Pozostałe 7 kodów nie ma testu liczenia (w `tests/test_local_rail_tariffs.py` jest jedno użycie kodu `zolnierze_niezawodowej_sluzby_wojskowej` w segmencie SKM, nie PKP).

---

## Tabela 3. Tłumaczenia (pl, en, de, es, fr, nl)

### 3a. Słowniki `i18n/*.py`

Każdy z 6 plików (`i18n/pl.py`, `en.py`, `de.py`, `es.py`, `fr.py`, `nl.py`) ma **354 klucze**. Zestawy kluczy i pola `{…}` są identyczne.
W żadnym języku **nie ma kluczy pustych ani brakujących ani nadmiarowych**. Pilnuje tego `tests/test_i18n.py::test_komplet_kluczy_i_te_same_pola`.
Podział na kategorie jest mój: kategoria wynika z prefiksu klucza z kilkoma wyjątkami (np. `form.pkp` trafia do tariff, `cards.risky` do ostrzeżeń).

Format komórki: **pokryte z n (liczba identycznych z PL)**. "Pokryte" = klucz jest i ma niepusty tekst.

| Kategoria | Klucze w PL (n) | pl | en | de | es | fr | nl |
|---|---|---|---|---|---|---|---|
| Etykiety i teksty interfejsu (`app, lang, yes, no, form*, group, citizen, idcountry, age, student, senior, addr, metric.time/price/transfers, col, list, res, search, details, cards*, profile, rec, rank, other_day*, leg`) | 140 | 140 (0) | 140 (3) | 140 (3) | 140 (3) | 140 (3) | 140 (3) |
| Nazwy wariantów i typów transportu (`variant` 11, `tmode` 23, `mode` 4, `plain` 4) | 42 | 42 (0) | 42 (1) | 42 (0) | 42 (2) | 42 (0) | 42 (2) |
| Statusy cen i plakietki (`price` 14, `badge` 6, `ptype` 2, `source` 2, `metric.price_*` 5, `cards.estimate*`/`confirmed` 4) | 33 | 33 (0) | 33 (2) | 33 (2) | 33 (2) | 33 (2) | 33 (2) |
| Komunikaty błędów i powody pominięć (`err` 12, `skip` 18) | 30 | 30 (0) | 30 (0) | 30 (0) | 30 (0) | 30 (0) | 30 (0) |
| Ostrzeżenia (`foreign` 8, `transfer` 7, `bc.no_db`, `bc.already`, `cards.risky`, `other_day.warning`) | 19 | 19 (0) | 19 (0) | 19 (0) | 19 (0) | 19 (0) | 19 (0) |
| Opisy taryf i ulg DB, PKP i lokalnych (`pkp` 9, `bc` 4, `alt` 2, `free` 14, `free_info` 5, 14 kluczy `form.*` o ulgach) | 48 | 48 (0) | 48 (4) | 48 (4) | 48 (3) | 48 (3) | 48 (4) |
| Opisy atrakcji i kart miejskich, tylko część UI (`attr` 13, `card` 17, `cat` 5) | 35 | 35 (0) | 35 (0) | 35 (0) | 35 (0) | 35 (0) | 35 (0) |
| Nazwy miast w UI (`city` 7) | 7 | 7 (0) | 7 (5) | 7 (2) | 7 (2) | 7 (4) | 7 (3) |
| **Razem** | **354** | **354 (0)** | **354 (15)** | **354 (11)** | **354 (12)** | **354 (12)** | **354 (14)** |

**Klucze identyczne z polskim (podejrzane o brak tłumaczenia), wypisane dokładnie:**

| Język | Klucze |
|---|---|
| en (15) | `lang.label`, `senior.label`, `res.risk_risky`, `tmode.metro`, `metric.price_exact`, `price.variant_single`, `alt.db`, `form.bahncard`, `bc.100`, `form.hamburg`, `city.krakow`, `city.poznan`, `city.wroclaw`, `city.berlin`, `city.lublin` |
| de (11) | `lang.label`, `senior.label`, `res.risk_risky`, `metric.price_exact`, `price.variant_single`, `alt.db`, `form.bahncard`, `bc.100`, `form.hamburg`, `city.berlin`, `city.lublin` |
| es (12) | `lang.label`, `senior.label`, `res.risk_risky`, `tmode.subway`, `tmode.metro`, `metric.price_exact`, `price.variant_single`, `alt.db`, `form.bahncard`, `bc.100`, `city.poznan`, `city.lublin` |
| fr (12) | `lang.label`, `senior.label`, `res.risk_risky`, `metric.price_exact`, `price.variant_single`, `alt.db`, `form.bahncard`, `bc.100`, `city.poznan`, `city.wroclaw`, `city.berlin`, `city.lublin` |
| nl (14) | `lang.label`, `senior.label`, `res.risk_risky`, `tmode.subway`, `tmode.metro`, `metric.price_exact`, `price.variant_single`, `alt.db`, `form.bahncard`, `bc.100`, `form.hamburg`, `city.poznan`, `city.wroclaw`, `city.lublin` |

Ocena: wszystkie te klucze to nazwy własne, marki (`BahnCard`, `DB Super Sparpreis Europa`), emoji, szablony `{price} PLN` albo wyraz zbieżny (`metro`).
Jedynie `senior.label` = "Senior" jest identyczne we wszystkich 5 językach (akceptowalne w en/de/fr/nl, słabe w es). Żaden klucz nie jest pusty. Polskie znaki (`ą ć ę ł ń ś ź ż`) w tłumaczeniach występują tylko w nazwach własnych (Poznań, Wrocław, Gdańsk Główny, Kraków, Muzeum Powstania Warszawskiego): en 11 kluczy, de 2, es 7, fr 11, nl 11. W każdym języku jest też `lang.label` ("Język / Language", celowo dwujęzyczne).

**Tłumaczenia opisów PKP:** wszystkie **9** kodów ulg z `pkp_intercity.json` ma klucz `pkp.<kod>` w 6 językach (`tests/test_i18n.py` sprawdza to dla kodów z JSON).
Etykiety BahnCard to 4 klucze `bc.brak/25/50/100` w 6 językach. **Nazwy produktów DB w UI** (Flexpreis, Sparpreis) nie są tłumaczone, bo jedyny taki napis to `alt.db`.

### 3b. Teksty poza `i18n/*.py`, które mają własne tłumaczenia lub nie

| Kategoria | Plik / dane | pl | en | de | es | fr | nl |
|---|---|---|---|---|---|---|---|
| Opisy atrakcji (82 atrakcje: 6 gelsenkirchen, 6 berlin, 5 krakow, 4 lublin, 9 warszawa, 7 poznan, 6 hamburg, 6 wroclaw, 18 munchen, 15 koln) | `attractions/data/translations/<lang>.json` → `descriptions`. Oryginał PL w `attractions.json`. Wybór: `attractions/service.py::localized_description` | 82 (źródło) | **82 z 82** (0 puste, 0 identycznych z PL) | 82 z 82 (0, 0) | 82 z 82 (0, 0) | 82 z 82 (0, 0) | 82 z 82 (0, 0) |
| Adnotacje do cen "od" (`price_is_from`; są 3 takie atrakcje: `essen_zeche_zollverein`, `berlin_fernsehturm`, `koln_zoo`) | `translations/<lang>.json` → `notes` | 3 (z `variable_pricing_note`) | 3 z 3 | 3 z 3 | 3 z 3 | 3 z 3 | 3 z 3 |
| Nazwy atrakcji (82), adresy (82) | `attractions.json` (`name`, `address`) | 82 + 82 | **0** (nazwy własne, brak pliku tłumaczeń) | 0 | 0 | 0 | 0 |
| Etykiety grup cenowych w atrakcjach (`child_price`, `student_price`, `senior_price`, `family_price`; łącznie **87 pól `GroupPrice`**, 85 unikalnych etykiet) | `attractions.json` → `label` (np. "uczący się"); pokazywane w `app.py:465` | 87 | **0** | 0 | 0 | 0 | 0 |
| Karty miejskie: 9 kart i 67 wariantów (nazwa, opis, `transit_zones`) | `attractions/data/city_cards.json`; w UI wariant: `ev.variant.name` (`app.py:433`) | 9 + 67 | **0** | 0 | 0 | 0 | 0 |
| Podsumowanie opłacalności karty (`CityCardEvaluation.summary`, 3 szablony po polsku) | `attractions/service.py:515–536`, wstawiane do `t("card.recommendation", summary=…)` (`app.py:418`) | 3 | **0** (w en/de/es/fr/nl ramka "Rekomendacja" jest przetłumaczona, ale zdanie w środku po polsku) | 0 | 0 | 0 | 0 |
| Nazwy miast (aliasy) | `places/aliases.json`, **42 miasta** (17 PL, 22 DE, 1 AT, 1 CZ, 1 NL), wszystkie `zweryfikowano: true` | 29 niepustych / 13 pustych | 9 / 33 | 38 / 4 | 15 / 27 | 15 / 27 | 10 / 32 |
| (jw.) identyczne z polską nazwą | | n/d | 1 (`krakow`) | 7 (`katowice`, `bydgoszcz`, `torun`, `opole`, `olsztyn`, `czestochowa`, `gorzow_wielkopolski`) | 1 (`praha`) | 0 | 0 |
| Aliasy tylko do wyszukiwania | pole `aliasy_wyszukiwania`: 8 wpisów w 8 miastach (Cracow, Kattowitz, Bromberg, Thorn, Oppeln, Allenstein, Tschenstochau, Landsberg an der Warthe) | | | | | | |
| Nazwy przystanków i dworców | **brak** słownika. `places/aliases.py::localize_name` podmienia tylko początek nazwy równy nazwie miasta ("Köln Hbf" → "Cologne Hbf"). Reszta nazw z MOTIS/GTFS idzie bez zmian. | | | | | | |

Puste pole w `aliases.json` znaczy z definicji pliku "brak odrębnej nazwy w tym języku, UI używa nazwy lokalnej". To nie jest błąd, ale jest to granica pokrycia.
Pokrycie nazw egzonimicznych różni się mocno: de 38 z 42, es i fr po 15, nl 10, en 9.

**Nazwa miasta w nagłówku atrakcji.** `app.py:317–318`: `known_cities = ("gelsenkirchen", "berlin", "krakow", "lublin", "warszawa")`.
Dla pozostałych 5 miast z katalogu atrakcji (`hamburg`, `munchen`, `koln`, `poznan`, `wroclaw`) nagłówek `attr.header` dostaje `norm_city.capitalize()`:
"Hamburg", "Munchen", "Koln", "Poznan", "Wroclaw" (bez umlautów i polskich znaków), w każdym języku, mimo że `city.poznan` i `city.wroclaw` w słownikach istnieją.

### 3c. Teksty wpisane na sztywno po polsku w kodzie, które trafiają na ekran

Wykryte przez prześledzenie ścieżek od `app.py` i `ui_helpers.py`. Tekst jest po polsku we wszystkich 6 językach.

| Plik:linia | Co | Liczba | Gdzie pokazywane |
|---|---|---|---|
| `fares/eligibility_info.py` (29 literałów) | 9 nazw miast, **21** tytułów bezpłatnych, **13** tytułów ulgowych, 2 szablony zdań `explain_ticket` ("Przejazd bezpłatny — …", "Bilet ulgowy — …") | 9 + 21 + 13 + 2 | `ui_helpers.py:54–71` `render_bezplatne_info`; ramka sukcesu i rozwijana lista "Kto jedzie bezpłatnie". Nagłówek i szablony `free_info.*` są przetłumaczone, elementy listy nie. |
| `fares/cards.py` (12 literałów) + `fares/data/bahncard.json` (`nazwa` 5 wariantów) | Szablon `opis` sugestii BahnCard (3 warianty zdania: opłaca się, nie zwraca się z progiem, brak dodatkowego rabatu) oraz nazwy kart | 3 + 5 | `app.py:297` i `app.py:299`: `st.info(f"💳 {best.opis}")` |
| `routing/pricing.py::_with_spi_range` | Źródła krańców przedziału: "SPI poziom I", "PKP cennik regularny", "DB (cena od, bez górnej granicy w źródle)", "SPI poziom V" | 4 unikalne | `app.py:219–221` wstawiane w `price.range` ("szacunek: od X (…) do Y (…)") |
| `flights/cabin_baggage.py::format_breakdown` (31 literałów w pliku) + dane `flights/data/` | Opis bagażu podręcznego ("Bagaż podręczny:", "Dopłata … ORIENTACYJNA, NIEPOTWIERDZONA …", "Inne opłaty bagażowe …", "Źródło opłat: …", "Źródło: …") | min. 5 szablonów | kolumna `col.cabin_baggage` (`app.py:205`). Kolumna `col.baggage_tariff` (`breakdown["bagaz_zrodlo"]`) też bez tłumaczenia. |
| `attractions/service.py:515–536` | `CityCardEvaluation.summary` | 3 szablony | `app.py:418` |
| `attractions/service.py:373` | Zapasowa adnotacja "ceny zależą od terminu/wariantu, ulgi możliwe" | 1 | Nieosiągalna dziś: 3 atrakcje z `price_is_from` mają tłumaczone `notes` |
| `ui_helpers.py:545` | `"woj. "` i `"województwo "` w opisie duplikatów w podpowiedziach adresów | 2 | `_region` → `option["detail"]` |
| `ui_helpers.py:449–452` (`KNOWN_PLACES`) | 55 nazw miast do korekty literówek (PL i DE w formie lokalnej) | 55 | dane, nie tekst UI |
| `routing/model.py::PricedLeg.unverified_label` (3 teksty) | Wersja po polsku. **UI używa tłumaczonego `app.py::_unverified_label`**, więc na ekranie to jest przetłumaczone. | 3 | tylko API i `demo.py` |
| `fares/*.py` → `PriceEstimate.notes` | Opis każdej wyceny po polsku (wszystkie kalkulatory) | każdy kalkulator | **Nie renderowane** przez `app.py` ani `ui_helpers.py` (0 trafień `.notes`). Idzie do API i `demo.py`. |
| `breakdown["typ_biletu"]` w `fares/*.py` | 17 literałów w 14 plikach, część po polsku, część po niemiecku ("Einzelkarte dziecko", "Einzelfahrt ermäßigt") | 17 | Wstawiane do szablonów `explain_ticket` (`ui_helpers.py:60`) |
| `app.py` | 1 literał z polskim tekstem: "Język / Language" (celowo dwujęzyczny). Klucz wewnętrzny `"Wszystkie"` (`app.py:330, 331, 345`) jest mapowany na `t("attr.all_categories")`, nie jest widoczny. | 1 | |

**Mechanizm `Msg`** (tłumaczone teksty generowane w kodzie domenowym): **65** wywołań `Msg(` w 8 plikach: `routing/variants.py` 28, `fares/foreigner_eligibility.py` 8, `routing/motis_client.py` 7, `routing/airports.py` 6, `routing/transfers.py` 6, `flights/travelpayouts.py` 6, `routing/model.py` 2, `routing/scoring.py` 2. To są klucze z 3a, więc przetłumaczone.

**Surowy licznik literałów** (parser AST: literały tekstowe poza docstringami, zawierające polskie znaki diakrytyczne albo polskie słowa kluczowe; obejmuje też klucze słowników i wyrażenia regularne, więc to górna granica, a nie liczba widocznych tekstów). Pliki z wynikiem ≠ 0:
`routing/pricing.py` 105, `demo.py` 44, `flights/cabin_baggage.py` 31, `fares/eligibility_info.py` 29, `ui_helpers.py` 19, `fares/international.py` 19, `fares/koleje_malopolskie.py` 15, `fares/_flixbus_api.py` 14, `fares/skm_trojmiasto.py` 14, `fares/cards.py` 12, `fares/lka_lodz.py` 12, `fares/polregio.py` 12, `fares/ztm_lublin.py` 12, `attractions/service.py` 12, `fares/koleje_mazowieckie.py` 11, `fares/bvg_berlin.py` 10, `flights/calculator.py` 10, `fares/model.py` 9, `routing/scoring.py` 8, `fares/bilet_graniczny_zasieki_forst.py` 8, `fares/mpk_krakow.py` 8, `fares/mpk_wroclaw.py` 8, `fares/ztm_poznan.py` 8, `fares/ztm_warszawa.py` 8, `fares/flixbus.py` 7, `fares/db.py` 6, `fares/pkp.py` 6, `api/schemas.py` 6, `fares/hvv.py` 5, `fares/mvv.py` 5, `fares/kd_zgorzelec_gorlitz.py` 5, `fares/zvon_gorlitz.py` 5, `routing/demo_route.py` 5, `fares/kvb.py` 4, `fares/vrr.py` 4, `api/main.py` 4, `routing/model.py` 4, `common/currency.py` 4, `fares/_db_vendo_api.py` 3, `fares/_dzieci_do_6.py` 3, `fares/international_pkp.py` 3, `flights/extras.py` 3, `app.py` 1, `fares/calculator.py` 1, `routing/motis_client.py` 1, `routing/transfers.py` 1, `flights/travelpayouts.py` 1. **Suma: 525.**
Skaner nie wykrywa tekstów bez polskich znaków i bez słów kluczowych (jedno słowo, np. "Wszystkie"), więc nie jest to pełny spis.

### 3d. Formaty liczb, walut i dat

| Element | Gdzie | Stan w każdym z 6 języków |
|---|---|---|
| Liczby | `f"{x:.2f}"` w **16 liniach** `app.py` (170, 176, 177, 180, 195, 209, 210, 218, 220, 228, 434, 438, 439, 441, 443, 460) | Zawsze kropka dziesiętna, bez separatora tysięcy, niezależnie od języka. Brak `locale`/Babel. |
| Waluty | Kod waluty z danych (`PLN` albo `EUR`); w szablonach i18n wpisane na sztywno "PLN" (`metric.price_from`, `metric.price_exact`, `metric.price_high_help`, `price.variant_*` i inne) | Jednakowo we wszystkich językach. Przelicznik stały `common/currency.py`: EUR = 4,3775 PLN (NBP, tabela A, 2026-10-09). Obsługiwane tylko PLN i EUR. |
| Daty weryfikacji | `ui_helpers.py:187` `strftime("%d.%m.%Y")` | Jeden format dla wszystkich języków. |
| Daty w komunikatach (`skip.no_via_connection`, `other_day.*`) | parametr `{date}` wstawiany jako `variant.date` | Zapis ISO `YYYY-MM-DD` bez formatowania językowego (pola `date: str` w `routing/model.py:57` i `:216`, `Msg(…, date=request.date)` w `routing/variants.py`). |
| Godziny | `f"{leg.depart:%H:%M}"`, `app.py:517` | 24 h we wszystkich językach |
| Jednostki czasu | `ui_helpers.py::duration_text`: "h" i "min" na sztywno; `app.py:163` `f"{… :.1f} h"`; `col.hours` z "min" na sztywno | Nieprzetłumaczone ("h", "min" są wspólne, ale nie z i18n) |
| Liczba mnoga | `ui_helpers.py::transfers_text`: polskie 4 formy (0/1/few/many) tylko dla `pl`; pozostałe języki 2 formy | OK dla en/de/es/fr/nl (2 formy); `other_day.later_one/_many` i `earlier_one/_many` mają po 2 formy we wszystkich językach |
| Atrybut `lang` strony | `ui_helpers.py::set_html_lang` ustawia `<html lang>` i `translate="no"` | Zmienia język dokumentu, nie wpływa na formaty |

---

## Lista luk

### A. Poziomy cen (tabela 1)

1. **Brak:** Super Sparpreis, Sparpreis, Sparpreis Europa (bez "Super"), Flexpreis 1. klasa, Länder-Tickets, City-Ticket, Flexpreis Young, Super Sparpreis Young/Senioren, bilety grupowe i bilet DB Regio z taryfą regionalną.
2. **Deutschlandticket:** dane są (63 EUR od 2026-01-01), ale **żaden kod ich nie czyta** i nie ma testu. Źródło jest wtórne (iamexpat.de), data 2026-09-27.
3. **Szacunek, nie taryfa:** cała cena krajowego DB (tabela Flexpreis z 10 pasm, brak daty weryfikacji; pasma ≤ 150 km niezgodne z własną formułą `46 + 0,17 EUR/km`; dystans to `leg.distance_km` z MOTIS, nie km taryfowe). Progi km dla Super Sparpreis Europa (350/525 km). Udział niemieckiego odcinka przy BahnCard PL↔DE. Każdy segment DB w UI ma status "SZACUNEK".
4. **Mnożnik BahnCard 100 = 0,0** bez URL źródła. Karty BahnCard 100 i wersji 1. klasy nie ma w `bahncard.json`, więc nie da się ich zasugerować.
5. **Odcinki DB Regio / S-Bahn poza miastami z taryfą i poza NRW** dostają 0,35 PLN/km (`GENERIC_FALLBACK_PLN_PER_KM`) bez źródła.
6. **Nieoficjalne API DB** (`UNOFFICIAL_PRICES=1`): domyślnie wyłączone; zwraca najniższą cenę bez informacji, jaki to rodzaj taryfy. Klient Pythona nie przekazuje `first=1` (1. klasa).
7. **Tylko 2. klasa.** Wykrywanie DB tylko po nazwie agencji ("db fernverkehr", "deutsche bahn", "db"). Inna nazwa w feedzie oznacza brak ceny DB.
8. **PKP-kraj:** `data_weryfikacji = null`, brak zapisu porównania pasm z PDF-em. EIC/EIP: cena z pasm TLK/IC, oznaczona jako niepotwierdzona.
9. **Odnośniki do plików, których nie ma w repo:** `research/zrodla-znizek-kart.md`, `research/zrodla-krzyzowa-kontrola.md` (w `fares/README.md`, `attractions/README.md`) i `research/ui-styl.md` (komentarz w `app.py`). W `research/` są tylko `ui-projekt.md` i `ui-przeglad.md`.

### B. Ulgi wiekowe i karty (tabela 2)

1. **`fares/db.py` ignoruje wiek:** brak ulgi dziecięcej, młodzieżowej, "Young" i seniorskiej dla Flexpreis krajowego. Dziecko 0–14 lat na trasie krajowej DB dostaje pełną cenę.
2. **Niemodelowane:** Super Sparpreis Senioren (65+), Flexpreis Young (−20%), BahnCard dla seniorów 60+, rodzina (poza `child_with_guardian` w PL↔DE), grupy, PKP "Młodzież −25%" (brak granic wieku w źródle).
3. **Niespójne progi wieku:** PKP-kraj "do 4 lat" a PKP-PL↔DE i DB-PL↔DE "do 6 lat". Domyślne checkboxy miast ustawiane z wieku (`wiek < 18` dla BVG wbrew własnemu opisowi 6–14, `wiek >= 70`, `wiek <= 21`).
4. **API:** `DiscountProfileIn` nie ma `child_with_guardian`.
5. **Brak testów:** BahnCard 50 i 100 przy cenie krajowej, 7 z 9 kodów ulg PKP-kraj (w tym `dzieci_do_4_lat` i `emeryci_rencisci_2_przejazdy_rok`), DB Senioren, PKP "Młodzież", status UI (`OFFICIAL`/`ESTIMATE`) dla odcinka DB (żaden test w `test_price_status_ui.py`, `test_unverified_prices.py` ani `test_partial_price.py` nie używa DB).
6. **Podział PL/DE dla BahnCard:** szacunek geograficzny (linia prosta + 6 punktów granicznych). Bez współrzędnych 25% od całej ceny, co zawyża rabat.
7. **Polski odcinek dziecka PL↔DE** (−50% dla 4–11 lat na bahn.de) celowo niemodelowany.

### C. Tłumaczenia (tabela 3)

1. **Słowniki `i18n/*.py` kompletne:** 354/354 w 6 językach, 0 pustych, 0 brakujących. Zero kluczy podejrzanych o brak tłumaczenia (15/11/12/12/14 identycznych z PL w en/de/es/fr/nl to nazwy własne, marki, emoji, szablony). Najsłabszy punkt: `senior.label` = "Senior" w es.
2. **Nieprzetłumaczone zdania wyświetlane użytkownikowi:** (a) lista "Kto jedzie bezpłatnie/ulgowo" (9 miast, 21 + 13 tytułów, 2 szablony; `fares/eligibility_info.py`); (b) `opis` sugestii BahnCard (3 szablony + 5 nazw kart); (c) 4 źródła krańców zakresu cen SPI; (d) bagaż podręczny i cennik bagażu (`flights/cabin_baggage.py`, `breakdown["bagaz_zrodlo"]`); (e) podsumowanie opłacalności karty miejskiej (3 szablony); (f) `"woj. "` w podpowiedziach adresów.
3. **Dane atrakcji:** opisy 82/82 w 5 językach i adnotacje 3/3 są pokryte. Nieprzetłumaczone: **87** etykiet grup cenowych (np. "uczący się"), 9 kart i **67** wariantów kart miejskich (nazwa, opis, `transit_zones`), 82 adresy. Nazwy atrakcji (82) to nazwy własne, bez pliku tłumaczeń.
4. **Nagłówek atrakcji:** 5 z 10 miast katalogu (`hamburg`, `munchen`, `koln`, `poznan`, `wroclaw`) pokazuje wewnętrzny klucz ("Munchen", "Koln", "Poznan", "Wroclaw") w każdym języku.
5. **Nazwy miast (`places/aliases.json`):** 42 miasta, ale pokrycie egzonimów niskie: de 38, es 15, fr 15, nl 10, en 9 niepustych. Pozostałe używają nazwy lokalnej. Brak słownika przystanków i dworców.
6. **Formaty:** kropka dziesiętna, "PLN" w szablonach, `%d.%m.%Y`, daty ISO w komunikatach, "h"/"min" na sztywno, brak lokalizacji formatów w żadnym z 6 języków.
7. **Teksty poza UI, tylko po polsku:** `PriceEstimate.notes` wszystkich kalkulatorów (API i `demo.py`), `demo.py` (44 literały), `api/schemas.py` (6), `api/main.py` (4), `routing/model.py::unverified_label` (3), `RECOMMENDATION_LABELS` (11, zgodne z kluczami `rec.*` — test pilnuje).
8. **Nie zweryfikowano:** testy nie były uruchamiane (brak `pytest` i `streamlit` w środowisku), więc stwierdzenie "ma test" oznacza istnienie testu w repo, nie jego przejście. Nie sprawdzano aktualności cen u przewoźników ani działania UI w przeglądarce.
