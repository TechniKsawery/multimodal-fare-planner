# Audyt zgodności całego produktu

Data audytu: 2026-10-14. Stan repozytorium: `main` @ `2f0db2c` (po scaleniu #136). Zakres: `fares/` (kod i `fares/data/*.json`),
`routing/`, `flights/`, `common/`, `api/`, `app.py`, `ui_helpers.py`, `i18n/`, `tests/`. Nie obejmuje modułu atrakcji
(`attractions/`) poza porównaniem progów wieku w tabeli 2 oraz tłumaczeń (te opisuje `research/audyt-taryf-db.md`).

**Metoda.**
1. Czytanie kodu i danych oraz liczenie skryptami (parser AST, `json`, `grep`) na plikach z repo. Niczego nie zmieniałem w kodzie
   ani w danych. Nie sprawdzałem cen u przewoźników: audyt dotyczy tylko tego, co jest w repo. Daty weryfikacji pochodzą z pól
   w plikach JSON, z `fares/README.md` albo z docstringów.
2. Testy uruchomiłem: `pytest` dał **2033 passed, 12 skipped** (12 pominiętych to testy wymagające lokalnie uruchomionego MOTIS,
   `tests/test_demo_route_live.py`). Do uruchomienia doinstalowałem w środowisku audytu `pytest`, `streamlit`, `fastapi`,
   `streamlit-searchbox` i `httpx`; repo nie zmieniłem. „Ma test” oznacza, że w `tests/` jest test danego zachowania (podaję jego nazwę).
3. Tabela 4 jest liczona **prawdziwym kodem repo z atrapą MOTIS**. Atrapa podmienia tylko `requests.get`: odpowiedź `/api/v6/plan`
   to ręcznie zbudowane itineraria w schemacie MOTIS API v6 (agencja, tryb, przystanki ze współrzędnymi, czasy). Cała reszta
   (`motis_client.itinerary_to_legs` → `variants.generate_variants` → `pricing` → `fares` → `scoring`) jest rzeczywista.
   Pozostałe zapytania (geokodowanie, API FlixBusa, Travelpayouts) nie działają: FlixBus zawsze wpada w fallback 0,27 PLN/km,
   a warianty lotnicze są pomijane (brak tokena `TRAVELPAYOUTS_TOKEN`), więc **lotów w tabeli 4 nie ma**. Itineraria są
   syntetyczne (nie są rozkładem jazdy), służą sprawdzeniu ścieżek wyceny. Skrypt atrapy nie jest w repo (zlecenie: „nic nie zmieniaj”);
   jego dane są w Aneksie na końcu pliku.
4. Gdzie czegoś nie ma w kodzie ani w danych, wpisuję **brak**.

**Słownik komórek tabeli 1.** **działa** = kalkulator stosuje regułę i ma źródło w repo. **nie działa** = pasażer ma tytuł, który
w realnej taryfie lub w opisie UI występuje, ale kod nie zmienia ceny (albo zmienia błędnie). **szacunek** = reguła jest, ale wynik
jest przybliżeniem, założeniem albo daną niezweryfikowaną niezależnie. **brak** = w kodzie i w danych nie ma ani reguły, ani źródła.
„RĘCZ.” = pasażer musi sam wybrać pozycję w formularzu (wiek jej nie ustawia). „UI” = domyślna wartość pola w `app.py` zależna od wieku.
„T:” = nazwa testu albo „brak”.

Oznaczenia cen w UI (`ui_helpers.py::leg_price_status`): `OFFICIAL` = plakietka „OFICJALNA TARYFA”, `ESTIMATE` = „SZACUNEK”,
`NO_PRICE` = „BRAK CENY”. `OFFICIAL` wymaga jednocześnie `price_type == "oficjalna_taryfa"` i `price_verified`. Źródło i datę w UI
bierze `leg_source` z `breakdown["zrodlo_url"]` albo `["zrodlo"]` (musi zaczynać się od `http`) oraz `["data_weryfikacji"]` albo `["data_odczytu"]`.

---

## Tabela 1. Macierz: grupa pasażera × przewoźnik i produkt

Macierz podzielona na trzy części (te same wiersze): 1a dalekobieżne i międzynarodowe, 1b komunikacja miejska w Polsce, 1c komunikacja
miejska w Niemczech i pogranicze. Zakres miast = to, co jest w kodzie (`fares/calculator.py::_CALCULATORS`, `routing/pricing.py::CITY_TARIFF_AREAS`).
Miast bez taryfy w kodzie (m.in. Gdańsk i Gdynia ZTM/ZKM, Łódź MPK, Szczecin, Drezno, Lipsk, Hanower, Frankfurt, Stuttgart) nie ma:
odcinek dostaje fallback 0,35 PLN/km albo wartość zastępczą 4,00 PLN (patrz tabela 3).

### 1a. Dalekobieżne, międzynarodowe, autokary, loty

Kolumny: **A** PKP Intercity krajowe (`fares/pkp.py`; EIC/EIP = cena z pasm TLK/IC jako szacunek). **B** PL↔DE: Berlin-Warszawa-Express i podobne,
cena = tańsza z oferty DB „Super Sparpreis Europa” (`international.py`) i oferty PKP „Polska-Niemcy” (`international_pkp.py`, plus przedział SPI). **C** regionalne PL:
Polregio/Koleje Dolnośląskie/Koleje Śląskie (`polregio.py`), SKM Trójmiasto, Koleje Mazowieckie (KM), Koleje Małopolskie (KMŁ), ŁKA.
**D** DB krajowe (`db.py`, Flexpreis jako górna granica); DB Regio/S-Bahn bez taryfy = fallback 0,35 PLN/km. **E** FlixBus i inne autokary. **F** loty.

| Grupa | A. PKP IC krajowe | B. PL↔DE (DB + PKP) | C. Regionalne PL | D. DB krajowe | E. FlixBus / autokary | F. Loty |
|---|---|---|---|---|---|---|
| **Dziecko do 5 lat** | **działa RĘCZ.** kod `dzieci_do_4_lat` 100% (próg 4 lata, nie 6; wiek go nie ustawia). Źr.: tabela ulg PKP 11.02.2026, bez daty weryfikacji. T: brak | **działa (szacunek)** `age<6` → 0 EUR (DB) i −100% (PKP). Źr.: bahn.de 2026-10-09; cennik PKP od 19.08.2026. T: `test_dziecko_do_5_lat_zawsze_gratis`, `test_ponizej_6_lat_przejazd_bezplatny` | **działa RĘCZ.** ten sam kod 100% w Polregio/KD/KŚ i SKM Trójmiasto (kwota z ulgą liczona %, więc szacunek). KM, KMŁ, ŁKA: **nie działa** (ulgi niemodelowane, cena normalna). T: brak dla tego kodu | **nie działa** `db.py` nie czyta wieku, dziecko płaci pełny Flexpreis. T: brak | **brak** `flixbus.py` nie czyta profilu. T: brak | **brak** wiek ignorowany, cena dorosłego. T: brak |
| **Dziecko 6–14 z opiekunem** | **brak** (PKP krajowe nie zna opiekuna) | **działa (szacunek)** `child_with_guardian` → 0 EUR. Checkbox w UI tylko dla wieku 6–14, **w API pola nie ma**. PKP nie rozróżnia opiekuna (−50%), cena główna = tańsza oferta. Źr.: bahn.de 2026-10-09. T: `test_dziecko_6_14_lat_z_opiekunem_gratis` | **brak** | **nie działa** | **brak** | **brak** |
| **Dziecko 6–14 samodzielnie** | **działa RĘCZ.** `dzieci_mlodziez_szkolna_do_24_lat` 37%. Źr.: tabela ulg 11.02.2026. T: brak dla PKP IC (kod testują tylko `test_polregio_tariff`, `test_local_rail_tariffs`) | **szacunek** DB: −50% tylko na niemiecki odcinek (× `german_portion_fraction`, bez współrzędnych od całości); polskiego odcinka nie modelujemy (bahn.de: 4–11 lat −50%). PKP: −50%. T: `test_dziecko_6_14_lat_samodzielnie_*` (3), `test_dziecko_6_14_lat_dostaje_50_procent_rabatu` | **działa RĘCZ.** 37% w Polregio/KD/KŚ i SKM (szacunek, patrz tabela 3); KM, KMŁ, ŁKA **nie działa**. T: `test_ulga_procentem_od_ceny_bazowej_i_nie_jest_odczytem_z_cennika` (Polregio) | **nie działa** | **brak** | **brak** |
| **Młodzież 15–17** | **działa RĘCZ.** ten sam kod 37% (uczniowie do 24 lat); wiek nie wybiera go sam. T: brak | **działa (szacunek)** wiek 15–26 → „Young” 18,99 EUR, jedna cena „od”. PKP „Młodzież −25%”: **brak** (cennik nie podaje granic wieku). Źr.: bahn.de 2026-10-07. T: `test_wiek_w_przedziale_young_dostaje_cene_young_niezaleznie_od_dystansu` (15, 20, 26) | jak w wierszu „6–14 samodzielnie” | **nie działa** („Flexpreis Young −20%” tylko opisany w `_sprawdzono_*`) | **brak** | **brak** |
| **Student (np. 22 l.)** | **działa RĘCZ.** `student_do_26_lat_doktorant_do_35_lat` 51%. W UI student 22 l. = pełna cena (kod nie ustawia się z wieku ani z „status ucznia/studenta”, ten checkbox dotyczy atrakcji). T: `test_pkp_z_ulga_studencka_51` | **działa (szacunek)** wyłącznie przez wiek 15–26 (Young 18,99 EUR); status studenta nie jest ani wymagany, ani sprawdzany. PKP: **brak**. T: testy „young” j.w. | Polregio/KD/KŚ **szacunek** 51% RĘCZ.; SKM **szacunek** (51% z tabeli ulg, kwoty wg Gemini); KM, KMŁ, ŁKA **nie działa**. T: `test_skm_trojmiasto_z_ulga_studencka_z_tabeli_ulg`, `test_ulga_daje_cene_normalna_niepotwierdzona` (KM), `test_ulgi_nie_sa_modelowane_cena_normalna_i_niepotwierdzona` (KMŁ), `test_lka_z_ulga_pokazuje_cene_normalna_jako_niepotwierdzona` | **nie działa** (brak ulgi legitymacyjnej; DB: `db_flexpreis.json::_sprawdzono_zagraniczne_legitymacje`) | **brak** | **brak** |
| **Uczeń** | **działa RĘCZ.** 37% (jak wyżej). T: brak | **brak** statusu ucznia (tylko wiek: 6–14, 15–26) | jak „6–14 samodzielnie” | **nie działa** | **brak** | **brak** |
| **Senior 60+/65+** | **działa RĘCZ., nie z wieku** kod `emeryci_rencisci_2_przejazdy_rok` 37%; progu wieku 60+/65+ w kodzie **brak**. T: brak | **brak** („Super Sparpreis Senioren” 65+ to osobny produkt krajowy DB, celowo niemodelowany; bahn.de 2026-10-09/10). PKP: **brak** | Polregio/KD/KŚ i SKM: jak A (RĘCZ., szacunek); KM, KMŁ, ŁKA **nie działa** | **brak** (Senioren i BahnCard 60+ nie ma w kodzie) | **brak** | **brak** |
| **Osoba z niepełnosprawnością** | **działa RĘCZ.** `niezdolni_do_samodzielnej_egzystencji` 37%, `niewidomi_…` 51%, `opiekun_lub_przewodnik_…` 95%. T: brak | **brak** | Polregio/KD/KŚ i SKM jak A; KM, KMŁ, ŁKA **nie działa** | **brak** (Fernverkehr bez zniżki z Schwerbehindertenausweis; bahn.de/barrierefrei, 2026-10-10) | **brak** | **brak** |
| **Cudzoziemiec** | **tylko ostrzeżenie** (cena bez zmian): kody studenckie + UE/poza UE (`foreign.pkp_eu`, `foreign.pkp_non_eu`). T: `test_pkp_ulga_studencka_poza_ue_ostrzega_o_wykluczeniu`, `…_ue_ostrzega_o_karcie_pobytu` | **brak** (obywatelstwo bez wpływu; Young i dziecko wg wieku) | ostrzeżenie jak w A dla kodów studenckich (każda taryfa używająca `pkp_ulga_kod`) | **brak** | **brak** | **brak** |
| **Posiadacz BahnCard** | nie dotyczy (pole ignorowane) | **szacunek** 25% dla BC25/50/100 tylko od niemieckiego odcinka. Źr.: dwa cytaty bahn.de 2026-09-29. T: `test_bahncard_25/50/100_bez_wspolrzednych_…`, `test_bahncard_z_udzialem_niemieckiego_odcinka_…` | nie dotyczy | **szacunek** mnożniki 0,75/0,5/0,0 × górna granica Flexpreis. BC100 (0,0) bez URL źródła. T: tylko BC25 (`test_db_flexpreis_z_bahncard25`); BC50 i BC100 przy cenie krajowej **brak** | nie dotyczy | nie dotyczy |
| **Karty PKP i miejskie** | **brak** (w kodzie nie ma żadnej karty PKP, w tym Karty Dużej Rodziny) | **brak** | **brak** | **brak**; `deutschlandticket.json` (63 EUR, 2026-09-27) jest w danych, **żaden kod go nie czyta**; City-Ticket: 0 trafień | **brak** | **brak** |

### 1b. Komunikacja miejska w Polsce

Kalkulatory ZTM/MPK nie czytają `DiscountProfile.age`, poza ZTM Lublin. Wiek działa tylko przez domyślne wartości checkboxów w `app.py` (nie przez API).

| Grupa | Lublin (ZTM) | Warszawa (ZTM) | Kraków (MPK) | Poznań (ZTM) | Wrocław (MPK) |
|---|---|---|---|---|---|
| **Dziecko do 5 lat** | **działa** z wieku: 0 zł (dziecko do 30.09 roku 7. urodzin). Źr.: zdtm.lublin.eu, 2026-10-13. T: `test_wiek_daje_przejazd_bezplatny`, `test_wiek_6_zalezy_od_daty_podrozy` | **brak** reguły: UI zaznacza „ulgowy” (<18), więc 3-latek płaci 1,70 zł (sprawdzone). T: brak | **brak** reguły: 3-latek płaci 3,00 zł (ulgowy z UI). T: brak | **brak** reguły: 3,50 zł. T: brak | **działa przez UI**: „bezpłatny” zaznaczony dla ≤7 lat, kalkulator wieku nie czyta. Źr.: wroclaw.pl, 2026-10-10. T: brak testu wartości domyślnej |
| **Dziecko 6–14 z opiekunem** | **brak** | **brak** | **brak** | **brak** | **brak** |
| **Dziecko 6–14 samodzielnie** | **szacunek** wiek 7–14 → 0 zł przez założenie „uczeń podstawówki” (wiek tego nie dowodzi, notes ostrzega, ale typ ceny zostaje `OFFICIAL`). T: `test_dziecko_8_lat_zakladany_uczen_podstawowki_z_adnotacja` | **działa** ulgowy 50% (flaga, UI <18); uczeń podstawówki 0 zł (flaga RĘCZ.). Źr.: wtp.waw.pl, 2026-10-10. T: `test_ztm_warszawa_bilet_20_minutowy_ulgowy`, `test_ztm_warszawa_bilet_bezplatny_uczen_podstawowki` | **działa** ulgowy 50% (flaga, UI <18); uczeń podstawówki z Krakowa/Metropolii 0 zł (flaga RĘCZ.). Źr.: ztp.krakow.pl, 2026-10-10. T: `test_mpk_krakow_bilet_60_minutowy_ulgowy`, `test_mpk_krakow_bilet_bezplatny_uczen_podstawowki` | **działa** ulgowy 50% (flaga, UI <18); bezpłatny dla uczniów **nie** (źr.: ztm.poznan.pl, 2026-10-10). T: `test_ztm_poznan_bilet_90_minutowy_ulgowy` | **działa przez UI**: „bezpłatny” zaznaczony dla ≤21 lat (uczniowie do 21 lat, bez wymogu zamieszkania). T: `test_mpk_wroclaw_bilet_bezplatny_uczen` |
| **Młodzież 15–17** | **działa** ulgowy 50% (flaga, UI <18). T: `test_ztm_lublin_ulgowy` | **działa** ulgowy 50% (flaga) | **działa** ulgowy 50% (flaga) | **działa** ulgowy 50% (flaga) | **działa przez UI**: 0 zł (≤21) |
| **Student (22 l.)** | **nie działa**: student polskiej uczelni bez ulgi (niepotwierdzone w źródle); ISIC do 26 lat zagr.: ulgowy (flaga). T: `test_dwudziestolatek_bez_flagi_placi_normalnie_student_polski_bez_ulgi` | **działa RĘCZ.** ulgowy 50% (studenci wymienieni w tytułach); UI nie ustawia. T: ogólny test ulgowego, testu „student” **brak** | **brak** (źródło w repo nie wymienia studentów polskich uczelni; `eligibility_info` ma pustą listę tytułów ulgowych dla Krakowa) | **brak** (źródło wymienia uczniów, nie studentów) | **działa RĘCZ.** ulgowy 50% (studenci i doktoranci). T: ogólny test ulgowego |
| **Uczeń** | podstawówka: 0 zł (flaga RĘCZ. albo założenie z wieku 7–14); ponadpodstawowa/policealna do 24 l.: ulgowy 50% (flaga RĘCZ.). T: `test_ztm_lublin_bilet_bezplatny_uczen_podstawowki` | podstawówka 0 zł (flaga RĘCZ.); ponadpodstawowa ulgowy | podstawówka 0 zł (flaga RĘCZ.); ponadpodstawowa ulgowy | ulgowy 50% (bezpłatny nie) | podstawowa i ponadpodstawowa do 21 lat 0 zł; policealna i szkoły zagraniczne do 24 l. ulgowy (flaga RĘCZ.) |
| **Senior 60+/65+/70+** | **działa** 65+: 0 zł z wieku lub flagi; emeryci: ulgowy (flaga RĘCZ.). T: `test_65_plus_a_nie_70_plus` | **działa** 70+: 0 zł (flaga, UI ≥70); emeryci do 70 lat ulgowy (flaga RĘCZ.). T: testu 70+ dla Warszawy **brak** | **działa** 70+: 0 zł (flaga, UI ≥70); emeryci do 70 lat ulgowy (flaga RĘCZ.). T: **brak** | **działa** 70+: 0 zł (flaga, UI ≥70); emeryci dowolny wiek ulgowy. T: `test_ztm_poznan_bilet_bezplatny_senior_70_plus` | **działa** 65+: 0 zł (flaga, UI ≥65). T: **brak** |
| **Osoba z niepełnosprawnością** | **brak** (tytułu nie ma w modelu) | **działa RĘCZ.** znaczna 26+ 0 zł, umiarkowana 26+ ulgowy (flagi). T: **brak** | **działa RĘCZ.** znaczna 0 zł (+ wąskie wyjątki dla „umiarkowanej”), umiarkowana ulgowy. T: **brak** | **działa RĘCZ.** znaczna / I grupa 0 zł (bez dolnej granicy 26 lat), umiarkowana ulgowy. T: **brak** | **brak** osobnego pola (opis mówi: zaznacz „bezpłatny” ręcznie) |
| **Cudzoziemiec** | **tylko ostrzeżenie** o zagranicznej legitymacji (`foreign.lublin`, ISIC) | **tylko ostrzeżenie** (`foreign.warsaw`) | **tylko ostrzeżenie** (`foreign.krakow`, ISIC). T: `test_krakow_ulgowy_ostrzega_o_isic` | **tylko ostrzeżenie** (`foreign.poznan`). T: `test_poznan_ulgowy_ostrzega_o_braku_uznania` | **tylko ostrzeżenie** (`foreign.wroclaw`, tłumaczenie przysięgłe). T Lublin/Warszawa/Wrocław: tylko ogólny `test_zagraniczna_legitymacja_polaka_ostrzega_o_uznawaniu` |
| **Posiadacz BahnCard** | nie dotyczy | nie dotyczy | nie dotyczy | nie dotyczy | nie dotyczy |
| **Karty PKP i miejskie** | **brak** (LUBIKA tylko jako źródło cennika) | **brak** (Karta Ucznia tylko jako opis tytułu) | **brak** | **brak** | **brak** |

Uwaga: karty miejskie typu City Card/Welcome Card są w module atrakcji (`attractions/data/city_cards.json`) i nie obniżają ceny odcinków w `fares/`.
SKM Warszawa i linia lotniskowa KM Płudy–Lotnisko Chopina dostają cenę biletu czasowego ZTM z tej samej kolumny, ale zawsze jako `ESTIMATE`
(honorowanie biletów ZTM wg raportu Gemini). Kolumna „Lublin” dotyczy wyłącznie ZTM Lublin; ŁKA i SKM Trójmiasto są w 1a, kolumna C.

### 1c. Komunikacja miejska w Niemczech i pogranicze

| Grupa | Berlin (BVG/VBB) | Hamburg (HVV) | Monachium (MVV) | Kolonia (VRS/KVB) | NRW (VRR eezy.nrw) | Görlitz (ZVON) | KD Zgorzelec–Görlitz | Bilet graniczny Zasieki–Forst |
|---|---|---|---|---|---|---|---|---|
| **Dziecko do 5 lat** | **brak** reguły: UI zaznacza „ulgowy” (<18), 3-latek płaci 2,50 EUR (sprawdzone). T: brak | **działa** `age<6` → 0 EUR. Źr.: HVV Beförderungsbedingungen, 2026-10-11. T: `test_dziecko_ponizej_6_lat_bezplatnie_granice_wieku` | **działa** `age<6` → 0 EUR. Źr.: mvv-muenchen.de, 2026-10-11. T: j.w. | **działa** `age<6` → 0 EUR. Źr.: vrs.de, 2026-10-11. T: j.w. | **nie działa**: brak reguły <6, 3-latek płaci cenę dorosłą (7,53 EUR przy 20 km; sprawdzone), a VRS (też NRW) daje 0. T: brak | **szacunek** `age<15` → 1,50 EUR (założony uczeń), reguły „gratis” brak. T: `test_granica_wieku_ulga_tylko_do_15_urodzin` | **działa** 0 zł dla wszystkich (nie zależy od wieku). Źr.: kolejedolnoslaskie.pl, odczyt 2026-10-13. T: `test_pociag_kd_zgorzelec_gorlitz_jest_za_0_zl_oficjalnie` | **działa (niejednoznaczne)** `age<6` → 0 zł; regulamin „do 6 lat” niejednoznaczny, flaga `dzieci_gratis_niejednoznaczne`. Źr.: regulamin KD, odczyt 2026-10-13. T: `test_dzieci_ponizej_6_lat_gratis` |
| **Dziecko 6–14 z opiekunem** | **brak** | **brak** | **brak** | **brak** | **brak** | **brak** | nie dotyczy (0 zł) | **brak** |
| **Dziecko 6–14 samodzielnie** | **działa** flaga `bvg_berlin_ulgowy` (Kurzstrecke 2,10, AB 2,50, ABC 3,50 EUR); UI zaznacza przy <18, nie tylko 6–14. Źr.: VBB 2026. T: `test_bvg_berlin_strefa_ab_ulgowy` | **działa** `hvv_dziecko` 1,50 EUR (UI 6–14). Źr.: hvv.de, 2026-10-09. T: `test_hvv_einzelkarte_dziecko` | **działa** `mvv_dziecko` 2,00 EUR. T: `test_mvv_einzelfahrkarte_zone_m_dziecko` | **działa** `vrs_koln_dziecko` 1,80 EUR (1b). T: `test_vrs_koln_dziecko_tansze_niz_normalny` | **działa** `vrr_dziecko` −50% także w suficie. Źr.: Preistabelle 01.06.2026 (bez daty weryfikacji). T: `test_vrr_kindertarif_50_procent_rabatu`, `…_dziala_tez_na_sufit_cenowy` | **szacunek** `age<15` → 1,50 EUR, zakładany uczeń. Źr.: zvon.de, 2026-10-13. T: `test_granica_wieku_ulga_tylko_do_15_urodzin` | 0 zł | **nie działa** pełne 5,00 zł (brak ulg ustawowych, §5 ust. 2). T: `test_uczniowie_studenci_i_dorosli_placa_pelna_cene` |
| **Młodzież 15–17** | **nie działa poprawnie**: źródło daje ulgę tylko 6–14, a UI zaznacza ją przy <18, więc cena zaniżona (AB 2,50 zamiast 4,00 EUR). T: brak | **brak** ulgi (Kindertarif tylko 6–14; UI nie zaznacza). T: brak | **brak** ulgi. T: brak | **brak** ulgi. T: brak | **brak** ulgi (`form.vrr_help`: od 15 lat cena pełna). T: brak | **nie działa** `age≥15` → 2,00 EUR. T: `test_granica_wieku_ulga_tylko_do_15_urodzin` | 0 zł | pełna cena |
| **Student** | **brak** (ulga tylko przez Semesterticket; `bvg_berlin.json::_sprawdzono_zagraniczne_legitymacje`) | **brak** (dane bez zasad studenckich) | **brak** | **brak** | **brak** (Semesterticket; `vrr_eezy.json::_sprawdzono_zagraniczne_legitymacje`) | **nie działa**. T: `test_student_nie_dostaje_ulgi` | 0 zł | **nie działa** (pełna cena) |
| **Uczeń** | **brak** statusu (tylko wiek 6–14 przez flagę) | **brak** | **brak** | **brak** | **brak** | **szacunek** (uczeń <15 założony z wieku) | 0 zł | **nie działa** |
| **Senior** | **brak** (65+ to płatny abonament VBB-Abo 65plus, niemodelowany) | **brak** | **brak** | **brak** | **brak** | **brak** | 0 zł | **nie działa** |
| **Osoba z niepełnosprawnością** | **działa** `bvg_berlin_schwerbehindert` → 0 EUR (Schwerbehindertenausweis + osobna Wertmarke). Źr.: bvg.de i vbb.de, 2026-10-10. T: `test_bvg_berlin_schwerbehindert_bezplatny` | **działa** `schwerbehinderte_wertmarke_de` → 0 EUR (§ 228 SGB IX). T: `test_hvv_schwerbehinderte_bezplatnie` | **działa**, jak HVV. T: `test_mvv_schwerbehinderte_bezplatnie` | **działa**, jak HVV. T: `test_vrs_koln_schwerbehinderte_bezplatnie` | **brak** (`vrr.py` nie obsługuje pola Wertmarke, komentarz w `fares/model.py`: „nie dotyczy VRR/BVG”) | **brak** | 0 zł | **brak** |
| **Cudzoziemiec** | **tylko ostrzeżenie** `foreign.germany` (dla `bvg_berlin_ulgowy`) | **brak** ostrzeżenia | **brak** ostrzeżenia | **brak** ostrzeżenia | **tylko ostrzeżenie** `foreign.germany` (dla `vrr_dziecko`) | **brak** | **brak** | **brak** |
| **Posiadacz BahnCard** | **brak** (City-Ticket nie zaimplementowany) | **brak** | **brak** | **brak** | **brak** | **brak** | **brak** | **brak** |
| **Karty PKP i miejskie** | **brak** (Deutschlandticket: dane są, kod ich nie czyta) | **brak** | **brak** | **brak** | **brak** | **brak** | **brak** | **brak** w cenie: bilety bez dopłaty 5 zł (Dolnośląski Bilet Weekendowy, Brandenburg-Berlin-Ticket, Schönes-Wochenende-Ticket) są tylko informacją w `notes` i fladze `breakdown`; `DiscountProfile` nie ma na to pól. T: `test_bilety_bez_doplaty_5_zl_jako_informacja_z_flaga` |

---

## Tabela 2. Spójność danych: kod × UI × API

Skróty: **UI** = `app.py` (Streamlit), **API** = `api/schemas.py` + `api/main.py`, **Model** = `fares/model.py::DiscountProfile`.

### 2a. Pola profilu, domyślne wartości, opisy

| Nr | Miejsce | Co się rozjeżdża | Skutek (dowód) | Test pilnuje? |
|---|---|---|---|---|
| 2.1 | Model `fares/model.py:159` ↔ API `api/schemas.py:10–31` | Pole `child_with_guardian` jest w Modelu i w UI (`app.py:718`, tylko dla wieku 6–14), **nie ma go w `DiscountProfileIn`**, mimo docstringu „to samo pole po polu”. | Przez API nie da się ustawić opiekuna. Lublin–Berlin A, dziecko 8 lat: API zawsze 178,68 PLN, UI bez opiekuna 175,62 PLN, UI z opiekunem 55,19 PLN. | **Nie.** `tests/test_ui_covers_discount_profile.py` sprawdza tylko pola z sufiksami `_bezplatny/_ulgowy/_dziecko/_schwerbehindert` |
| 2.2 | Model ↔ UI ↔ API, pozostałe pola | Pozostałe 22 pola Modelu ma kontrolkę w `app.py` i pole w API (sprawdzone parserem). `legitymacja_zagraniczna` w UI jest wyliczona z listy „Kraj legitymacji” (`_kraj_legitymacji in ("DE","other")`), w API jest polem bool. | Zgodne. Różni się sposób wprowadzenia. | Częściowo (`test_every_flag_has_checkbox_in_app`, `test_every_flag_in_api_schema`) |
| 2.3 | API `api/schemas.py:11,12,30,31` ↔ UI `app.py:673–674, 709` | API: `bahncard: str`, `pkp_ulga_kod: str`, `obywatelstwo: str`, `age: int` bez enumeracji i granic. UI: listy wyboru, wiek 0–120. | Błędna wartość nie daje 422, tylko cichy fallback. `bahncard="75"` dla odcinka DB 420 km: kalkulator rzuca `ValueError`, a `price_rail_leg` zwraca 147,00 PLN (0,35 PLN/km, „szacunek”) zamiast 131,00 EUR (Flexpreis bez karty) albo 98,25 EUR (BC25). Nieistniejący kod PKP na 150 km: 52,50 zamiast 45,00 PLN. | **Nie.** `tests/test_api.py:166` używa nieistniejącego kodu `"ulgowy"` i przechodzi, bo wycena jest zamockowana |
| 2.4 | UI `app.py:742–794` ↔ API | Domyślne wartości checkboxów zależne od wieku (`wiek < 18`, `wiek >= 70` itd.) istnieją tylko w UI. Kalkulatory ZTM Warszawa/Kraków/Poznań/Wrocław, BVG i VRR nie czytają wieku. | Ten sam pasażer, inna cena. Policzone atrapą dla 3 profili × 17 wariantów: **10 z 51 wyników różni się** UI vs API (np. dziecko 8 lat, Szczecin–Berlin C: UI 46,69, API 53,26 PLN; senior 70, Kraków–Görlitz A: UI 108,45, API 112,45 PLN). | **Nie** (`tests/test_ui_style.py::test_domyslne_wartosci_checkboxow_zaleza_od_wieku_jak_dotad` sprawdza tylko wiek 10) |
| 2.5 | UI `app.py:670–678` ↔ API `api/schemas.py:30` | Wiek domyślny w UI = 30, w API = `None` (brak wieku wyłącza ścieżki wiekowe: Young, dziecko, HVV/MVV/VRS <6, Lublin, ZVON, sugestie My/Jugend BahnCard). | Zapytanie API bez `age` = dorosły bez wyjątków. | **Nie** |
| 2.6 | UI `app.py:754` ↔ `i18n/pl.py:152` (`form.kinder_other`: „od 15 lat obowiązuje bilet normalny”), `fares/eligibility_info.py` (BVG: dzieci 6–14), komentarz w Modelu | `bvg_berlin_ulgowy` domyślnie `wiek < 18`, a ulga BVG dotyczy 6–14. | 15–17 lat dostają cenę ulgową (AB 2,50 zamiast 4,00 EUR). 0–5 lat płacą ulgową zamiast 0 (reguły „dzieci do N lat” w repo **brak**). | **Nie** |
| 2.7 | UI `app.py:789` ↔ `i18n/pl.py:168–169` (`free.wroclaw_help`) | `mpk_wroclaw_bezplatny` domyślnie `wiek <= 7 or wiek <= 21 or wiek >= 65`: pierwszy człon zbędny; `<= 21` zaznacza „bezpłatny” każdej osobie do 21 lat, a opis mówi o uczniach szkół podstawowych i ponadpodstawowych; „dzieci do 7 lat” w opisie vs `<= 7` w kodzie. | 19–21-latek niebędący uczniem dostaje domyślnie 0 zł zamiast ulgowego 50%. Student 22 lat nie jest dotknięty. | **Nie** |
| 2.8 | UI `app.py:794` ↔ `fares/ztm_lublin.py:41–55`, `fares/data/ztm_lublin.json:37` | Checkbox „bezpłatny” w Lublinie domyślnie dla `wiek <= 14`. Kalkulator sam z wieku nadaje 0 zł: <6 zawsze, 6 lat tylko do 30.09, 7–14 przez założenie „uczeń podstawówki w Lublinie” (`uczniowie_podstawowek_zakladany_wiek: [7, 14]`). | 6-latek w terminie po 30.09 jest w UI darmowy (checkbox), a w samym kalkulatorze płaci. Założenie ucznia daje `OFFICIAL`. | Częściowo (`test_wiek_6_zalezy_od_daty_podrozy` bez udziału UI) |
| 2.9 | `i18n/pl.py:107` (`age.help`) ↔ kod | Opis: „Używany tylko do PODPOWIEDZI zniżek… (VRR Kindertarif 6–14, ZTM Lublin ulgowy)”. W rzeczywistości wiek **bezpośrednio liczy cenę** w `international.py`, `international_pkp.py`, `ztm_lublin.py`, `zvon_gorlitz.py`, `_dzieci_do_6.py` (HVV/MVV/VRS), `bilet_graniczny_zasieki_forst.py` i `cards.py`. | Opis wprowadza w błąd: np. dorosły 30 l. 29,99 EUR, student 22 l. 18,99 EUR na PL↔DE wyłącznie z wieku. | **Nie** |
| 2.10 | `i18n/pl.py:131` (`form.pkp`: „Ulga PKP”), `app.py:709` | Jeden wybór `pkp_ulga_kod` steruje 6 kalkulatorami, ale **KM, KMŁ i ŁKA go ignorują** (cena normalna, `price_verified=False`), a Polregio/KD/KŚ stosują ulgę PKP IC (`_ULGI = pkp_intercity.json`), bo własnych tabel ulg Polregio w danych nie ma. Opisu w UI brak. | Pasażer z ulgą w Mazowszu, Małopolsce lub Łodzi widzi cenę pełną bez wyjaśnienia (jest tylko `powod_szacunku`). | Tak dla mechanizmu (testy KM/KMŁ/ŁKA), **nie** dla komunikatu w UI |
| 2.11 | `fares/vrr.py`, `fares/bvg_berlin.py` ↔ `fares/_dzieci_do_6.py`, `hvv.py`, `mvv.py`, `kvb.py` | Dzieci <6 lat jeżdżą bezpłatnie w HVV/MVV/VRS (kod), nie ma tej reguły w VRR i BVG. | Dziecko 3 lata w NRW (VRR) płaci cenę dorosłą, w Kolonii (VRS) 0. | **Nie** |
| 2.12 | `fares/_dzieci_do_6.py:9` ↔ `fares/data/{hvv,mvv,vrs_koln}.json` | Próg 6 lat jest **wpisany na sztywno w kodzie** (`WIEK_GRANICA = 6`), a pliki danych podają go tylko tekstem (`wiek_dziecko_lata`, `dzieci_ponizej_6_lat_bezplatnie.cytat`). Inne moduły (ZVON, Zasieki, Lublin, `international*.json`) czytają próg z JSON. | Zmiana danych nie zmieni kodu. | Tak (`test_dziecko_ponizej_6_lat_bezplatnie_granice_wieku`) |
| 2.13 | `i18n/pl.py:114–115` (`student.label`, `student.help`) ↔ transport | Checkbox „Zniżka uczniowska/studencka” dotyczy **tylko atrakcji** (`i18n/pl.py:114–115`), a w transporcie nie ma pola „student”; student 22 lat dostaje ulgi tylko po ręcznym wyborze kodu PKP i checkboxów miast. | Student 22 w UI: 13 z 17 wariantów e2e bez żadnej zmiany ceny względem dorosłego (tabela 4a). | **Nie** |

### 2b. Progi wieku w modułach

| Moduł | Próg | Gdzie zapisany | Źródło i data |
|---|---|---|---|
| PKP IC krajowe | dziecko **do 4 lat** 100% (kod `dzieci_do_4_lat`); uczeń do 24 l. 37%; student do 26 l. 51% | `pkp_intercity.json::ulgi_procent` (RĘCZ.) | tabela ulg PKP 11.02.2026; **bez daty weryfikacji** |
| PKP IC PL↔DE | **<6 lat** 100%; 6–14 lat −50% | `international_pl_de_pkp.json` (`niemowle_wiek_max: 6`) | cennik od 19.08.2026, zweryfikowany 2026-10-09 |
| DB PL↔DE | **<6** gratis; 6–14 z opiekunem gratis, samodzielnie −50% (niemiecki odcinek); Young **15–26** | `international_pl_de.json` | bahn.de 2026-10-09 (dziecko), 2026-10-07 (Young) |
| DB krajowe | **brak** (wiek nieczytany) | `fares/db.py` | brak |
| BahnCard (sugestie) | My BC **19–26**, Jugend BC **6–18** | `bahncard.json` | bahn.de 2026-10-11; promocja Jugend 0 EUR: 2026-10-07…2026-12-12 |
| HVV/MVV/VRS | <6 gratis (kod), 6–14 Kindertarif (flaga) | `_dzieci_do_6.py:9`, `app.py:758–764` | regulaminy, 2026-10-11 |
| VRR | 6–14 Kindertarif (flaga), <6 **brak** | `vrr.py`, `app.py:758` | Preistabelle 01.06.2026 (bez daty weryfikacji) |
| BVG | 6–14 (dane i opis), **UI `<18`** | `app.py:754` | VBB 2026 |
| ZVON Görlitz | ermäßigt **<15** (zakładany uczeń) | `zvon_gorlitz.json::ermaessigt_wiek_ponizej` | zvon.de 2026-10-13 |
| Zasieki–Forst | gratis **<6** (niejednoznaczne) | `bilet_graniczny_zasieki_forst.json` | regulamin KD, odczyt 2026-10-13 |
| ZTM Lublin | gratis do 30.09 roku **7. urodzin**, 65+, założony uczeń **7–14**; UI free **≤14 lub ≥65**, ulgowy **<18** | `ztm_lublin.json`, `app.py:742, 794` | zdtm.lublin.eu 2026-10-13 |
| MPK Wrocław | UI free **≤7, ≤21, ≥65**; kalkulator wieku nie czyta | `app.py:789` | wroclaw.pl 2026-10-10 |
| ZTM Warszawa, MPK Kraków, ZTM Poznań | UI free **≥70**, ulgowy **<18**; kalkulatory wieku nie czytają | `app.py:745–749, 774–784` | wtp.waw.pl, ztp.krakow.pl, ztm.poznan.pl 2026-10-10 |
| Atrakcje | `child_price.max_age` 6–21 lat (17 różnych par min/max), `senior_price.min_age` 60 (2 atrakcje) albo brak | `attractions/data/attractions.json` | per atrakcja |

Wniosek: dziecko „bezpłatne” to w repo cztery różne progi (<4, <6, ≤7, ≤14), seniorzy mają progi 60, 65 i 70; nie ma wspólnego źródła progów.

### 2c. Mnożniki i stałe bez źródła albo bez daty weryfikacji

| Stała | Wartość | Miejsce | Źródło | Data weryfikacji | Uwaga |
|---|---|---|---|---|---|
| `GENERIC_FALLBACK_PLN_PER_KM` | 0,35 PLN/km | `routing/pricing.py:19` | **brak** | **brak** | Używana dla DB Regio poza NRW i miastami, ODEG, KD Wrocław–Görlitz, trilex, S-Bahn poza obsługiwanymi miastami, autokarów innych niż Flix, długich odcinków lokalnych i błędów kalkulatora. W atrapie: **4 z 17 wariantów** (Kraków–Görlitz B, Szczecin–Berlin A, Wrocław–Drezno A i B) |
| `LOCAL_BUS_FLAT_PLN` | 4,00 PLN | `routing/pricing.py:1063` | **brak** (opisana jako PLACEHOLDER) | **brak** | Wliczana do sumy (patrz tabela 3). W atrapie: 2 z 17 wariantów (Wrocław–Drezno A i C) |
| `DEFAULT_BAGGAGE_ESTIMATE_PLN` | 150 PLN | `routing/pricing.py:23` | „typowa cena” bez URL | **brak** | Bagaż rejestrowany, loty |
| `GENERIC_FLIGHT_FALLBACK_PLN` | 350 PLN | `flights/calculator.py:11` | „rząd wielkości typowych cen”, bez URL | **brak** | Cena lotu bez wpisu w cache |
| `bahncard_mnoznik["100"]` | 0,0 | `db_flexpreis.json` | „ogólnie znana zasada”, **bez URL** | **brak** | BC25 i BC50 z bahn.de/faq (bez daty). Karty BC100 nie ma w `bahncard.json` |
| Pasma Flexpreis (10 wartości) | 25…182 EUR | `db_flexpreis.json` | regresja `46 + 0,17 EUR/km` z 4 próbek blogów i raportu vzbv | **brak** | Pasma ≤150 km nie zgadzają się z formułą (50 km: 25 vs 54,50; 100 km: 38 vs 63,00; 150 km: 55 vs 71,50). Dystans to linia prosta |
| Progi `progi_km` Super Sparpreis Europa | 350 / 525 km | `international_pl_de.json` | „nasze przybliżenie” do 3 przykładów | kwoty 2026-09-29; progi **bez daty** | |
| `german_portion_fraction` | 0–1 | `routing/pricing.py:390` (6 punktów przejść) | **brak** (geometria przybliżona) | **brak** | Steruje rabatem BahnCard i dziecięcym na PL↔DE |
| `ulgi_procent` PKP | 37/49/51/78/95/100% | `pkp_intercity.json` | URL tabeli ulg z 11.02.2026 | `data_weryfikacji: null` (**brak**) | Używane też przez Polregio, SKM, KM, KMŁ, ŁKA, choć to tabela PKP IC |
| Pasma PKP IC | 76 pasm | `pkp_intercity.json` | URL cennika od 23.07.2026 | `data_weryfikacji: null` (**brak**) | Powyżej 1000 km ekstrapolacja (`_uwaga_powyzej_1000km`) |
| `CITY_TARIFF_AREAS` | promienie 11–20 km | `routing/pricing.py:81` | **brak** | **brak** | Koło zamiast granicy strefy. Podobnie: BER 2,5 km, SKM Trójmiasto 20 km, ŁKA 9 km, prostokąty NRW |
| Dobór biletu BVG po czasie jazdy | ≤15 min = Kurzstrecke, ≤120 = AB | `bvg_berlin.json::wazny_min`, `bvg_berlin.py` | **brak** reguły czasowej w cenniku (Kurzstrecke zależy od liczby przystanków) | **brak** | Heurystyka kodu |
| Najniższa strefa HVV/MVV/VRS | Ringe 1–2 / Zone M / 1b | `hvv.py`, `mvv.py`, `kvb.py` | cenniki oficjalne | 2026-10-09 / 2026-10-09 / 2026-10-11 | Cena oficjalna, ale **zastosowanie** przybliżone (brak mapowania przystanków na strefy) |
| VRR eezy.nrw | 1,73 EUR + 0,29 EUR/km, sufit C 19,80 | `vrr_eezy.json` | Preistabelle „Stand 01.06.2026” | data wejścia w życie, **bez daty weryfikacji** | Brak URL i daty w `breakdown` |
| ZTM Warszawa/MPK Kraków/ZTM Poznań/MPK Wrocław | ceny biletów czasowych | `ztm_warszawa.json`, `mpk_krakow.json`, `ztm_poznan.json`, `mpk_wroclaw.json` | URL w `_zrodlo` | data tylko **tekstem** (2026-10-06/07/10), brak pola maszynowego | Nie trafia do `breakdown` ani do UI |
| Kurs EUR | 4,3775 PLN | `common/currency.py` | NBP, tabela A | 2026-10-09 | Stały, służy do sum i rankingu |
| FlixBus fallback | 0,27 PLN/km | `flixbus_fallback.json` | kalibracja 72 odpowiedzi API | 2026-10-11 | Rozrzut Q1 0,209 – Q3 0,303; w `breakdown` tylko etykieta `fallback_km` |
| Stałe rankingu | 40 PLN/h, kary 60 min/50 PLN i 20 min/30 PLN | `routing/scoring_config.py` | „SZACUNEK, do strojenia” | **brak** | Wpływa na „kompromis”, nie na ceny |
| Dane „wg Gemini” | SKM Trójmiasto (21 pasm), KMŁ (30 pasm), ŁKA (3 bilety), honorowanie biletów ZTM w SKM/KM lotniskowej | `skm_trojmiasto.json`, `koleje_malopolskie.json`, `lka_lodz.json` | raporty `research/skm-km-tabele.md`, `research/km-malopolskie.md`, `research/ztm-lka-regio.md` — **tych plików w repo nie ma** | 2026-10-12 | Wszystko `ESTIMATE`; KMŁ ma `obowiazuje_od: null` |
| `deutschlandticket.json` | 63 EUR/mies. | `fares/data/deutschlandticket.json` | iamexpat.de (wtórne) | 2026-09-27 | **Żaden kod nie czyta** |
| `flights/data/extras_placeholder.json` | bagaż, dojazd | `flights/data/` | PLACEHOLDER (`_uwaga`) | **brak** | |

Odnośniki do plików, których nie ma w repo: `research/ui-styl.md` (`README.md:184`), `research/zrodla-znizek-kart.md` (`README.md:388`, `fares/README.md:45`),
`research/skm-km-tabele.md`, `research/ztm-lka-regio.md`, `research/km-malopolskie.md` (`fares/README.md:263,338`, `fares/koleje_malopolskie.py`).
W `research/` są tylko `audyt-taryf-db.md`, `ui-projekt.md`, `ui-przeglad.md` i ten plik.

---

## Tabela 3. Oznaczenia cen: typ odcinka i źródło z datą

Kryterium: każdy odcinek ma typ (OFICJALNA TARYFA / SZACUNEK / BRAK CENY), a odcinek oznaczony OFICJALNA TARYFA ma w `breakdown` źródło (URL) **i** datę
(to jedyne, co UI może pokazać; `ui_helpers.py::leg_source`). Kolumna „Przykład” to cena odcinka dla dorosłego policzona prawdziwym kodem na odcinku testowym
(`price_leg`, wiek 30; źródło danych: skrypt audytu poza repo). „Źr./data w UI” = `leg_source` zwrócił URL i datę.

| Przewoźnik / produkt | Typy możliwe | Co decyduje o typie | Przykład (dorosły) | Źr./data w UI | Ocena |
|---|---|---|---|---|---|
| PKP IC krajowe TLK/IC | OFICJALNA | zawsze `oficjalna_taryfa` (`pkp.py`), także dla km z linii prostej | 46,00 PLN (OFICJALNA) | URL **tak**, data **nie** (`data_weryfikacji: null`) | **nie spełnia**: OFICJALNA bez daty; pasmo z linii prostej, a taryfa liczy km po torach |
| PKP IC EIC/EIP | SZACUNEK | `is_pkp_premium_train` wymusza `szacunek` | 67,00 PLN (SZACUNEK) | nie | spełnia (typ jawny) |
| PL↔DE (DB + PKP + SPI) | SZACUNEK (zawsze) | `international.py` i `international_pkp.py` zwracają `ESTIMATE` | 29,99 EUR (SZACUNEK) | URL/data tylko w `zakres_cen` (SPI), nie w głównym `breakdown` | spełnia (typ jawny); kwota „od” jest oficjalna, a oznaczona SZACUNEK |
| DB krajowe (Flexpreis) | SZACUNEK | `db.py` zawsze `ESTIMATE` | 131,00 EUR (SZACUNEK) | nie | spełnia; dane **bez daty** weryfikacji |
| DB Regio / S-Bahn poza miastami i NRW | SZACUNEK | `_fallback_priced_leg` | 30,85 PLN (SZACUNEK) | nie | spełnia (typ jawny); stawka 0,35 PLN/km **bez źródła** |
| Polregio/KD/KŚ | OFICJALNA tylko po torach z potwierdzonym pasmem bez ulgi; inaczej SZACUNEK | `distance_along_track` i `potwierdzone` | 23,00 PLN (OFICJALNA po torach; SZACUNEK z linii prostej) | URL i data **tak** (2026-10-12) | spełnia |
| Koleje Mazowieckie | j.w. | j.w. | 26,50 PLN (SZACUNEK, linia prosta) | tak (2026-10-13) | spełnia |
| Koleje Małopolskie | SZACUNEK | dane wg Gemini | 27,60 PLN (SZACUNEK) | tak (2026-10-12) | spełnia |
| SKM Trójmiasto | SZACUNEK | dane wg Gemini | 11,00 PLN (SZACUNEK) | tak (2026-10-12) | spełnia |
| ŁKA (Łódź) | SZACUNEK | dane wg Gemini | 4,40 PLN (SZACUNEK) | **nie** (data w JSON, nie w `breakdown`) | spełnia (typ jawny), bez źródła w UI |
| SKM Warszawa / KM lotniskowa (bilet ZTM) | SZACUNEK | wymuszone w `price_pl_local_rail_leg` | 3,40 PLN (SZACUNEK) | nie | spełnia (typ jawny) |
| ZTM Lublin | OFICJALNA; SZACUNEK po przekroczeniu najdłuższego biletu | `przekroczono` | 4,60 PLN (OFICJALNA) | tak (2026-10-13) | spełnia; **uwaga**: 0 zł z założenia „uczeń 7–14” też jest OFICJALNA |
| ZTM Warszawa | OFICJALNA / SZACUNEK | j.w. | 3,40 PLN (OFICJALNA) | **nie** | **nie spełnia** |
| MPK Kraków | j.w. | j.w. | 4,00 PLN (OFICJALNA) | **nie** | **nie spełnia** |
| ZTM Poznań | j.w. | j.w. | 5,00 PLN (OFICJALNA) | **nie** | **nie spełnia** |
| MPK Wrocław | j.w. | j.w. | 3,20 PLN (OFICJALNA) | **nie** | **nie spełnia** |
| BVG/VBB Berlin | OFICJALNA / SZACUNEK | j.w. (`przekroczono`) | 4,00 EUR (OFICJALNA) | **nie** | **nie spełnia** |
| HVV Hamburg | OFICJALNA | zawsze `OFFICIAL` | 4,10 EUR (OFICJALNA) | **nie** | **nie spełnia**; cena najniższej strefy, zastosowanie przybliżone |
| MVV Monachium | OFICJALNA | zawsze `OFFICIAL` | 4,20 EUR (OFICJALNA) | **nie** | **nie spełnia**; jak HVV |
| VRS/KVB Kolonia | OFICJALNA | zawsze `OFFICIAL` | 4,00 EUR (OFICJALNA) | **nie** | **nie spełnia**; jak HVV |
| VRR eezy.nrw | OFICJALNA | zawsze `OFFICIAL` | 8,90 EUR (OFICJALNA) | **nie** | **nie spełnia**; wzór `1,73 + 0,29 × km` z sufitem C, linia prosta |
| ZVON Görlitz | OFICJALNA | zawsze `OFFICIAL` | 2,00 EUR (OFICJALNA) | tak (2026-10-13) | spełnia; ulga <15 z założenia ucznia |
| KD Zgorzelec–Görlitz | OFICJALNA / SZACUNEK | status w JSON | 0,00 PLN (OFICJALNA) | tak (2026-10-13) | spełnia |
| Bilet graniczny Zasieki–Forst | OFICJALNA | zawsze `OFFICIAL` | 5,00 PLN (OFICJALNA) | tak (2026-10-13) | spełnia |
| FlixBus | SZACUNEK | zawsze `ESTIMATE` (API na żywo albo fallback) | 117,78 PLN (SZACUNEK, fallback 0,27 PLN/km) | nie (`zrodlo` to etykieta, nie URL) | spełnia (typ jawny) |
| Autokary inne niż Flix | SZACUNEK | fallback | 82,37 PLN (SZACUNEK) | nie | spełnia; stawka bez źródła |
| Loty (Travelpayouts) | SZACUNEK | zawsze `ESTIMATE` | 311,93 PLN (SZACUNEK, z cache); 500,00 PLN przy fallbacku 350 + bagaż 150 | nie | spełnia (typ jawny); fallback bez źródła |
| Odcinek transgraniczny przewoźnika spoza PKP IC/DB (ODEG, KD Wrocław–Görlitz) | SZACUNEK | fallback 0,35 PLN/km | 44,46 PLN (SZACUNEK) | nie | spełnia (typ jawny); stawka bez źródła |
| Kolej podmiejska poza znanymi taryfami | SZACUNEK | `price_suburban_leg` | 4,22 PLN (SZACUNEK) | nie | spełnia (typ jawny) |
| Autobus lokalny w mieście bez taryfy (np. Drezno) | BRAK CENY | `wartosc_zastepcza` | 4,00 PLN wliczone w sumę, UI „BRAK CENY” | nie | **nie spełnia** spójności: patrz niżej |
| Obszar Görlitz, operator spoza ZVON | BRAK CENY | `cena_nieznana` | 0,00 PLN, **nie** wliczone w sumę | nie | spełnia |
| Odcinek pieszy | brak statusu | `oficjalna_taryfa` 0 PLN, bez statusu w UI | 0,00 PLN | nie dotyczy | spełnia |

**Przewoźnicy i produkty, które nie spełniają warunku „oficjalna taryfa ⇒ źródło z datą”: 10 modułów**
(1) PKP Intercity krajowe TLK/IC (URL jest, daty brak), (2) ZTM Warszawa, (3) MPK Kraków, (4) ZTM Poznań, (5) MPK Wrocław, (6) BVG/VBB Berlin,
(7) HVV, (8) MVV, (9) VRS/KVB, (10) VRR eezy.nrw. W 8 z nich (ZTM Warszawa, MPK Kraków, ZTM Poznań, MPK Wrocław, BVG, HVV, MVV, VRS) data weryfikacji istnieje w JSON jako tekst w `_zrodlo`, ale nie trafia do `breakdown`; VRR ma tylko „Stand: 01.06.2026” (data wejścia w życie), a PKP IC pole `data_weryfikacji: null`.

**Inne niespójności oznaczeń**
- **Typ OFICJALNA mimo założenia:** ZTM Lublin (0 zł z wieku 7–14 jako „uczeń podstawówki”), ZVON (<15 jako „uczeń”), HVV/MVV/VRS/BVG (najniższa strefa), PKP IC (km z linii prostej).
  Moduły Polregio, KM, KMŁ i SKM w tej samej sytuacji (linia prosta) obniżają typ do SZACUNEK, PKP IC i VRR nie.
- **BRAK CENY dwojako:** `cena_nieznana` (Görlitz) daje 0,00 PLN poza sumą, a `wartosc_zastepcza` (autobus w mieście bez taryfy) dodaje 4,00 PLN do `total_price_pln`,
  choć `Itinerary.price_status` = „pelna”, a UI pokazuje „BRAK CENY”. W atrapie rekomendacja „Najtańsza” dla Wrocław–Drezno wskazuje wariant „BRAK CENY”.
- **PL↔DE zawsze SZACUNEK**, także gdy kwota „od” jest z oficjalnej strony (konserwatywne, ale cena nigdy nie jest OFICJALNA).

---

## Tabela 4. Wyniki end-to-end (6 tras × 5 profili, atrapa MOTIS)

Data podróży 2026-10-20, odjazd od 05:00, bagaż rejestrowany. Dla każdej trasy 2–3 itineraria atrapy (aneks). Ceny w PLN (EUR przeliczone kursem 4,3775), suma wariantu, bez lotów (brak tokena).
Oznaczenia: **of** = OFICJALNA TARYFA, **sz** = SZACUNEK, **bc** = BRAK CENY (status całego wariantu = najsłabszy odcinek, `itinerary_price_status`). Zakres „od–do” = `total_price_pln`–`total_price_pln_high` (przedział PKP SPI).
Profile: dorosły 30 l.; dziecko 8 l.; student 22 l.; senior 70 l.; BahnCard 25 (30 l.).

Dwa tryby wejścia: **UI** = profil z domyślnymi wartościami formularza dla danego wieku (tak liczy `app.py`: PKP „brak”, checkboxy miast wg `wiek`),
**RĘCZNY** = pasażer sam zaznacza przysługujące ulgi (PKP: dziecko `dzieci_mlodziez_szkolna_do_24_lat`, student `student_do_26_lat_doktorant_do_35_lat`, senior `emeryci_rencisci_2_przejazdy_rok`;
student dodatkowo ulgowy ZTM Warszawa i MPK Wrocław, bo tylko tam repo potwierdza tytuł studencki).

#### Tabela 4a. Tryb UI

| Trasa | Wariant atrapy | dorosły 30 | dziecko 8 | student 22 | senior 70 | BahnCard 25 (30 l.) | Identyczne z dorosłym |
|---|---|---|---|---|---|---|---|
| Lublin–Gdańsk | A: ZTM bus + IC + EIC + SKM | 124,60 sz | 120,00 sz | 124,60 sz | 120,00 sz | 124,60 sz | student, BC25 |
| Lublin–Gdańsk | B: IC + IC (bez EIC) | 114,00 of | 114,00 of | 114,00 of | 114,00 of | 114,00 of | dziecko, student, senior, BC25 |
| Lublin–Gdańsk | C: FlixBus | 117,78 sz | 117,78 sz | 117,78 sz | 117,78 sz | 117,78 sz | dziecko, student, senior, BC25 |
| Kraków–Görlitz | A: tramwaj + IC + KD + KD (0 zł) + ZVON | 112,45 of | 108,27 of | 112,45 of | 108,45 of | 112,45 of | student, BC25 |
| Kraków–Görlitz | B: IC + KD Wrocław–Görlitz (transgraniczny) | 111,22 sz | 111,22 sz | 111,22 sz | 111,22 sz | 111,22 sz | dziecko, student, senior, BC25 |
| Kraków–Görlitz | C: FlixBus | 100,03 sz | 100,03 sz | 100,03 sz | 100,03 sz | 100,03 sz | dziecko, student, senior, BC25 |
| Szczecin–Berlin | A: RE66 (ODEG) + S-Bahn | 56,72 sz | 53,65 sz | 56,72 sz | 56,72 sz | 56,72 sz | student, senior, BC25 |
| Szczecin–Berlin | B: PKP IC transgraniczny + U-Bahn | 99,76 sz | 57,78 sz | 95,39 sz | 99,76 sz | 80,33 sz | senior |
| Szczecin–Berlin | C: FlixBus + BVG | 53,26 sz | 46,69 sz | 53,26 sz | 53,26 sz | 53,26 sz | student, senior, BC25 |
| Lublin–Berlin | A: ZTM + IC + BWE + U-Bahn | 194,14–325,07 sz | 175,62 sz | 145,99–325,07 sz | 189,54–320,47 sz | 188,71–325,07 sz | — |
| Lublin–Berlin | B: FlixBus + BVG | 193,80 sz | 187,23 sz | 193,80 sz | 193,80 sz | 193,80 sz | student, senior, BC25 |
| Warszawa–Gelsenkirchen | A: BWE + ICE Berlin–Dortmund + RE | 747,09–878,02 sz | 715,06 sz | 698,94–878,02 sz | 743,69–874,62 sz | 598,30–734,66 sz | — |
| Warszawa–Gelsenkirchen | B: BWE + ICE Berlin–Gelsenkirchen | 704,73–835,66 sz | 693,88 sz | 656,58–835,66 sz | 704,73–835,66 sz | 555,94–692,30 sz | senior |
| Warszawa–Gelsenkirchen | C: FlixBus + RE | 290,53 sz | 271,05 sz | 290,53 sz | 290,53 sz | 290,53 sz | student, senior, BC25 |
| Wrocław–Drezno | A: KD + KD (0 zł) + trilex + DVB | 73,55 bc | 73,55 bc | 73,55 bc | 73,55 bc | 73,55 bc | dziecko, student, senior, BC25 |
| Wrocław–Drezno | B: KD Wrocław–Görlitz (transgr.) + DB Regio | 81,07 sz | 81,07 sz | 81,07 sz | 81,07 sz | 81,07 sz | dziecko, student, senior, BC25 |
| Wrocław–Drezno | C: FlixBus + DVB | 66,35 bc | 66,35 bc | 66,35 bc | 66,35 bc | 66,35 bc | dziecko, student, senior, BC25 |

Wariant „Najtańsza” (rekomendacja silnika): Lublin–Gdańsk B (114,00 of) dla wszystkich 5 profili; Kraków–Görlitz A; Szczecin–Berlin C; Lublin–Berlin B dla dorosłego, a A dla pozostałych;
Warszawa–Gelsenkirchen C; Wrocław–Drezno C (**bc**) dla wszystkich 5 profili.

Liczba wyników identycznych z dorosłym (z 17 wariantów): dziecko **7**, student **13**, senior **13**, BahnCard 25 **13** (razem **46 z 68**).
Statusy dorosłego: **2 of**, **13 sz**, **2 bc** (z 17).

#### Tabela 4b. Tryb RĘCZNY (ulgi zaznaczone ręcznie)

| Trasa | Wariant atrapy | dziecko 8 | dziecko 8 + opiekun | student 22 | senior 70 |
|---|---|---|---|---|---|
| Lublin–Gdańsk | A: ZTM bus + IC + EIC + SKM | 75,60 sz | 75,60 sz | 63,40 sz | 75,60 sz |
| Lublin–Gdańsk | B: IC + IC (bez EIC) | 71,82 of | 71,82 of | 55,86 of | 71,82 of |
| Lublin–Gdańsk | C: FlixBus | 117,78 sz | 117,78 sz | 117,78 sz | 117,78 sz |
| Kraków–Görlitz | A: tramwaj + IC + KD + KD (0 zł) + ZVON | 71,38 sz | 71,38 sz | 61,61 sz | 71,56 sz |
| Kraków–Görlitz | B: IC + KD Wrocław–Görlitz (transgraniczny) | 88,65 sz | 88,65 sz | 80,11 sz | 88,65 sz |
| Kraków–Görlitz | C: FlixBus | 100,03 sz | 100,03 sz | 100,03 sz | 100,03 sz |
| Szczecin–Berlin | A: RE66 (ODEG) + S-Bahn | 53,65 sz | 53,65 sz | 56,72 sz | 56,72 sz |
| Szczecin–Berlin | B: PKP IC transgraniczny + U-Bahn | 57,78 sz | 9,19 sz | 95,39 sz | 99,76 sz |
| Szczecin–Berlin | C: FlixBus + BVG | 46,69 sz | 46,69 sz | 53,26 sz | 53,26 sz |
| Lublin–Berlin | A: ZTM + IC + BWE + U-Bahn | 158,60 sz | 38,17 sz | 122,53–301,61 sz | 172,52–303,45 sz |
| Lublin–Berlin | B: FlixBus + BVG | 187,23 sz | 187,23 sz | 193,80 sz | 193,80 sz |
| Warszawa–Gelsenkirchen | A: BWE + ICE Berlin–Dortmund + RE | 715,06 sz | 594,63 sz | 697,24–876,32 sz | 743,69–874,62 sz |
| Warszawa–Gelsenkirchen | B: BWE + ICE Berlin–Gelsenkirchen | 693,88 sz | 573,45 sz | 656,58–835,66 sz | 704,73–835,66 sz |
| Warszawa–Gelsenkirchen | C: FlixBus + RE | 271,05 sz | 271,05 sz | 290,53 sz | 290,53 sz |
| Wrocław–Drezno | A: KD + KD (0 zł) + trilex + DVB | 59,23 bc | 59,23 bc | 53,81 bc | 59,23 bc |
| Wrocław–Drezno | B: KD Wrocław–Görlitz (transgr.) + DB Regio | 81,07 sz | 81,07 sz | 81,07 sz | 81,07 sz |
| Wrocław–Drezno | C: FlixBus + DVB | 66,35 bc | 66,35 bc | 66,35 bc | 66,35 bc |

Nawet po ręcznym zaznaczeniu wszystkich ulg identyczne z dorosłym są: dziecko **4 z 17**, student **8 z 17**, senior **10 z 17** wariantów.

#### Wyniki nieprawdopodobne lub identyczne

| Nr | Trasa / wariant | Obserwacja | Przyczyna w kodzie |
|---|---|---|---|
| 4.1 | Lublin–Gdańsk B | **114,00 of dla wszystkich 5 profili**. Po ręcznym wyborze ulgi PKP: dziecko 71,82 (−37%), student 55,86 (−51%), senior 71,82 (−37%). Plakietka „OFICJALNA TARYFA” pokazuje cenę pełną jako pewną dla dziecka i seniora. | UI domyślnie `pkp_ulga_kod="brak"`, wiek go nie ustawia (`app.py:709`) |
| 4.2 | Wrocław–Drezno A, B, C | **Wszystkie 5 profili identyczne w każdym z 3 wariantów** (tryb UI), a w trybie ręcznym wariant B nadal identyczny (81,07) i C (66,35). | KD Wrocław–Görlitz (transgraniczny), DB Regio i trilex idą w fallback 0,35 PLN/km bez ulg; FlixBus nie czyta profilu |
| 4.3 | Wszystkie warianty FlixBus (6 z 17) | Identyczne dla dorosłego, studenta, seniora i BC25; dziecko 8 l. różni się tylko przez odcinki lokalne BVG/RE (np. 271,05 vs 290,53). Każda cena FlixBusa to fallback 0,27 PLN/km z linii prostej (API niedostępne w atrapie): 436 km = 117,78 PLN, 932 km = 251,57 PLN. | `fares/flixbus.py` nie czyta `DiscountProfile`; brak danych cennika |
| 4.4 | Warszawa–Gelsenkirchen A i B | 704,73–878,02 PLN, czyli **0,73–0,78 PLN/km** wobec 0,30 PLN/km FlixBusa (2,4×). Suma łączy „od” BWE (29,99 EUR, najniższa możliwa) z **górną granicą** Flexpreis ICE (131,00 EUR). BC25 obniża A o ok. 149 PLN. | `fares/db.py` zwraca górną granicę, `international.py` cenę „od”; `build_itinerary` je sumuje |
| 4.5 | Kraków–Görlitz A vs B oraz Wrocław–Drezno A vs B | **Ten sam pociąg KD Wrocław–Zgorzelec/Görlitz kosztuje 38,70 PLN (OFICJALNA, 141,5 km po torach) albo 50,22 PLN (SZACUNEK, +30%)**, zależnie od tego, czy MOTIS zgłasza go jako dwa odcinki, czy jeden transgraniczny. | `price_rail_leg`: odcinek transgraniczny przewoźnika spoza PKP IC/DB → fallback 0,35 PLN/km |
| 4.6 | Wrocław–Drezno C | „Najtańsza” = wariant z **BRAK CENY** (66,35), choć wariant B (81,07 sz) jest w pełni wyceniony. Suma 66,35 zawiera 4,00 PLN wartości zastępczej za autobus DVB w Dreźnie. | `LOCAL_BUS_FLAT_PLN` wchodzi do `total_price_pln`; brak taryfy Drezna |
| 4.7 | Kraków–Görlitz A, dziecko 8 vs senior 70 | 108,27 vs 108,45: bliskie, ale z różnych powodów (MPK ulgowy 2,00 PLN i ZVON 1,50 EUR vs MPK 0 zł). Dziecko 8 l. dostaje w Krakowie ulgowy, nie bezpłatny, choć uczniowie podstawówek z Krakowa jeżdżą bezpłatnie wg `mpk_krakow.json` (UI nie zna szkoły). | `app.py:746, 779` |
| 4.8 | Lublin–Berlin A, dziecko 8 l. | 175,62 (jedna kwota) vs dorosły 194,14–325,07 (przedział): kwoty nieporównywalne. Dziecko: przedziału SPI nie liczymy. Rabat dziecka 8 l. na BWE to tylko 29,99 → 27,51 EUR (−8%), bo rabat dotyczy niemieckiego odcinka (16,5% dystansu w linii prostej). | `spi_range_for_segment`, `german_portion_fraction` |
| 4.9 | Szczecin–Berlin B | 99,76 PLN (0,77 PLN/km), prawie 2× wariant A (56,72) i C (53,26). Różnica to „od” 19,99 EUR vs fallback 0,35 PLN/km. Student 22 l. 95,39 (Young 18,99 EUR). BC25 80,33: odcinek PKP −22% (udział niemiecki 89% dystansu), suma −19,5%. | `international.py`, `german_portion_fraction` |
| 4.10 | Lublin–Gdańsk A i B | IC Warszawa–Gdańsk 283 km (linia prosta) = 67,00 PLN zarówno dla EIC (szacunek), jak TLK (oficjalna): EIC wyceniany jak TLK. Przy km po torach większych o 10% pasmo dałoby 70 PLN, o 20%: 71 PLN. | `pkp.py` bierze `distance_km` (linia prosta), nie `distance_along_track_km` |
| 4.11 | Dziecko 8 l., Lublin–Gdańsk A | 120,00 sz: ZTM Lublin 0 zł z założenia „uczeń podstawówki w Lublinie” (typ OFFICIAL), reszta cena pełna. Taki sam wynik 120,00 ma senior 70 l. (65+, z wieku). Dwa różne tytuły, identyczna cena. | `ztm_lublin.py::_powod_bezplatny` |

---

## Lista luk (wg wpływu na użytkownika)

Wpływ: **wysoki** = zmienia kwotę lub jej wiarygodność w głównych trasach dla wielu pasażerów; **średni** = dotyczy węższej grupy albo mniejszej kwoty; **niski** = dane, opisy, testy.

### Wysoki

1. **UI nie stosuje ulg PKP dla dziecka, studenta i seniora.** Domyślnie `pkp_ulga_kod="brak"`, a wiek go nie ustawia: 46 z 68 wyników (tryb UI) identyczne z dorosłym, np. Lublin–Gdańsk B 114,00 „OFICJALNA” dla wszystkich profili (z ulgą 71,82 / 55,86 / 71,82). Kod `dzieci_do_4_lat` próg 4 lata, nietestowany (`app.py:709`, `fares/pkp.py`, tabele 1a, 4a).
2. **DB krajowe nie czyta wieku.** Dziecko, młodzież, student i senior płacą pełny Flexpreis, który jest sam górną granicą (SZACUNEK, pasma bez daty, pasma ≤150 km sprzeczne z własną formułą). Suma „od” BWE + górna granica ICE daje 705–878 PLN wobec 291 PLN FlixBusa na Warszawa–Gelsenkirchen (tabele 1a, 2c, 4.4).
3. **API liczy inaczej niż UI i nie waliduje wejścia.** Brak `child_with_guardian` w API, brak domyślnych ulg z wieku (10 z 51 wyników inne niż w UI), nieistniejący `bahncard` lub `pkp_ulga_kod` daje cichy fallback 0,35 PLN/km bez błędu 422 (tabela 2a, 2.1, 2.3, 2.4).
4. **FlixBus i loty bez profilu pasażera i bez realnych cen.** FlixBus: zawsze SZACUNEK, bez ulg, w atrapie 0,27 PLN/km z linii prostej (6 z 17 wariantów). Loty: wiek ignorowany, fallback 350 PLN + 150 PLN bagażu bez źródła; bez tokena Travelpayouts nie dało się policzyć żadnego lotu end-to-end (tabele 1a, 3, 4.3).
5. **Dzieci poniżej 6 lat w VRR, BVG, Warszawie, Krakowie i Poznaniu płacą cenę dorosłą albo ulgową.** HVV, MVV i VRS dają 0 EUR, VRR (też NRW) 7,53 EUR dla 3-latka na 20 km; UI zaznacza „ulgowy” dla <18. W repo brak reguły „dzieci do N lat” dla tych miast (tabele 1b, 1c, 2.11).
6. **Odcinki regionalne bez taryfy idą w 0,35 PLN/km bez źródła.** ODEG, KD Wrocław–Görlitz, DB Regio, trilex, S-Bahn poza obsługiwanymi miastami: 4 z 17 wariantów. Ten sam pociąg KD kosztuje 38,70 albo 50,22 PLN zależnie od podziału odcinków przez MOTIS (tabele 2c, 3, 4.5).

### Średni

7. **Brak taryf miejskich poza 9 miastami** (m.in. Drezno, Szczecin, Gdańsk/Gdynia ZTM i ZKM, Łódź MPK). Wartość zastępcza 4,00 PLN wchodzi do sumy i do rankingu, a wariant z „BRAK CENY” wygrywa „Najtańszą” (Wrocław–Drezno C, 4.6).
8. **„OFICJALNA TARYFA” bez źródła i daty w UI w 10 modułach:** PKP IC krajowe (brak daty), ZTM Warszawa, MPK Kraków, ZTM Poznań, MPK Wrocław, BVG, HVV, MVV, VRS, VRR. Daty istnieją w JSON jako tekst, ale nie w `breakdown` (tabela 3).
9. **PKP IC liczone z linii prostej, a oznaczone jako OFICJALNA.** Polregio, KM, KMŁ i SKM w tej samej sytuacji są SZACUNKIEM. EIC/EIP wyceniane z pasm TLK/IC (4.10).
10. **Domyślne wartości UI niezgodne z opisami:** BVG `wiek < 18` zamiast 6–14 (15–17 lat zaniżone), Wrocław „bezpłatny” dla każdego do 21 lat, Lublin „bezpłatny” 0–14 niezależnie od daty (2.6–2.8).
11. **Założenia o statusie z samego wieku oznaczone OFICJALNA:** ZTM Lublin (7–14 lat jako uczeń podstawówki), ZVON (<15 jako uczeń) (tabela 3).
12. **Student:** brak tytułu studenckiego w Krakowie, Poznaniu i dla polskich uczelni w Lublinie; w Niemczech ulgi studenckiej per przejazd brak (Semesterticket); PKP „Młodzież −25%” na PL↔DE i DB „Flexpreis Young −20%” niemodelowane. Student 22 l. w UI: 13 z 17 wariantów bez zmiany ceny (tabele 1a–1c, 4a).
13. **Senior:** brak progu wieku dla PKP (tylko RĘCZ. kod „emeryci 2 przejazdy/rok”), brak DB „Senioren” 65+ i BahnCard 60+, brak VBB-Abo 65plus. Progi 60/65/70 bez wspólnego źródła (tabela 2b).
14. **Niepełnosprawność:** brak w DB krajowym, PL↔DE, VRR i dla Lublina; Wrocław bez osobnego pola; Wertmarke tylko HVV, MVV, VRS i osobna flaga BVG; testów dla ZTM Warszawa/Kraków/Poznań na te tytuły brak (tabele 1a–1c).
15. **Niezmodelowane ulgi w KM, KMŁ i ŁKA:** pasażer z ulgą widzi cenę pełną jako „górną granicę” (SZACUNEK), bez komunikatu w UI (2.10).
16. **Produkty DB:** brak Sparpreis, Super Sparpreis krajowych, 1. klasy, Länder-Tickets, City-Ticket i Deutschlandticket (dane są, kodu nie ma), BahnCard 100 w `bahncard.json`; mnożnik BC100 bez URL (tabela 1a).

### Niski

17. **Dane „wg Gemini”, bez raportów w repo:** SKM Trójmiasto (21 pasm), KMŁ (30 pasm, brak `obowiazuje_od`), ŁKA, honorowanie biletów ZTM w SKM Warszawa i na linii lotniskowej KM. Raporty `research/skm-km-tabele.md`, `km-malopolskie.md`, `ztm-lka-regio.md`, `zrodla-znizek-kart.md`, `ui-styl.md` nie istnieją (tabela 2c).
18. **Stałe bez źródła lub daty:** 0,35 PLN/km, 4,00 PLN, 150 PLN, 350 PLN, promienie `CITY_TARIFF_AREAS`, dobór BVG po czasie jazdy, najniższa strefa HVV/MVV/VRS, stałe rankingu (tabela 2c).
19. **Opisy UI:** `age.help` twierdzi, że wiek tylko podpowiada, a on liczy ceny PL↔DE, Lublin, ZVON, HVV/MVV/VRS, Zasieki; `form.pkp` nie mówi, że KM/KMŁ/ŁKA ignorują ulgę (2.9, 2.10).
20. **Cudzoziemcy:** ostrzeżenia tylko dla PKP studenckich, 5 miast PL oraz BVG i VRR; brak dla HVV, MVV, VRS; testy tylko dla PKP, Krakowa, Poznania i testu ogólnego (tabele 1b, 1c).
21. **Brak testów:** kod `dzieci_do_4_lat`, `emeryci_rencisci_2_przejazdy_rok` i trzy kody niepełnosprawności PKP, `dzieci_mlodziez_szkolna_do_24_lat` na PKP IC, BC50 i BC100 przy cenie krajowej DB, 70+ w Warszawie, Krakowie i Wrocławiu, niepełnosprawność w ZTM Warszawa/Kraków/Poznań, domyślne checkboxy dla wieku innego niż 10 i 30, parytet UI–API, walidacja API, status UI (`OFFICIAL`/`ESTIMATE`) dla odcinka DB.
22. **Bezpłatne 0–4 lat w PKP (próg 4) kontra 6 w PL↔DE i HVV/MVV/VRS, ≤7 we Wrocławiu i Lublinie:** brak wspólnego źródła progów (tabela 2b).
23. **Nie zweryfikowano:** aktualności cen u przewoźników, realnego rozkładu i podziału odcinków w MOTIS (atrapa syntetyczna), działania UI w przeglądarce, powodów 12 testów pominiętych poza informacją, że wymagają działającego MOTIS.

---

## Aneks. Dane atrapy MOTIS (odcinki)

Czasy odjazdu 2026-10-20 (strefa +02:00), współrzędne przystanków przybliżone (stacje i adresy wpisane ręcznie). Odległości to linia prosta z `haversine_km`, jak w kodzie.

- **Lublin–Gdańsk.** A: ZTM Lublin Plac Litewski→Lublin Główny (2 km, 20 min); PKP Intercity Lublin Główny→Warszawa Centralna (155 km, 125 min); PKP Intercity „EIC” Warszawa Centralna→Gdańsk Główny (284 km, 175 min); SKM Trójmiasto Gdańsk Główny→Gdańsk Wrzeszcz (4 km, 12 min); pieszo. B: PKP Intercity Lublin Główny→Warszawa Zachodnia (156 km, 130 min); PKP Intercity „TLK” Warszawa Zachodnia→Gdańsk Główny (283 km, 240 min). C: FlixBus Lublin Główny→Gdańsk Główny (436 km, 540 min).
- **Kraków–Görlitz.** A: MPK Kraków Plac Wszystkich Świętych→Kraków Główny (1 km, 12 min); PKP Intercity Kraków Główny→Wrocław Główny (235 km, 255 min); Koleje Dolnośląskie Wrocław Główny→Zgorzelec (142 km po torach, 175 min, przystanki Legnica i Bolesławiec); Koleje Dolnośląskie Zgorzelec→Görlitz (2 km, 6 min); ZVON Görlitz→Hotel Börse (1 km, 9 min). B: PKP Intercity Kraków→Wrocław (235 km); Koleje Dolnośląskie Wrocław Główny→Görlitz (144 km, 190 min). C: FlixBus Kraków Główny→Görlitz (370 km, 420 min).
- **Szczecin–Berlin.** A: ODEG „RE66” Szczecin Główny→Berlin Hbf (127 km, 125 min); S-Bahn Berlin Hbf→Ostbahnhof (5 km, 9 min); pieszo. B: PKP Intercity Szczecin Główny→Berlin Hbf (127 km, 130 min); BVG Berlin Hbf→Alexanderplatz (3 km, 9 min); pieszo. C: FlixBus Szczecin Główny→Berlin ZOB (132 km, 150 min); BVG Berlin ZOB→Alexanderplatz (9 km, 25 min).
- **Lublin–Berlin.** A: ZTM Lublin (2 km, 20 min); PKP Intercity Lublin Główny→Warszawa Centralna (155 km); PKP Intercity „EC 45 Berlin-Warszawa-Express” Warszawa Centralna→Berlin Hbf (519 km, 330 min); BVG Berlin Hbf→Alexanderplatz (3 km); pieszo. B: FlixBus Lublin Główny→Berlin ZOB (653 km, 720 min); BVG Berlin ZOB→Alexanderplatz (9 km, 25 min).
- **Warszawa–Gelsenkirchen.** A: ZTM Warszawa Marszałkowska→Warszawa Centralna (1 km, 15 min); BWE Warszawa Centralna→Berlin Hbf (519 km); DB Fernverkehr Berlin Hbf→Dortmund Hbf (420 km, 270 min); DB Regio AG NRW Dortmund Hbf→Gelsenkirchen Hbf (25 km, 35 min). B: BWE; DB Fernverkehr Berlin Hbf→Gelsenkirchen Hbf (444 km, 300 min). C: FlixBus Warszawa Centralna→Dortmund ZOB (932 km, 900 min); DB Regio AG NRW Dortmund→Gelsenkirchen (25 km).
- **Wrocław–Drezno.** A: Koleje Dolnośląskie Wrocław Główny→Zgorzelec (142 km po torach); Koleje Dolnośląskie Zgorzelec→Görlitz (2 km); trilex Görlitz→Dresden Hbf (88 km, 95 min); Dresdner Verkehrsbetriebe Dresden Hbf→adres (0,5 km, 12 min). B: Koleje Dolnośląskie Wrocław Główny→Görlitz (144 km, 190 min); DB Regio AG Südost Görlitz→Dresden Hbf (88 km, 95 min); pieszo. C: FlixBus Wrocław Główny→Dresden Hbf (231 km, 270 min); Dresdner Verkehrsbetriebe (0,5 km, 12 min).

Profile trybu UI odtwarzają wyrażenia `value=` z `app.py:742–794` (np. `ztm_lublin_ulgowy = wiek < 18`, `ztm_warszawa_bezplatny = wiek >= 70`, `mpk_wroclaw_bezplatny = wiek <= 7 or wiek <= 21 or wiek >= 65`,
`vrr_dziecko/hvv_dziecko/mvv_dziecko/vrs_koln_dziecko = 6 <= wiek <= 14`, `bvg_berlin_ulgowy = wiek < 18`), z `pkp_ulga_kod="brak"`, `child_with_guardian=False`.
