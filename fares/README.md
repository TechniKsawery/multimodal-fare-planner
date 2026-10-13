# Moduł taryf (`fares/`)

Szacuje cenę pojedynczego segmentu podróży dla sześciu przewoźników:

- **PKP Intercity** (`fares/pkp.py`) — cena z tabeli pasm odległości × mnożnik ulgi. Tylko
  odcinki KRAJOWE (w całości w Polsce) — odcinek PL↔DE (patrz niżej) idzie osobną ścieżką.
- **DB** (`fares/db.py`) — Flexpreis jako górna granica z tabeli pasm odległości × mnożnik BahnCard
  (BahnCard 25 → ×0.75, BahnCard 50 → ×0.5). Tylko odcinki KRAJOWE (w całości w Niemczech).
- **Międzynarodowy PL↔DE** (`fares/international.py`) — jeden ciągły odcinek kolejowy
  przekraczający granicę (np. Berlin-Warszawa-Express). SZTYWNE kategorie cenowe wg relacji
  (Super Sparpreis Europa: krótka/średnia/długa), NIE tabela pasm jak PKP/DB. Wykrywane w
  `routing/pricing.py::is_cross_border_pl_de()` po prefiksie datasetu MOTIS stacji początkowej
  i końcowej (`pl`/`ztml` = Polska, `defv`/`derv` = Niemcy) — PRZED zwykłym `infer_rail_carrier()`,
  więc taki odcinek nigdy nie trafia do krajowej tabeli PKP/DB, nawet jeśli agencyName brzmi jak
  jeden z nich. BahnCard: oficjalnie rabat dotyczy tylko niemieckiego odcinka trasy — nie mamy
  podziału PL/DE, więc to uproszczone (patrz `_uwaga_bahncard` w
  `fares/data/international_pl_de.json`). Pasażerowie 15-26 lat (`DiscountProfile.age`) dostają
  zamiast tego taryfę "Super Sparpreis Europa Young" — JEDNA cena "od" dla wszystkich relacji
  (bahn.de nie publikuje progów zależnych od odległości dla tej oferty), BahnCard działa tak samo
  jak dla dorosłych. `age` NIE wpływa na żaden inny moduł taryf w tym katalogu — zob.
  `_uwaga_young` w `fares/data/international_pl_de.json`.
- **VRR** (`fares/vrr.py`) — taryfa eezy.nrw: cena = Grundpreis + cena za km (linii prostej),
  z sufitem cenowym. Obejmuje pociągi regionalne VRR ORAZ lokalny bus/tramwaj/U-Bahn w obszarze
  VRR (Zagłębie Rury/NRW) — to jedna, wspólna taryfa strefowa dla całego transportu VRR.
  `routing/pricing.py` stosuje ją WYŁĄCZNIE do odcinków, których oba końce leżą w NRW
  (`is_leg_in_nrw()`); poza NRW wynik jest niepotwierdzonym szacunkiem (`price_verified=False`).
  Zniżka: oficjalny Kindertarif (`DiscountProfile.vrr_dziecko=True`) — 50% rabatu dla dzieci
  6-14 lat, wliczając sufity cenowe (dzieci poniżej 6 lat jeżdżą bez biletu — nie modelowane).
- **ZTM Lublin** (`fares/ztm_lublin.py`) — taryfa czasowa (bilety 15/40/90-minutowe, strefa 1+2):
  dobiera najkrótszy bilet, którego czas ważności pokrywa czas jazdy odcinka z MOTIS.
- **BVG/VBB Berlin** (`fares/bvg_berlin.py`) — bilety Kurzstrecke/AB/ABC z cennika VBB od
  1.01.2026 (źródło i data w `fares/data/bvg_berlin.json`). Dobiera bilet wg czasu jazdy; gdy
  `Segment.tariff_zone == "ABC"` (routing/pricing.py ustawia to dla odcinka z/do lotniska BER,
  strefa C) — tylko bilet ABC. Wcześniej ABC wybierany był tylko jako „najdłuższy” bilet dla
  jazdy ponad 120 min (przy równym czasie ważności 120 min wygrywał AB), więc BER → centrum
  dostawało 4,00 EUR (AB) zamiast 5,00 EUR (ABC).
  Źródło tego, że BER leży w strefie C (vbb.de i bvg.de), ma w `bvg_berlin.json` pole
  `zrodlo_strefa_c_ber` (`vbb_url`: vbb.de/tickets/einzelfahrausweise/, `bvg_url`:
  bvg.de/de/touristen/verkehrsmittel-tarifbereiche, `data_weryfikacji` 2026-10-12, z cytatami). URL-e wg raportu
  `research/zrodla-znizek-kart.md` (Gemini) — niezweryfikowane niezależnie, bo strony przewoźników są
  niedostępne z chmury. Ceny bez zmian.
  Bilety BVG obowiązują też dla S-Bahnu Berlin (tryb MOTIS `SUBURBAN`) w kole 20 km wokół centrum.
- **Kolej podmiejska poza znanymi taryfami (SKM Szczecin, S-Bahn spoza Berlina i NRW)**
  — SKM Trójmiasto, SKM Warszawa i ŁKA w Łodzi mają od 2026-10-12 osobne taryfy (sekcja „Lokalne
  taryfy kolejowe” niżej). Dla reszty `fares/` NIE ma modułu ani danych w `fares/data/*`. `routing/pricing.py` (tryb
  `SUBURBAN`, `price_suburban_leg`) wycenia ją jako niepotwierdzony szacunek PLN/km
  (`price_verified=False`), a nie jako autobus za 4 PLN. To samo dotyczy odcinków, które feed
  oznaczył jako `BUS`, ale są dłuższe niż 20 km (`LOCAL_BUS_MAX_KM`, np. RB66 Szczecin ->
  Angermünde, 58 km: ok. 20 PLN, niepotwierdzone) — ryczałt 4 PLN zostaje tylko dla krótkich
  odcinków lokalnych. Dodanie modułu wymaga cennika z URL źródła
  i datą weryfikacji (jak pozostałe pliki w `fares/data/`).
- **FlixBus** (`fares/flixbus.py` + `fares/_flixbus_api.py`) — REALNA cena z publicznego
  (nieoficjalnego) API FlixBusa dla konkretnej daty przejazdu, z fallbackiem do zgrubnego
  szacunku PLN/km gdy API jest niedostępne/bez wyniku — patrz sekcja niżej.
- **HVV** (`fares/hvv.py`, Hamburg), **MVV** (`fares/mvv.py`, Monachium), **VRS/Köln**
  (`fares/kvb.py`) — dodane 2026-10-09, uzupełnione 2026-10-10 (pełne tabele stref/Preisstufen
  do odczytu informacyjnego + zniżka dla osób z ciężką niepełnosprawnością), żeby domknąć "pełny
  pakiet" (transport+atrakcje) dla miast, którym dociągnęliśmy atrakcje ([[attractions/]]).
  Każdy kalkulator wciąż zawsze LICZY (jako cenę segmentu) najniższą/bazową strefę cenową (brak
  mapowania przystanek->strefa) — patrz ograniczenia niżej. `routing/pricing.py` wybiera je, gdy
  oba końce odcinka leżą w obszarze miasta z `CITY_TARIFF_AREAS` (bez współrzędnych: nazwy jako
  całe słowa, `HVV_KEYWORDS`/`MVV_KEYWORDS`/`VRS_KOLN_KEYWORDS`). GTFS gtfs.de (FV/RV/NV) obejmuje
  całe Niemcy, a `docker-compose.de-full-city-gtfs.yml` dokłada pełne GTFS tych trzech miast.
  - **Zniżki/grupy osób zamodelowane (2026-10-10)**: Kindertarif 6-14 lat (`hvv_dziecko`/
    `mvv_dziecko`/`vrs_koln_dziecko`, dzieci do 6 lat jeżdżą bezpłatnie — poza zakresem pola, bo
    nie wymaga biletu) ORAZ bezpłatny przejazd dla osób z ciężką niepełnosprawnością
    (`schwerbehinderte_wertmarke_de` — § 228 SGB IX, Merkzeichen G/aG/H/Bl/Gl + ważna Wertmarke).
    Ta druga zniżka jest **ogólnoniemiecka** (nie taryfa konkretnego związku), więc jedno pole w
    `DiscountProfile` obsługuje identycznie wszystkie trzy miasta — zob. komentarz w
    `fares/model.py`. Zniżki specyficznie SENIORSKIE/STUDENCKIE na bilet JEDNORAZOWY nie istnieją
    w żadnym z trzech związków (sprawdzone: "Monatskarte 65"/"AKTIV60"/Semesterticket to produkty
    abonamentowe, nie rabat na Einzelkarte) — stąd brak odpowiednich pól, nie przeoczenie.

## Stan danych po researchu (2026-09-26, sekcja HVV/MVV/VRS zaktualizowana 2026-10-10)

| Przewoźnik | Status | Źródło |
|---|---|---|
| PKP Intercity — pasma cenowe (TLK/IC, 2. klasa) | **oficjalne** | [Cennik PKP Intercity](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Cennik_uslug_przewozowych_PKP_Intercity_tekst_ujednolicony_obowiazuje_od_23.07.2026_r.pdf), tekst ujednolicony od 23.07.2026 |
| PKP Intercity — ulgi ustawowe | **oficjalne** | [Tabele ulg ustawowych](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Ulgi%20ustawowe/Tabele_ulg_ustawowych_11-02-2026.pdf), stan na 11.02.2026 |
| VRR — eezy.nrw (Grundpreis + cena/km) | **oficjalne** | [Preistabelle VRR](https://www.vrr.de/fileadmin/user_upload/pdf/service/downloads/Weitere_Broschueren_und_Tarifinformationen/VRR_Preise_2026.pdf), Stand 01.06.2026 |
| VRR — Kindertarif (50% rabatu, dzieci 6-14 lat) | **oficjalne** | tamże, sekcja "Kinder 50% Rabatt pro Person und Fahrt inkl. Deckel" |
| DB — mnożniki BahnCard 25/50 | **oficjalne** | [bahn.de/faq/pk/angebot/flexpreis](https://www.bahn.de/faq/pk/angebot/flexpreis) |
| DB — tabela pasm odległości Flexpreis | **szacunek, skalibrowany do 1 realnej próbki** | DB nie publikuje takiej tabeli (cena dynamiczna); próba żywego wyszukiwania na bahn.de zablokowana jako ruch bota (błąd 751) — użyto zamiast tego realnej ceny Halle→München (373 km, 106–127 EUR) z bahndampf.de + oficjalnie cytowanej górnej granicy (150 EUR 2. klasa) do skalibrowania prostej formuły baza+km |
| ZTM Lublin — bilety czasowe (15/40/90 min, strefa 1+2) | **oficjalne** | [Cennik LUBIKA](https://lubika.zdtm.lublin.eu/cennik/) (system biletu elektronicznego ZDiTM Lublin), ważny od 16.02.2026 |
| Międzynarodowy PL↔DE — 3 kategorie cenowe (krótka/średnia/długa) | **oficjalne ceny "od", progi km SZACUNEK** | [Super Sparpreis Europa Polska](https://www.bahn.de/angebot/sparpreis-flexpreis/super-sparpreis-europa-polen), [zasada BahnCard tylko na niemiecki odcinek](https://int.bahn.de/en/offers/saver-fare-flexible-fare/super-saver-fare-europe-poland) — sprawdzone 2026-09-29 |
| Międzynarodowy PL↔DE — taryfa Young (15-26 lat) | **oficjalna cena "od" (MINIMUM, nie realna cena — bahn.de explicite nie podaje górnej granicy, "je nach Verfügbarkeit"), flat (bez progów km — tak reklamuje to bahn.de)** | [Super Sparpreis Europa Young Polen](https://www.bahn.de/angebot/sparpreis-flexpreis/super-sparpreis-europa-young-polen), [FAQ cena](https://www.bahn.de/bahnbusiness/faq/preis-super-sparpreis-europa-polen), [FAQ Young](https://www.bahn.de/faq/pk/angebot/sparpreis/young/super-sparpreis-young) — sprawdzone 2026-10-07 (2x, niezależnie) |
| HVV (Hamburg) — Einzelkarte/Tageskarte najniższa strefa + Kindertarif 6-14 | **oficjalne** | [hvv.de](https://www.hvv.de/), Tarifstand 01.01.2026 (zweryfikowane w przeglądarce 2026-10-09) + niezależnie potwierdzone komunikatem prasowym HVV `PM251028_Tarifanpassung.pdf` i wandernundmehr.at (wiek dziecka) 2026-10-10 |
| MVV (Monachium) — Einzelkarte Zone M + Kindertarif 6-14 | **oficjalne** | cennik MVV (ceny od 01.01.2026, zweryfikowane w przeglądarce 2026-10-09) + niezależnie potwierdzone muenchen.de i komunikatem prasowym MVV "Neue Fahrpreise...01.01.2027" 2026-10-10 |
| VRS/Rheinlandtarif (Kolonia) — Preisstufe 1b (miasto) + Kindertarif 6-14 | **oficjalne** (poprzednio ESTIMATE — mapowanie nazwa poziomu→kwota było niejednoznaczne) | [vrs.de](https://www.vrs.de/tickets/ticketsortiment/einzelticket) — tabela K/1a/1b/2/3 (Stand 01.06.2026), zweryfikowane w przeglądarce 2026-10-11; 1b = 4,00 EUR (stara tabela z dialogforum, 404, miała 3,50 EUR) |
| HVV/MVV/VRS — bezpłatny przejazd, ciężka niepełnosprawność (Wertmarke) | **oficjalne, podstawa ustawowa** | § 228 SGB IX ([gesetze-im-internet.de](https://www.gesetze-im-internet.de/sgb_9_2018/__228.html)); szczegóły Wertmarke (104/53 EUR, zwolnienia dla H/Bl i świadczeń socjalnych) wg [gegen-hartz.de](https://www.gegen-hartz.de/news/mit-dem-schwerbehindertenausweis-kostenlos-pnv-fahren-diese-regeln-sind-fix) — zweryfikowane 2026-10-10. Zasada ogólnoniemiecka, NIE taryfa związku — identyczna dla HVV/MVV/VRS (i, poza zakresem tej zmiany, docelowo też dla VRR/BVG). |

Każdy wynik niesie `price_type`: `PriceType.OFFICIAL` ("oficjalna_taryfa") tam, gdzie dane są
oficjalne, `PriceType.ESTIMATE` ("szacunek") tam, gdzie nadal szacujemy (obecnie: cały wynik DB,
bo tabela pasm jest interpolacją).

### Ważne ograniczenia (nawet tam, gdzie dane są "oficjalne")

- **PKP Intercity**: tabela obejmuje tylko pociągi **TLK/IC**. Ceny **EIC/EIP** w oficjalnym
  cenniku są ustalane **per konkretna relacja** (setki wierszy tabeli stacja→stacja), a nie wg
  prostych pasm odległości — nie są tu zaimplementowane. Realna cena rynkowa (z promocjami,
  ofertami specjalnymi) może być niższa niż "cena bazowa" z cennika.
- **VRR eezy.nrw**: sufit cenowy powinien zależeć od strefy cenowej (Preisstufe A/B/C) właściwej
  dla danej relacji, ale nie mamy mapowania geograficznego relacja→strefa, więc kalkulator zawsze
  używa najwyższego, sieciowego sufitu (Preisstufe C, 19,80 EUR). Dla krótkich, lokalnych relacji
  to zawyża rzeczywisty sufit (choć sama cena bazowa Grundpreis+km jest dokładna, dopóki nie
  osiągnie sufitu).
- **DB Flexpreis**: nie istnieje oficjalna tabela cena-za-km — cena Flexpreis jest wyliczana
  dynamicznie przez system rezerwacji DB per trasa/data/popyt. Tabela w
  `fares/data/db_flexpreis.json` to nadal przybliżenie.
- **ZTM Lublin**: ceny są oficjalne, ale (1) zawsze użyta jest cena strefy 1+2 (obejmuje całą
  sieć, w tym gminy ościenne) — nie mamy mapowania przystanek→strefa, więc przejazdy tylko w
  obrębie strefy 1 mogą być w rzeczywistości tańsze; (2) dobór biletu wg czasu jazdy z MOTIS to
  przybliżenie realnego biletu czasowego (liczonego od skasowania, może obejmować też
  oczekiwanie); (3) osobna "taryfa przystankowa" (bilet wg liczby przystanków) nie jest
  zaimplementowana.
- **Międzynarodowy PL↔DE**: DB nie publikuje tabeli relacja→kategoria cenowa, więc progi
  odległości (do 350/525 km) są NASZYM przybliżeniem dopasowanym do 3 podanych oficjalnie
  przykładów — zawodne blisko granic progów (Warszawa i Kraków z Berlina mają niemal identyczny
  dystans w linii prostej — 519 vs 532 km — mimo różnych kategorii cenowych, bo o kategorii
  decyduje rzeczywista trasa kolejowa, nie linia prosta). Ceny to "cena OD" (promocyjna,
  ograniczona pula) — cena rynkowa poza wczesną rezerwacją bywa wyższa. Rabat BahnCard
  (nominalnie 25% dla każdego poziomu karty — zweryfikowane na bahn.de, patrz
  `_uwaga_bahncard`) dotyczy oficjalnie TYLKO niemieckiego odcinka trasy — skoro nie mamy
  realnego podziału ceny PL/DE, `routing/pricing.py::german_portion_fraction()` szacuje udział
  niemieckiego odcinka geograficznie (linia prosta origin→przybliżony punkt granicy
  Rzepin/Frankfurt(Oder)→destination) i rabat jest naliczany proporcjonalnie do tego udziału,
  nie od całej ceny. Bez współrzędnych stacji (fallback) nadal liczymy 25% od całości — zawyża
  rabat, ale to jedyna opcja bez geografii.
- **HVV/MVV/VRS Köln**: każdy kalkulator zawsze liczy najniższą/bazową strefę cenową (Hamburg:
  Einzelkarte 1-2 Ringe; Monachium: Zone M; Kolonia: Preisstufe 1b) — brak mapowania
  przystanek→strefa, więc relacje wychodzące poza tę najniższą strefę są w rzeczywistości droższe
  niż wynik kalkulatora (pełne tabele stref są w `fares/data/*.json`, do odczytu informacyjnego).
  Od 2026-10-10 mapowanie nazwy poziomu→kwota dla VRS/Köln jest jednoznacznie potwierdzone
  (dialogforum.vrs.de), więc wszystkie trzy kalkulatory zwracają `price_type=OFFICIAL`. Żaden z
  trzech kalkulatorów nie jest jeszcze używany przez `routing/pricing.py` w praktyce — patrz
  uwaga przy opisie modułów wyżej.
- **Bezpłatny przejazd dla ciężkiej niepełnosprawności**: `DiscountProfile.schwerbehinderte_wertmarke_de`
  zeruje cenę biletu, ale NIE modeluje kosztu samej Wertmarke (legitymacji) — ona bywa płatna
  (104 EUR/12 mies. lub 53 EUR/6 mies.) poza przypadkami zwolnienia (Merkzeichen H/Bl, określone
  świadczenia socjalne). To koszt roczny/półroczny niezależny od pojedynczej trasy, więc nie
  pasuje do modelu jednorazowego porównania segmentów (analogicznie do Deutschlandticket/BahnCard
  — zob. niżej). Pole dotyczy TYLKO HVV/MVV/VRS_KOLN — VRR i BVG_BERLIN nie mają jeszcze tej
  kategorii zamodelowanej (ta sama zasada ustawowa by tam zadziałała identycznie, ale to poza
  zakresem tej zmiany).

### PKP Super Promo International (SPI): przedział cen PL↔DE

Dla biletu PL↔DE (relacja polska stacja ↔ Berlin) silnik dokłada do wyniku
`breakdown["zakres_cen"]` = „od X do Y" wg oficjalnego cennika *Super Promo International
Polska–Niemcy* (ważny od 19.08.2026, tekst w `verification/zrodla-pdf/`, oryginalny PDF pod linkiem źródła). Dane:
`fares/data/pkp_spi_pl_de.json`, generowane `scripts/build_spi_data.py` (parser
`scripts/parse_spi_pdf.py`, strefy miejscowości wpisane ręcznie i sprawdzane względem tekstu PDF).

- Dolna granica = min(poziom I SPI, cena główna, czyli tańsza z DB „od" i PKP regularnego);
  górna = min(poziom V SPI, cena regularna PKP). Dla stacji w kilku pociągach bierzemy minimum
  poziomu I i maksimum poziomu V po wszystkich pociągach z cennika.
- `amount` (cena główna) zostaje dolną granicą jak dotąd; `Itinerary.total_price_pln_high` ma
  sumę z górnymi granicami. Etykieta: „szacunek: od X (źródło dolnej) do Y (źródło górnej)" — `od_zrodlo`/`do_zrodlo` w `zakres_cen`.
- Tylko dorosły (cennik SPI nie podaje ulg) i tylko 2. klasa. Dziecko/niemowlę: bez SPI.
- NIE modelujemy reguły przydziału poziomu na konkretny dzień (cennik jej nie podaje).
- Poza zakresem: Saxonia 132/133 i Via Regia 134/135 (Lipsk), Chopin i Carpatia (Monachium,
  miejsca sypialne). Relacje do Frankfurtu n. Odrą są w danych, ale nie wyceniane.
- DB „od" nadal nie ma górnej granicy w źródle. Wyniki weryfikacji: `verification/spi-cennik-weryfikacja-2026-10-11.md`.

### Czego by trzeba, żeby domknąć resztę

1. **PKP EIC/EIP per relacja** — jeśli potrzebne, można by wczytać całą tabelę relacji z cennika
   (jest w tym samym PDF-ie, str. 11–84) jako osobny, sztywny słownik stacja→stacja, analogicznie
   do poprzedniego podejścia VRR.
2. **VRR Preisstufe A/B/C per relacja** — potrzeba mapy stref cenowych VRR (miasta/gminy → strefa)
   z `Tarifgebiete, Regionen & Preisstufen` na vrr.de, żeby dobierać właściwy sufit zamiast zawsze
   najwyższego.
3. **DB Flexpreis** — więcej próbek realnych cen z bahn.de dla interesujących nas relacji PL↔DE
   (np. Berlin→Gelsenkirchen, Warszawa→Berlin) — mamy na razie tylko jedną (Halle→München).
   Automatyczne wyszukiwanie na bahn.de jest zablokowane jako ruch bota (błąd 751, kod 751,
   "Ihr Browser-Verhalten ähnelt dem eines Bots"), więc te próbki musi zebrać ktoś ręcznie,
   wpisując wyszukiwania na bahn.de i przekazując ceny.
4. **Międzynarodowy PL↔DE relacja→kategoria** — realna tabela relacja→kategoria cenowa (DB jej
   nie publikuje) zamiast naszego przybliżenia progami km. Podział trasy PL/DE dla rabatu
   BahnCard jest już szacowany geograficznie (`german_portion_fraction()`, patrz wyżej) zamiast
   flat 25% na całość — ale to nadal linia prosta do jednego stałego punktu granicy, nie realna
   geometria trasy kolejowej ani realny podział ceny biletu.

## POLREGIO / KD / KŚ: degresywna tabela zamiast 0,35 zł/km (2026-10-12)

`fares/polregio.py` + `fares/data/polregio_taryfa_podstawowa.json` zastępują sztywne
`0.35 PLN/km` dla pociągów regionalnych POLREGIO, Kolei Dolnośląskich i Kolei Śląskich w Polsce
tabelą pasm odległości (do 5 km, 6-10, ... do 800 km; 30 pasm). Taryfa jest silnie degresywna
(ok. 1,22 zł/km na 5 km, ok. 0,30 zł/km na 100 km), więc liniowa stawka
zaniżała krótkie trasy i zawyżała długie.

**Status weryfikacji: wszystkie 30 pasm POTWIERDZONE** (Gemini, 2026-10-12, gałąź
`gemini/taryfy-weryfikacja`) w Taryfie Przewozowej POLREGIO, tekst jednolity ze zm. 24 od
1.09.2026, Dział III, Rozdz. 1, Tabela nr 1; Koleje Dolnośląskie (cennik od 1.09.2026) i Koleje
Śląskie (TP-KŚ od 2.07.2026) mają te same stawki bazowe. Źródło i data są przy każdym paśmie w
pliku danych (pole `potwierdzone`). W sesji, w której powstał kalkulator, domeny przewoźników były
zablokowane (403 egress), więc potwierdzenie pochodzi z weryfikacji Gemini, nie z mojego odczytu.
Szczegóły: `verification/taryfy-skm-rb-weryfikacja-2026-10-12.md`.

**Co znaczy „potwierdzone”, a co zostaje szacunkiem.** Potwierdzona jest KWOTA pasma, ale pasmo
zależy od kilometrów taryfowych (po torach), a `leg.distance_km` z MOTIS to linia prosta, która je
zaniża (Wrocław–Kłodzko: ok. 79 km prosto, ok. 84 km po stacjach — pasmo do 90 km zamiast do 80).
Dlatego:
- gdy odpowiedź MOTIS ma geometrię odcinka (`legGeometry`) albo przystanki pośrednie
  (`intermediateStops`), routing liczy z nich km (`routing/motis_client.py::track_distance_km`,
  dłuższy z dwóch kandydatów, bez żadnego współczynnika) i ustawia
  `Segment.distance_along_track=True` oraz `Segment.distance_source`; wtedy
  `breakdown["odleglosc_taryfowa"]="po torach"`, `breakdown["zrodlo_km"]` i `notes` podają
  źródło kilometra, a przy potwierdzonym paśmie bez ulgi `price_type="oficjalna_taryfa"`.
  Uwaga: to suma odcinków prostych między punktami kształtu/przystankami, czyli dolne
  ograniczenie długości toru (bliższe prawdy niż cięciwa, ale nie pomiar taryfowy co do km);
  MOTIS nie zwraca `shape_dist_traveled` z GTFS;
- bez geometrii i przystanków (albo gdy kształt nie pasuje do stacji końcowych): linia prosta,
  `breakdown["odleglosc_taryfowa"]="linia prosta"`, opis (`notes`) z informacją o przybliżeniu i
  `price_type="szacunek"`;
- `breakdown["price_verified"]=True`, `zrodlo_url` i `data_weryfikacji` w `breakdown` w obu
  przypadkach, gdy pasmo ma potwierdzenie;
- cena z ulgą (procent od ceny bazowej, nie tabela ulg POLREGIO) ma `price_verified=False` i
  `price_type="szacunek"` także przy km po torach;
- pasmo bez `potwierdzone` (albo z pustą datą / URL-em niebędącym adresem http) jest
  niepotwierdzone (testy na fixture w `tests/fixtures/`).

Testy kilometrów po torach: `tests/test_track_distance.py` na syntetycznym fixture
`tests/fixtures/motis_kd_wroclaw_klodzko.json` (schemat MOTIS v6, przybliżone współrzędne; to nie
zapis prawdziwej odpowiedzi). Nie zweryfikowano w chmurze (mkuran.pl i MOTIS są niedostępne), czy GTFS `polish_trains`
zawiera `shapes.txt` ani co `legGeometry` zawiera bez niego; dlatego liczymy też z przystanków
pośrednich i podajemy w cenie, które źródło wygrało. Do sprawdzenia na żywym MOTIS.

Znane ograniczenia:
- POLREGIO w części województw stosuje własne taryfy regionalne (Pomorska, Podlaska,
  Małopolska, Podkarpacka, Świętokrzyska), nie Podstawową; wyszukiwarka nie zna województwa.
  Cennik POLREGIO „Załącznik 2 — bilety jednorazowe od 1.03.2026” to załącznik do taryfy
  pomorskiej, nie do Podstawowej.
- ŁKA ma dodatkowo tańszą taryfę „Łódzkie Łączy”, której tu nie ma (też w sekcji o ŁKA w Łodzi).

## Odcinki bez wyceny pociągiem (niewdrożone)

- **Szczecin Główny – Angermünde (RB66).** W październiku 2026 RB66 nie kursuje na tym odcinku
  (do 12.12.2026 komunikacja zastępcza autobusowa; potwierdzone w komunikatach przewoźników). Nie
  wyceniamy go jako pociągu VBB (taryfa stykowa Teil E, EUR): odcinek z feedu to autobus
  zastępczy, a do czasu zbadania jego ceny zostaje niepotwierdzony szacunek PLN/km
  (`price_type="szacunek"`, `price_verified=False`). Taryfę VBB Teil E (Szczecin – Angermünde,
  Szczecin – Tantow) można rozważyć dopiero, gdy pociąg wróci na trasę (od 13.12.2026) i kwoty
  zostaną odczytane z broszury VBB.
- **Koleje Mazowieckie.** Wdrożone osobno (Tabela nr 1 TP-KM, 27 pasm, potwierdzona 2026-10-13),
  patrz sekcja niżej. Wyjątek: linia lotniskowa Płudy - Lotnisko Chopina nadal na biletach ZTM.
- SKM Trójmiasto, SKM Warszawa, ŁKA w Łodzi i Koleje Małopolskie (Tabela nr 1 TP-KMŁ): wdrożone,
  patrz niżej.

## Lokalne taryfy kolejowe: SKM Trójmiasto, SKM Warszawa, ŁKA w Łodzi, Koleje Małopolskie (2026-10-12)

Wszystkie kwoty i zasady honorowania pochodzą z raportów Gemini z 2026-10-12
(`research/skm-km-tabele.md`, `research/ztm-lka-regio.md`, `research/km-malopolskie.md`) i mają status **„wg Gemini,
niezweryfikowane niezależnie”** (domeny przewoźników są z chmury zablokowane). Status jest w
`breakdown["status_weryfikacji"]`, w `notes` i w plikach danych. **Decyzja (CONTRIBUTING.md, „Dane
z zewnętrznych AI”): wszystkie te kwoty mają `breakdown["price_verified"]=False` i
`PriceType.ESTIMATE` do czasu drugiego niezależnego źródła** (otwarcie wskazanych PDF-ów/stron w
przeglądarce). Dla SKM Trójmiasto, Kolei Małopolskich i ŁKA przełącznikiem jest pole `status` w danych
(`potwierdzone.status` w paśmie SKM/KMŁ, `weryfikacja.status` w `lka_lodz.json`): po zmianie na inny
niż „wg Gemini, niezweryfikowane niezależnie” kwoty wracają do `price_verified=True`. Ranking
(`Itinerary.price_verified`) traktuje je więc jak szacunek.

- **SKM Trójmiasto** (`fares/skm_trojmiasto.py`, `fares/data/skm_trojmiasto.json`): tabela
  odległościowa Taryfy Pomorskiej, 21 pasm (7,00 zł do 6 km … 42,00 zł do 500 km), cennik
  C-PKP SKM obowiązujący od 1.03.2026 (Uchwała Zarządu nr 20/2026), Tabela nr 1 s. 15 PDF:
  https://www.skm.pkp.pl/files/user-uploads/ms/1_marca_2026/Cennik_1_marca_2026_po_zm_1.pdf .
  Ulgi 37% i 51% bierzemy z tabel ulg (nr 4 i 8) z pliku danych; inne ulgi to procent od ceny
  bazowej. `price_verified=False` zawsze (także dla cen bazowych i ulg z tabel), dopóki kwoty
  mają tylko raport Gemini. Bilety **ZTM Gdańsk i ZKM Gdynia nie są honorowane w SKM**
  (pasażer potrzebuje biletu kolejowego Taryfy Pomorskiej). Bilety strefowe Taryfy Pomorskiej
  (Bilet Miejski 8,50 zł, Bilet Trójmiejski 12,50 zł) NIE są modelowane, więc na dłuższych
  odcinkach cena z tabeli km może być wyższa niż realna najtańsza opcja. Archiwalne ceny
  2023-2024 (12,00 zł za 31-40 km, 10,00 zł za 19-24 km) nie obowiązują od 1.03.2026.
  Odległość: `Segment.distance_along_track=True` (km po torach) dałoby `PriceType.OFFICIAL`, ale
  dopiero przy niezależnie zweryfikowanej kwocie (dziś zawsze `ESTIMATE`); routing ustawia flagę, gdy w `leg.extra["distance_along_track_km"]` są km po torach z odpowiedzi
  MOTIS (PR #105, jeszcze niescalony); inaczej linia prosta i `PriceType.ESTIMATE` z opisem
  przybliżenia (pasmo bywa zaniżone).
- **SKM Warszawa** (bez nowego kalkulatora, `Carrier.ZTM_WARSZAWA`): cena odcinka SKM to bilet
  czasowy ZTM wybrany wg czasu jazdy: 20 min 3,40 zł (strefy 1+2), 75 min 4,40 zł (strefa 1),
  90 min 7,00 zł (strefy 1+2); ulgowy 50% z `ztm_warszawa_ulgowy`. Źródło honorowania:
  https://www.wtp.waw.pl/ceny-i-rodzaje-biletow/ (`_zrodlo_skm` w `ztm_warszawa.json`).
  **Koleje Mazowieckie i WKD nie honorują biletów czasowych ZTM** (Wspólny Bilet obejmuje tylko
  dobowe i dłuższe): odcinek KM/WKD w obszarze ZTM nie dostaje ceny ZTM, tylko niepotwierdzony
  szacunek 0,35 zł/km. Cena odcinka SKM/lotniskowego KM z biletu ZTM ma `price_verified=False`
  i `PriceType.ESTIMATE`, bo honorowanie biletów czasowych ZTM pochodzi z raportu Gemini
  (kwoty ZTM same w sobie są z cennika, odczyt z 2026-10-06). Wyjątek: linia lotniskowa KM Warszawa Płudy - Warszawa Lotnisko Chopina
  (w obu kierunkach, rozpoznawana po nazwach stacji) dostaje bilet czasowy ZTM
  (https://www.wtp.waw.pl/integracje/wspolny-bilet-ztm-km-wkd/ , `_zrodlo_km_wkd`).
- **ŁKA w Łodzi** (`fares/lka_lodz.py`, `fares/data/lka_lodz.json`): w Strefie A (granice Łodzi)
  honorowane są bilety MPK Łódź (cennika MPK Łódź w repo nie ma) i własne bilety strefowe ŁKA
  20 min 4,40 zł, 40 min 5,60 zł, 80 min 6,80 zł (wybór wg czasu jazdy, dłużej niż 80 min to
  szacunek). Źródło: https://lka.lodzkie.pl/Honorowanie-biletow-komunikacji-miejskiej-w-Lodzi/ .
  Bilety z aplikacji trzeba skasować kodem QR; Open Payment System i check-in/check-out nie są
  honorowane. Ulgi (ulgowy 50%: 2,20 / 2,80 / 3,40 zł) i bilety okresowe nie są modelowane:
  przy uldze pokazujemy cenę normalną; `price_verified=False` zawsze (kwoty tylko z raportu Gemini).
- **Koleje Dolnośląskie, Zgorzelec - Görlitz** (`fares/kd_zgorzelec_gorlitz.py`,
  `fares/data/kd_zgorzelec_gorlitz.json`): pociąg KD dokładnie między tymi stacjami (oba kierunki)
  jest bezpłatny (0 zł, oficjalna taryfa). Źródło: https://kolejedolnoslaskie.pl/oferty-taryfowe/oferty-przygraniczne/
  (odczyt 2026-10-13, treść strony sprawdzona przez właściciela projektu). Autobus zastępczy KD i
  ZVON EuropastadtTarif (komunikacja miejska) nie są objęte; dłuższe przejazdy (Wrocław - Görlitz)
  idą dalej ścieżką niepotwierdzonego szacunku.
- **Bilet graniczny Polska-Niemcy, Zasieki - Forst** (`fares/bilet_graniczny_zasieki_forst.py`,
  `fares/data/bilet_graniczny_zasieki_forst.json`, `Carrier.BILET_GRANICZNY_ZASIEKI_FORST`): stała
  cena 5,00 zł w jedną stronę (regulamin PDF, str. 1 §2 ust. 1), ważny na KD Zasieki - Zasieki(Gr)
  i DB Regio Zasieki(Gr) - Forst, obowiązuje od 2024-10-01. Brak ulg ustawowych (§5 ust. 2):
  uczniowie i studenci płacą pełną cenę. Z regulaminu: bilet na okaziciela, do 6 osób na blankiecie
  (§1 ust. 2); rower, bagaż i pies bezpłatnie (§2 ust. 3); przedsprzedaż 30 dni (§3 ust. 1); dzieci
  „do 6 lat" bezpłatnie (§2 ust. 2) — granica wieku niejednoznaczna, przyjęto wiek < 6 (flaga
  `dzieci_gratis_niejednoznaczne`). Bilet jest **dodatkiem** do biletu krajowego KD do Zasieki
  (strona KD: „oprócz biletu krajowego do Zasieki"): cena trasy z Wrocławia/Legnicy = bilet krajowy
  + 5,00 zł; komunikat w `notes`/`breakdown["dodatek_do_biletu_krajowego"]`. Źródła: regulamin
  https://kolejedolnoslaskie.pl/wp-content/uploads/2025/10/R_Bilet-graniczny-Polska-Niemcy_2024-10-01.pdf
  i https://kolejedolnoslaskie.pl/oferty-taryfowe/oferty-przygraniczne/ (odczyt 2026-10-13). Wycenia tylko odcinek
  pociągowy (KD lub DB Regio) z Zasieki do Forst w obie strony; odcinki cząstkowe, autobus
  zastępczy i dłuższe przejazdy idą dalej starą ścieżką (bez zgadywania ceny).
- **Koleje Małopolskie** (`fares/koleje_malopolskie.py`, `fares/data/koleje_malopolskie.json`,
  `Carrier.KOLEJE_MALOPOLSKIE`): wyłącznie **Tabela nr 1** taryfy przewozowej TP-KMŁ, 30 pasm
  biletu jednorazowego wg taryfy normalnej, 2. klasa, pociąg osobowy, cena brutto z 8% VAT (8,00 zł
  do 5 km … 62,40 zł do 800 km; 91-100 km = 31,30 zł). Dokument: „Załącznik nr 2 do Uchwały Zarządu
  „Koleje Małopolskie” sp. z o.o. nr 43/2026 z dnia 17 marca 2026 r.” (tekst jednolity po zmianie
  nr 8), PDF (Tabela nr 1 na s. 66):
  https://kolejemalopolskie.com.pl/brepo/panel_repo/2026/03/19/cpt2dx/taryfa-przewozowa-kml-zm8-ost.pdf ,
  raport `research/km-malopolskie.md` (gałąź `gemini/km-malopolskie`), sprawdzenie 2026-10-12.
  Źródło, cytat, data weryfikacji i status są w pliku danych (blok `zrodlo` oraz `potwierdzone` przy
  każdym paśmie). **Data wejścia w życie: brak** — raport jej nie odczytał, w danych jest to
  jawnie `"obowiazuje_od": null` (+ `obowiazuje_od_status`), a w `notes` „data wejścia w życie:
  brak w raporcie, niezweryfikowana”. **Wszystkie kwoty: „wg Gemini, niezweryfikowane
  niezależnie”**, więc `price_verified=False` i `PriceType.ESTIMATE`. Przełącznik jak w SKM:
  zmiana `potwierdzone.status` pasma na inny niż „wg Gemini, niezweryfikowane niezależnie” przywraca
  `price_verified=True` (a `PriceType.OFFICIAL` tylko przy km po torach). Przewoźnik: `routing`
  rozpoznaje `agencyName`/nazwę z MOTIS „Koleje Małopolskie” (wielkość liter, spacje, bez polskich
  znaków oraz skróty KMŁ/KML; pociąg, nie autobus) w `infer_pl_local_rail_carrier()`. Kilometry:
  `leg.extra["distance_along_track_km"]` (km po torach), gdy jest, inaczej linia prosta
  (`leg.distance_km`, pasmo bywa zaniżone, opis w `notes`). **Ograniczenia:** (1) tabela nie
  obowiązuje do/z Kraków Lotnisko — taki odcinek nie dostaje tej tabeli (szacunek 0,35 zł/km);
  (2) ulgi, bilety okresowe i łączne (np. WSPÓLNY KMK+KMŁ) nie są modelowane: przy uldze pokazujemy
  cenę normalną, niepotwierdzoną; (3) raport podaje też cenę 28,50 zł dla Kraków Główny - Jasło
  (rozkład K71), której w Tabeli nr 1 nie ma (patrz
  `verification/koleje-malopolskie-weryfikacja-2026-10-12.md`); wcześniejsza notatka o drugiej,
  regionalnej tabeli („Taryfa Małopolska”) nie jest tym raportem rozstrzygnięta. **Koleje
  Mazowieckie i inni przewoźnicy nie są tu ruszani** (POLREGIO w Małopolsce dalej dostaje Taryfę
  Podstawową). Testy: `tests/test_koleje_malopolskie_tariff.py`.

### Koleje Mazowieckie (Tabela nr 1 TP-KM, 2026-10-13)

`fares/koleje_mazowieckie.py`, `fares/data/koleje_mazowieckie.json`, `Carrier.KOLEJE_MAZOWIECKIE`:
bilet jednorazowy wg taryfy normalnej, 2. klasa, 27 pasm (do 5 km … 481–520 km), kwoty brutto
(brutto = netto + PTU, oba w danych). Źródło: oficjalny PDF „Załącznik do TP-KM z uwzględnieniem
zmian nr 1–6”, s. 13, Tabela nr 1
(https://www.mazowieckie.com.pl/sites/default/files/Za%C5%82%C4%85cznik%20do%20Taryfy%20przewozowej%20Kolei%20Mazowieckich-KM%20%28TP-KM%29%20z%20uwzgl.%20Zmian%20nr%201-6_0.pdf).
**Tabelę potwierdził właściciel projektu w PDF 2026-10-13** → `price_verified=True`
(`PriceType.OFFICIAL` tylko z km po torach, `leg.extra["distance_along_track_km"]`; linia prosta →
`ESTIMATE` z opisem przybliżenia). Baza: uchwała Zarządu KM 268/Z/2022 (w życie 1.07.2022), zmiana
nr 6 od 1.01.2025 tabeli cen nie zmienia (wg briefu, niezależnie nieodczytane). To rozstrzyga
dawny spór 15,30 vs 15,60 zł dla 31–40 km: oficjalna tabela ma **15,30 zł**. Nie modelujemy ulg,
biletów okresowych/czasowych; powyżej 520 km brak pasma → niepotwierdzony szacunek PLN/km. WKD to
inny przewoźnik i tej tabeli nie dostaje. Testy: `tests/test_koleje_mazowieckie_tariff.py`.

Ograniczenia (wspólne): obszary to koła, nie granice (`routing/pricing.py`: `SKM_TROJMIASTO_AREA`
20 km wokół Sopotu, `LKA_LODZ_AREA` 9 km wokół centrum Łodzi, SKM Warszawa/lotnisko: koło ZTM
15 km). Odcinek poza kołem (SKM do Wejherowa, ŁKA do Zgierza/Pabianic, SKM Warszawa do
Pruszkowa/Otwocka) nie dostaje tych taryf i idzie szacunkiem 0,35 zł/km. Bilet czasowy ZTM jako
cena odcinka SKM jest górną granicą dla podróży z przesiadkami (jeden bilet 75/90 min pokrywa
kilka odcinków), a kalkulator ZTM nie zna granicy stref 1/2 (bilet 75-minutowy dotyczy tylko
strefy 1). Testy: `tests/test_local_rail_tariffs.py`.

## FlixBus: realna cena z API zamiast szacunku po km (2026-09-26)

Wcześniej FlixBus (jak każdy nierozpoznany autokar dalekobieżny) był wyceniany bardzo z grubsza
jako `0.35 PLN/km` (`routing.pricing.GENERIC_FALLBACK_PLN_PER_KM`) — to sztucznie zaniżało jego
pozycję w rankingu wobec środków transportu z realnymi cenami. `fares/flixbus.py` teraz próbuje
najpierw pobrać REALNĄ cenę na konkretną datę z (nieoficjalnego, ale publicznie dostępnego,
używanego przez samą stronę flixbus.com) API:

1. `GET /search/autocomplete/cities` — zamienia nazwę miasta (np. `"Gelsenkirchen Hbf"`) na
   wewnętrzne `city_id` FlixBusa.
2. `GET /search/service/v4/search` — dla pary `city_id` + daty zwraca wszystkie przejazdy tego
   dnia; bierzemy najtańszy.

**FlixBus nie publikuje stałego cennika** (ceny są dynamiczne, jak w lotnictwie) — dlatego,
tak samo jak ceny lotów z Travelpayouts w `flights/`, wynik jest oznaczony jako
`PriceType.ESTIMATE` ("szacunek"), NIE `OFFICIAL`, nawet gdy pochodzi z API. Żeby mimo to dało
się odróżnić realną cenę z API od zgrubnego fallbacku po km, każdy wynik niesie w `breakdown`
pole `"zrodlo"`: `"api_flixbus_live"` albo `"fallback_km"`. Wynik z `"fallback_km"` ma dodatkowo
`"price_verified": False` (cena niepotwierdzona: UI i `demo.py` dopisują to samo co przy innych
szacunkach, a wariant nie wygrywa „Najtańszej” z cenami potwierdzonymi); wynik z live API tej
flagi nie ma.

### To API nie było testowane na żywo — przetestuj lokalnie

Sieć środowiska Claude (kontener chmurowy) blokuje `global.api.flixbus.com` (403 na CONNECT,
tak samo jak wcześniej mkuran.pl/gtfs.de/geofabrik.de — patrz `[[network-blocked-data-hosts]]`
w pamięci projektu), więc **`fares/_flixbus_api.py` nie zostało zweryfikowane na żywym ruchu**.
Kod jest napisany defensywnie (jasne błędy `FlixbusApiError` przy nieoczekiwanym kształcie
JSON-a zamiast cichego crasha) i zawsze ma fallback do PLN/km, więc silnik nie wywali się nawet
jeśli endpoint się zmienił — ale zanim zaczniesz polegać na realnych cenach, zrób lokalnie:

```python
from fares._flixbus_api import find_city_id, fetch_cheapest_trip
lublin = find_city_id("Lublin")
berlin = find_city_id("Berlin")
print(fetch_cheapest_trip(lublin, berlin, "2026-11-15"))
```

Jeśli któryś krok rzuci `FlixbusApiError` z komunikatem o nieoczekiwanym kształcie odpowiedzi,
napraw parsowanie w `_flixbus_api.py` na podstawie faktycznej odpowiedzi (endpoint community-known,
może się zmienić bez ostrzeżenia — patrz komentarz na górze pliku).

### Segment.travel_date

`fares.model.Segment` ma teraz opcjonalne pole `travel_date` (`"YYYY-MM-DD"`) — wymagane tylko
dla `Carrier.FLIXBUS` (pozostałe przewoźniki mają stałe taryfy, nie potrzebują daty). Bez
`travel_date` kalkulator FlixBus od razu spada do fallbacku po km. `routing/pricing.py`
(`price_flixbus_leg`) ustawia je automatycznie z `leg.depart`.

## Sugestia zakupu BahnCard (`fares/cards.py`, 2026-09-27)

PKP i DB mają różny mechanizm zniżek: ulgi PKP Intercity są **ustawowe** (przysługują z tytułu
wieku/statusu, nie trzeba nic kupować — po prostu ustawia się `DiscountProfile.pkp_ulga_kod`).
BahnCard jest **produktem do kupienia** — samo posiadanie zniżki nie wystarczy, trzeba osobno
policzyć, czy roczny koszt karty zwróci się w oszczędnościach na przewidywanej liczbie podróży.
Stąd osobny moduł, `fares/cards.py`:

```python
from fares.cards import suggest_bahncard

for s in suggest_bahncard(distance_km=550, journeys_per_year=2, age=22):
    print(s.opis)
```

`routing/card_suggestions.py` (`suggest_bahncard_for_itinerary`) robi to samo, ale bierze gotowy
`Itinerary` i sam wylicza sumę dystansów odcinków DB Fernverkehr w wariancie — używane w
`demo.py` (`--age`) i `app.py` (pole "Wiek pasażera" już istniejące dla ulg ZTM/VRR).

Warianty i ceny (`fares/data/bahncard.json`, sprawdzone 2026-10-11 na bahn.de/angebot/bahncard):

| Wariant | Cena roczna | Rabat na Flexpreis | Wiek |
|---|---|---|---|
| BahnCard 25 (standard) | 62,90 EUR | 25% | dowolny |
| BahnCard 50 (standard) | 244,00 EUR | 50% | dowolny |
| My BahnCard 25 | 39,90 EUR | 25% | 19–26 lat |
| My BahnCard 50 | 79,90 EUR | 50% | 19–26 lat |
| Jugend BahnCard 25 | 7,90 EUR (**0 EUR promocyjnie 2026-10-07 do 2026-12-12**) | 25% | 6–18 lat |

Bez podanego wieku pod uwagę brane są tylko warianty standardowe (dostępne każdemu). Wariant
promocyjny automatycznie przestaje być darmowy po dacie z `promocja_do` (`reference_date`
domyślnie = dzisiaj). Próg opłacalności: gdy karta się jeszcze nie zwraca przy podanej liczbie
podróży/rok, `CardSuggestion.journeys_needed_to_break_even` podaje, od ilu podróży rocznie się
opłaci — patrz `fares/cards.py` po szczegóły wzoru.

**Ograniczenie**: dotyczy wyłącznie Flexpreis DB (odcinki `Carrier.DB` w module taryf / DB
Fernverkehr w routingu) — nie obejmuje ulg PKP (już wliczonych przez `pkp_ulga_kod`) ani innych
przewoźników, dla których BahnCard nie działa. Bagaż nie jest tu liczony — dla kolei/autokarów
PL/DE jest bezpłatny i nie wpływa na próg; TODO w kodzie zaznacza, że przy przyszłym
porównaniu z lotami (gdzie bagaż rejestrowany realnie podnosi cenę) warto to doliczyć.

### Polityka wygasających promocji (np. Jugend BahnCard 25)

Gdy promocja wygasa (`promocja_do` w danych), dane **NIE są usuwane** z tabeli — kod sam
przełącza się na cenę standardową po tej dacie (`_effective_price()` w `fares/cards.py`,
porównanie z `reference_date`, domyślnie dzisiaj). Powód: (1) historia/źródło zostaje
udokumentowane, (2) jeśli DB przedłuży promocję, wystarczy zmienić jedną datę zamiast
przywracać usunięte dane, (3) nie trzeba pamiętać o "sprzątaniu" kodu po każdej wygasającej
ofercie — sam się dezaktywuje. Ta sama zasada obowiązuje dla każdej kolejnej czasowej promocji
dodanej do tego modułu.

### Research: inne korzystne okazje u innych przewoźników (2026-09-27)

Sprawdzone pod kątem czegoś analogicznego do BahnCard (kupowana karta/abonament dający % lub
stały rabat na wiele przejazdów):

- **PKP Intercity**: **brak** takiego produktu. Zamiast tego: system dynamicznych "poziomów
  Promo" (15–45% zależnie od terminu/obłożenia pociągu — to ceny biletów, nie karta), Karta
  Dużej Rodziny (bezpłatna, państwowa, ulga ustawowa — inny mechanizm niż zakup karty),
  "Bilet Seniora" (promocyjny produkt biletowy, nie abonament). Statutowe ulgi już są wliczone
  przez `pkp_ulga_kod` — nic do dodania.
- **FlixBus**: brak ogólnodostępnej karty/abonamentu; jedyne stałe zniżki to 10–15% dla
  posiadaczy ISIC/ESNcard (osobne członkostwo studenckie, wąska grupa, niepewna dostępność w
  Polsce) — uznane za zbyt niszowe, żeby modelować w silniku ogólnego użytku.
- **VRR / transport lokalny DE**: **Deutschlandticket** — ogólnoniemiecki bilet miesięczny,
  63 EUR/mies. od 2026-01-01 (wcześniej 58 EUR, dane w `fares/data/deutschlandticket.json`).
  Ciekawostka: własny sufit miesięczny taryfy eezy.nrw (`vrr_eezy.json`:
  `sufit_miesieczny_2_klasa`) to też 63 EUR — więc Deutschlandticket opłaca się bardziej niż
  same bilety VRR TYLKO gdy pasażer i tak przekroczyłby miesięczny sufit VRR ORAZ jeździ też
  transportem lokalnym poza obszarem VRR w tym samym miesiącu. **Nie wpięte w kalkulator** —
  silnik liczy pojedyncze trasy, nie miesięczne wzorce podróży, więc próg opłacalności
  (podróże/miesiąc, nie podróże/rok jak BahnCard) nie pasuje do obecnego modelu jednorazowego
  porównania tras. Dane zostawione udokumentowane na przyszłość (TODO), gdyby silnik kiedyś
  zaczął doradzać też osobom mieszkającym/dojeżdżającym regularnie w Niemczech.

## Użycie

```python
from fares import estimate_price
from fares.model import Carrier, DiscountProfile, Segment

segment = Segment(
    carrier=Carrier.PKP_INTERCITY,
    origin="Lublin", destination="Warszawa Wschodnia",
    distance_km=170,
    discounts=DiscountProfile(pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"),
)
result = estimate_price(segment)
print(result)  # np. "24.50 PLN (oficjalna_taryfa) — pkp_intercity"
print(result.breakdown)

vrr_segment = Segment(Carrier.VRR, "Gelsenkirchen Hbf", "Duisburg Hbf", distance_km=20)
print(estimate_price(vrr_segment))  # Grundpreis + km, oficjalna taryfa eezy.nrw
```

## Testy

```
pytest tests/test_fares.py
```

### Kalibracja fallbacku FlixBus (2026-10-11)

Fallback `pln_per_km` zmieniono z 0.35 na 0.27 (mediana z 72 prawdziwych cen API, 24 trasy PL-PL/PL-DE,
3 daty; próbka z datami w `fares/data/flixbus_calibration.json`, zbierana `scripts/calibrate_flixbus.py`).
Rozrzut jest duży (Q1 0.209, Q3 0.303), krótkie trasy są tańsze za km niż długie — to nadal szacunek.

## Nieoficjalne źródła cen (opcjonalne, domyślnie WYŁĄCZONE)

Gdzie nie ma oficjalnego API cen (DB, PKP IC), można włączyć nieoficjalne źródło:
`UNOFFICIAL_PRICES=1` (opcje: `UNOFFICIAL_PRICES_SOURCES=db,pkp`, `UNOFFICIAL_PRICES_PER_MINUTE=20`,
`UNOFFICIAL_PRICES_TTL_MIN=360`, `UNOFFICIAL_PRICES_CACHE_DIR`). Wspólna logika (przełącznik, limit
zapytań, cache na dysku): `fares/_unofficial.py`.

- **DB**: `fares/_db_vendo_api.py` woła lokalny serwis `tools/db-vendo-service` (db-vendo-client,
  `DB_VENDO_URL`, domyślnie http://127.0.0.1:3100). Wymaga `travel_date` w segmencie. Biblioteka
  zastrzega, że formalnie potrzebna jest zgoda DB, a API bywa blokowane.
- Każdy wynik to `PriceType.ESTIMATE`, `breakdown["zrodlo"]` = `nieoficjalne_db_vendo`, a w notes
  jest informacja o nieoficjalnym źródle. Każdy błąd, limit lub brak odpowiedzi = powrót do tabeli.
- Droga formalna (zgody, konta partnerskie): `verification/instrukcje-oficjalne-drogi-dostepu-2026-10-11.md`.
- **Test na żywo 2026-10-11 (komputer Ksaviego, 6 zapytań, profil dbnav):** DB odpowiedziało
  `OPS_BLOCKED` na każde zapytanie, więc źródło DB nie zwraca dziś cen i nie omijamy blokady
  (inne profile nie były próbowane). Kod zostaje jako opcja na wypadek zgody DB lub zmiany stanu.
- **PKP IC / KOLEO / bilkom:** brak publicznego źródła cen bez omijania zabezpieczeń (Koleo
  `connections` zwraca 406 "Nieprawidłowa wersja klienta", intercity.pl ma skrypt antybotowy,
  bilkom bez JSON-a z ceną bez sesji). Moduł PKP nieoficjalny NIE powstał; zostaje oficjalny cennik.
