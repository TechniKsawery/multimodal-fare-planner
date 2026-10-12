# `routing/` — silnik optymalizacji trasy (Sesja 4)

Dla podanej pary miast (jako `stopId` z MOTIS) i daty generuje kilka **wariantów** podróży
łączących routing kolejowy z MOTIS (Sesja 2) z modułami taryf `fares/` i `flights/` (Sesja 3,
3b), liczy dla każdego cenę/czas/przesiadki, sprawdza bezpieczeństwo przesiadek i wybiera
4 rekomendacje.

## Alternatywne huby/węzły przesiadkowe (Sesja 6)

Huby lot↔kolej (lotnisko wylotu + lotnisko przylotu + stacje dojazdowe po obu stronach,
`HubConfig`) są konfigurowane jako **lista** kandydatów (`rail_flight_rail_hubs`,
`flight_regional_hubs` w `generate_variants`) — silnik generuje jeden wariant na hub, więc
dopisanie alternatywnego lotniska/miasta przesiadkowego (np. lot przez Berlin vs Wrocław vs
Düsseldorf zamiast Dortmundu) to tylko dopisanie kolejnego `HubConfig` do listy w
`demo_route.py`, bez zmian w silniku.

Warianty "tylko kolej" biorą się przede wszystkim z JEDNEGO zapytania origin→destination do
MOTIS (różne itineraria, które silnik i tak zwraca dla tej samej relacji). To dobrze pokrywa
alternatywne przesiadki na trasie, którą MOTIS sam wybrał, ale nie pokrywa dwóch sytuacji:
przejazdu przez **inne miasto graniczne/węzeł**, którego MOTIS mógłby nie faworyzować w
topowych itinerariach (np. Poznań/Rzepin zamiast Warszawa/Berlin), oraz startu/końca z
**innego dworca w tym samym mieście**. Do tego służy `AlternativeStop` (`variants.py`):

- `via_hub_stops` — jawnie spina origin→via oraz via→destination jako dwa osobne zapytania do
  MOTIS (`build_rail_via_stop_variant`), zamiast liczyć na to, że MOTIS sam tak poprowadzi.
  Drugie zapytanie startuje z buforem `MIN_TRANSFER_MINUTES_WALK` po przyjeździe pierwszego
  odcinka (bez tego MOTIS łapał połączenie na styk kilku minut, poniżej nawet absolutnego
  minimum wykonalności) i węzeł pośredni jest jawnie oznaczony jako wymagający przejścia
  (`requires_walk=True`) — dwa niezależnie zapytane odcinki nie gwarantują tego samego peronu.
  **Limit objazdu** (patrz niżej, „Limit objazdu przez huby kolejowe”) odrzuca węzły, które nie
  leżą po drodze, i trasy wracające tą samą stacją.
- `alternative_origin_stops` / `alternative_destination_stops` — powtarza główne zapytanie
  "tylko kolej" z podmienionym dworcem startu/mety.

Wszystkie warianty kolejowe (główne zapytanie + alternatywy) są odchudzane WSPÓLNYM dedup po
sygnaturze trasy (sekwencja nazw origin/destination odcinków) — ta sama fizyczna trasa
znaleziona kilkoma drogami trafia do wyniku tylko raz, a błąd MOTIS dla jednej alternatywy
(`MotisError`, np. brak połączenia przez dany węzeł) ląduje w `SkippedVariant`, nie przerywa
reszty. Konkretne `stopId` dla `AlternativeStop` trzeba dobrać ręcznie (np. przez
`/api/v1/geocode` albo znajomość sieci) — silnik nie zgaduje sam, które miasta/dworce warto
sprawdzić.

## Bagaż rejestrowany czy podręczny (loty)

`RouteRequest.checked_baggage` (UI: pole "Bagaż rejestrowany (loty)", API: `checked_baggage`,
domyślnie `True`, jak wcześniej) steruje trzema rzeczami naraz: czy cena lotu zawiera bagaż
rejestrowany, bufor po lądowaniu przy budowie wariantu i próg przesiadki lot->kolej
(`flight_to_rail_minimum` w `transfers.py`: 90 min z rejestrowanym, 60 min bez). Wartość jest
zapisana w `Leg.extra["checked_baggage"]` odcinka lotu. To SZACUNKI, nie wytyczne przewoźników.
Bagaż podręczny per przewoźnik (limity wag i opłaty) jest osobnym zadaniem i nie jest tu modelowany.

### Limit objazdu przez huby kolejowe (`VIA_HUB_STOPS`, dziś Poznań Główny)

Gdy MOTIS nie ma bezpośredniej trasy (np. Kraków → Gorlice), wariant „Kolej przez Poznań Główny”
składał absurd: Kraków → Wrocław → Poznań → Wrocław → Tarnów → Stróże → Gorlice (32 h, 5
przesiadek). Dwa osobne zapytania spięte węzłem nie pytały, czy węzeł jest po drodze. Teraz
`build_rail_via_stop_variant` rzuca `MotisError` z powodem, a `generate_variants` wpisuje go do
`skipped` („Pominięte warianty”), gdy:

1. **Objazd w linii prostej:** `origin→via + via→destination > VIA_HUB_MAX_DETOUR_RATIO (1,5) ×
   origin→destination` (haversine; ta sama skala co `HUB_MAX_DETOUR_RATIO` dla hubów lotniczych).
   Gdy współrzędne znamy z zapytania (adres → adres daje `"lat,lon"`), odrzucenie następuje
   **przed** zapytaniem do MOTIS. Przy samych `stopId` limit liczymy ze współrzędnych odcinków po
   zbudowaniu wariantu. Brak współrzędnych = nie filtrujemy (jak `hub_is_detour`).
2. **Powrót tą samą stacją:** trasa przejeżdża dwa razy przez tę samą stację (współrzędne w
   promieniu `SAME_STATION_RADIUS_KM = 0,5 km`, a bez współrzędnych ta sama nazwa), np.
   Wrocław → Poznań → Wrocław. Przesiadka w jednym miejscu i dwa różne dworce jednego miasta
   (Berlin Hbf / Ostbahnhof) to nie powrót; dojścia piesze nie są liczone.

**Skąd próg 1,5.** Współczynniki dla Poznania (haversine, centra miast): Lublin → Berlin 1,00,
Lublin → Gelsenkirchen 1,02, Warszawa → Berlin 1,00, Kraków → Berlin 1,08, Katowice → Berlin 1,12,
Wrocław → Gelsenkirchen 1,19, Gdańsk → Berlin 1,20, Wrocław → Berlin 1,29 — Poznań po drodze albo
lekki łuk. Bez sensu: Zielona Góra → Berlin 2,19, Kraków → Warszawa 2,44, Szczecin → Berlin
3,40, Kraków → Gorlice 7,74. Próg 1,5 leży w luce między jednymi a drugimi (zapas ok. 0,2 nad
najgorszą sensowną trasą). Świadomy koszt: Gdańsk → Szczecin (1,53) odpada z wariantu przez
Poznań — tę relację pokrywa główne zapytanie origin → destination. Próg to heurystyka na
liniach prostych, nie na realnej sieci kolejowej. Testy graniczne (±0,0001° wokół 1,5) i
korytarze: `tests/test_via_hub_detour.py`.

## Dynamiczny dobór lotnisk (huby lot<->kolej)

Huby nie są stałą listą par: `routing/airports.py::discover_hubs` dobiera je dla każdego zapytania.
1. Lotniska z `routing/data/airports.json` (PL+DE, współrzędne) w promieniu 200 km od startu i celu.
2. Odrzucane są pary będące objazdem: lotnisko przylotu musi być bliżej celu niż wylotu, a droga
   start->wylot->przylot->cel w linii prostej <= 1,5 x bezpośrednia.
3. Do 16 najlepszych par sprawdzamy w Travelpayouts (`prices_for_dates`, `direct=true`, data, potem
   miesiąc). Bez biletu bezpośredniego w cache para odpada: to brak POTWIERDZENIA, nie dowód braku lotu.
4. Dojazd do lotniska: stacja z `AIRPORT_STATIONS`, a dla reszty współrzędne lotniska (MOTIS dobiera
   przystanek; bez przystanku w zasięgu wariant trafia do pominiętych).

Każda odrzucona para ma powód w "Pominięte warianty" (pary bez potwierdzenia są zgrupowane w jeden
wpis na powód). Tabela lotnisk nie mówi nic o rejsach; lot jest nadal bezpośredni, ze sztywnym czasem.

## Moduły

| Plik | Zawartość |
|---|---|
| `model.py` | `Leg`, `PricedLeg`, `Itinerary`, `TransferWarning`, `SkippedVariant` |
| `motis_client.py` | zapytania do `/api/v6/plan`, parsowanie itinerary → `Leg` (haversine dla distance_km) |
| `pricing.py` | dispatch `Leg` → `fares.estimate_price` (kolej) / `flights.estimate_price` (lot) |
| `transfers.py` | minimalne bezpieczne czasy przesiadek + wykrywanie ryzykownych |
| `scoring.py` | agregacja `PricedLeg` → `Itinerary`, wybór 4 rekomendacji |
| `variants.py` | generator wariantów (`RouteRequest`, `HubConfig`, `generate_variants`) |
| `demo_route.py` | konkretna konfiguracja dla `demo.py`: Lublin → Gelsenkirchen |

## Bezpieczeństwo przesiadek

MOTIS zwraca realny czas przejścia pieszego jako osobny leg `WALK` między odcinkami transitu —
korzystamy z tego do ustawienia `Leg.requires_walk` (czy przesiadka wymaga zmiany
peronu/dworca, czy jest na tym samym przystanku). Minimalne progi (SZACUNEK, nie oficjalne
zalecenia przewoźników — patrz `transfers.py`):

| Przesiadka | Minimum |
|---|---|
| kolej → kolej, ten sam peron/przystanek | 20 min |
| kolej → kolej, wymaga przejścia (jest leg WALK) | 30 min |
| kolej → lot | 120 min (dojście do terminala, odprawa, kontrola bezpieczeństwa) |
| lot → kolej | 90 min (wyjście z samolotu, bagaż, dojście/dojazd do stacji) |

Loty nie mają w tym module własnego rozkładu godzin (`flights/` daje tylko cenę, nie godziny
odlotu/przylotu) — `variants.py` przyjmuje **placeholder 2h czasu lotu** i buforuje odjazd/
przyjazd kolei wokół niego (120 min przed odlotem na odprawę, po przylocie 90 min z bagażem rejestrowanym albo 60 min z samym podręcznym; to te same stałe co progi przesiadek w `transfers.py`).
To wystarcza do liczenia bufora przesiadki, ale nie jest realnym rozkładem lotów.

## Wycena odcinków lotniczych: tylko bilet + bagaż (bez dojazdu/transferu)

`flights.estimate_price()` sam w sobie liczy bilet + bagaż + dojazd na lotnisko + transfer
z lotniska (patrz `flights/README.md`) — to poprawne, gdy ktoś wycenia lot samodzielnie, poza
tym silnikiem. W wariancie mieszanym (kolej + lot + kolej) dojazd na lotnisko i transfer z
lotniska do miasta docelowego są już osobnymi, realnie wycenionymi odcinkami kolejowymi
(`build_rail_flight_rail_variant` w `variants.py`) — doliczenie ich drugi raz z placeholderowej
tabeli `flights/data/extras_placeholder.json` podwójnie liczyłoby ten sam koszt.

Dlatego `pricing.price_flight_leg()` woła `flights.estimate_price()` z własnym
`ExtrasProfile`, w którym `airport_access_cost`/`destination_transfer_cost` są wyzerowane, a
`baggage_cost` bierze tylko pole `bagaz` z tabeli `flights/` dla danej relacji (albo
`DEFAULT_BAGGAGE_ESTIMATE_PLN` = 150 PLN, jasno oznaczone jako szacunek, gdy relacja nie ma
wpisu w tabeli). Rozbicie bilet/bagaż jest widoczne w `PricedLeg.breakdown` i wypisywane osobno
w `demo.py`/`app.py` dla odcinków lotu.

**Dopracowanie bagażu wg realnego cennika linii:** dopiero PO zapytaniu do Travelpayouts znamy
kod linii obsługującej najtańszy bilet (`result.breakdown["linia"]`, np. `"FR"` dla Ryanaira) —
za wcześnie, żeby użyć go przy budowaniu `ExtrasProfile` powyżej. Dlatego `price_flight_leg()`
po otrzymaniu wyniku sprawdza `flights.extras.get_baggage_by_airline(linia)`: jeśli przewoźnik
jest w tabeli realnych cenników (`flights/data/baggage_by_airline.json` — obecnie Ryanair, Wizz
Air, LOT, Eurowings), NADPISUJE placeholderowy/domyślny bagaż tą realną kwotą (przeliczoną do
waluty segmentu przez `routing/currency.py:convert`) i dopisuje źródło do
`breakdown["bagaz_zrodlo"]` oraz do notatki. Dla nieznanego przewoźnika zostaje bagaż z tabeli
relacji/domyślny szacunek — patrz `flights/README.md` po pełny opis i zastrzeżenie o
DYNAMICZNYCH opłatach za bagaż (kwoty w tabeli to dolna granica opublikowanego przedziału).

## Wycena odcinków kolejowych: mapowanie przewoźnika

`price_rail_leg()` najpierw sprawdza `pricing.is_cross_border_pl_de(leg)` — jeśli odcinek
przekracza granicę PL/DE jednym ciągłym przejazdem (np. Berlin-Warszawa-Express), wymusza
`Carrier.INTERNATIONAL_PL_DE` (patrz `fares/international.py`) i **pomija**
`infer_rail_carrier()` całkowicie, niezależnie od tego jak brzmi `agencyName`. Detekcja idzie
GEOGRAFICZNIE — po współrzędnych (`origin_lat/lon`, `destination_lat/lon` w `leg.extra`, wzięte
wprost z MOTIS) stacji początkowej i końcowej, ze zgrubnymi skrzynkami PL/DE
(`_PL_BBOX`/`_DE_BBOX` w `routing/pricing.py`). Prefiks datasetu MOTIS w `stopId` (`pl`/`ztml` =
Polska, `defv`/`derv` = Niemcy) jest tylko FALLBACKIEM gdy lat/lon brak — **NIE głównym
sygnałem**: prefiks datasetu to źródło FEEDU, nie kraj przystanku, a polski feed
(PolishTrainsGTFS) dla kursów międzynarodowych PKP Intercity publikuje też przystanki fizycznie
leżące w Niemczech pod prefiksem `pl_` (zaobserwowany bug 2026-09-29: Warszawa Wschodnia →
Berlin-Lichtenberg, oba `stopId` z prefiksem `pl_`, wyceniane błędnie jako krajowy PKP zamiast
międzynarodowy — naprawione przejściem na współrzędne jako główny sygnał). Brak jednoznacznego
kraju po którejś stronie (brak lat/lon i stopId, albo stacja w pasie przygranicznym ok.
14.0-14.9°E, gdzie skrzynki PL/DE nachodzą na siebie) → bezpiecznie `False` (leg idzie zwykłą,
krajową ścieżką wyceny zamiast fałszywie alarmować).

Granica PL/DE: skrzynki PL/DE nakładają się w pasie ok. 14.0-15.05°E (Görlitz leży na wschód od
14.9°E, Szczecin na zachód od Odry) — tam kraj rozstrzyga przybliżona łamana granicy Odra-Nysa
(`_PL_DE_BORDER_LINE`), z marginesem ok. 700 m, w którym nie zgadujemy (None). Odcinek
transgraniczny przewoźnika innego niż PKP Intercity/DB (np. DB Regio Szczecin–Berlin, Koleje
Dolnośląskie Wrocław–Görlitz) NIE dostaje taryfy międzynarodowej — moduły `fares/international*.py`
opisują oferty PKP Intercity/DB — tylko niepotwierdzony szacunek.

Dla odcinków KRAJOWYCH `pricing.infer_rail_carrier()` mapuje `agencyName` z MOTIS wyłącznie na
przewoźników dalekobieżnych:
- `"PKP Intercity"` → `Carrier.PKP_INTERCITY` (pociąg EIC/EIP po `routeShortName`: kwota z pasm
  TLK/IC, ale `price_type="szacunek"` i `breakdown["price_verified"]=False` — ceny EIC/EIP są w
  cenniku per relacja, których nie mamy)
- nazwa zawierająca `"DB Fernverkehr"`/`"Deutsche Bahn"` → `Carrier.DB`
- POLREGIO / Koleje Dolnośląskie / Koleje Śląskie, gdy OBA końce odcinka leżą w Polsce
  (`infer_pl_regional_carrier()`, kraj wg współrzędnych, bez nich wg prefiksu datasetu) →
  `Carrier.POLREGIO_PODSTAWOWA`: degresywna tabela odległościowa zamiast sztywnego 0,35 zł/km
  (`fares/polregio.py`). Kwoty pasm są potwierdzone (źródło i data w `breakdown`,
  `price_verified=True`). `leg.distance_km` to zawsze linia prosta; pasmo wybieramy jednak z
  km po torach, gdy MOTIS dał geometrię odcinka (`legGeometry`) albo przystanki pośrednie
  (`intermediateStops`): `motis_client.track_distance_km()` zapisuje je w `leg.extra`
  (`distance_along_track_km`, `distance_along_track_source`), a `price_rail_leg` przekazuje do
  `Segment.distance_along_track`/`distance_source`. Wtedy (kwota pasma potwierdzona, bez ulgi)
  `price_type="oficjalna_taryfa"`, a `breakdown["zrodlo_km"]` i `notes` mówią, skąd pochodzi
  kilometr. Bez geometrii i przystanków zostaje linia prosta i `price_type="szacunek"` (patrz
  fares/README.md). Odcinek transgraniczny albo bez ustalonego kraju tej tabeli nie dostaje.
- każdy inny przewoźnik (DB Regio, S-Bahn, ODEG, a w Polsce Koleje Mazowieckie, ŁKA, SKM, ...) →
  taryfa zależy od MIEJSCA:
  taryfa miejska, gdy oba końce leżą w obszarze miasta z `CITY_TARIFF_AREAS` (Berlin, Hamburg,
  Monachium, Kolonia — Verbundtarif obejmuje też S-Bahn/RE), a `Carrier.VRR` (eezy.nrw) **tylko
  gdy oba końce leżą w NRW** (`is_leg_in_nrw()`, konserwatywne prostokąty `_NRW_INNER_BOXES`).
  Wcześniej każda nazwa z `"regio"`/`"s-bahn"` szła do VRR z uzasadnieniem, że feed `derv` obejmuje
  tylko NRW — to nieprawda (`scripts/fetch_data.py` pobiera gtfs.de `rv_free`/`nv_free` dla całych
  Niemiec), a `"regio"` łapało też POLREGIO (błąd K2 z audytu).
- lokalne taryfy kolejowe w Polsce (`infer_pl_local_rail_carrier()`, tryb RAIL i SUBURBAN; oba
  końce odcinka w kole z `SKM_TROJMIASTO_AREA` / `LKA_LODZ_AREA` / kole ZTM Warszawa, bez
  współrzędnych wg nazw): **SKM Trójmiasto** → `Carrier.SKM_TROJMIASTO` (tabela Taryfy Pomorskiej,
  21 pasm; bilety ZTM/ZKM nie obowiązują w SKM), **ŁKA w Łodzi** → `Carrier.LKA_LODZ` (bilety
  czasowe ŁKA 20/40/80 min), **SKM Warszawa** → `Carrier.ZTM_WARSZAWA` (bilet czasowy ZTM jako
  cena odcinka). Kolej Mazowiecka i WKD **nie honorują** biletów czasowych ZTM (odcinek w obszarze
  ZTM dostaje niepotwierdzony szacunek, `_km_wkd_without_ztm_tickets()`), z wyjątkiem linii
  lotniskowej Warszawa Płudy - Warszawa Lotnisko Chopina (`is_warsaw_airport_line()`). Dla
  tabeli SKM km bierze się z `leg.extra["distance_along_track_km"]` (km po torach, PR #105), gdy
  jest dostępne, inaczej z `leg.distance_km` (linia prosta). Status kwot: „wg Gemini,
  niezweryfikowane niezależnie” — wszystkie trzy ścieżki (SKM Trójmiasto, ŁKA, bilet ZTM w SKM
  Warszawa/KM lotniskowej) dają `price_type="szacunek"` i `breakdown["price_verified"]=False`
  (CONTRIBUTING.md) do czasu drugiego niezależnego źródła. Szczegóły:
  `fares/README.md`, testy `tests/test_local_rail_tariffs.py`.
- wszystko inne (w tym Koleje Mazowieckie, Koleje Małopolskie, SKM Trójmiasto/ŁKA/SKM Warszawa
  poza swoimi obszarami i autobus zastępczy
  RB66 Szczecin–Angermünde, który nie jest wyceniany jak pociąg VBB) → zgrubny fallback `GENERIC_FALLBACK_PLN_PER_KM` (0.35 PLN/km),
  `price_type="szacunek"`, `breakdown["price_verified"]=False`, żeby jeden nierozpoznany
  przewoźnik nie wywalał całego wariantu, ale też nie udawał ceny z cennika.

Autobusy/tramwaje (`price_bus_leg()`): taryfa miejska tylko, gdy oba końce leżą w obszarze miasta
z `CITY_TARIFF_AREAS` (bez współrzędnych: nazwy dopasowywane jako CAŁE słowa, więc „Krakowskie
Przedmieście" w Warszawie nie dostaje taryfy MPK Kraków — błąd S4), eezy.nrw tylko w NRW, a poza
tym jawna wartość zastępcza `LOCAL_BUS_FLAT_PLN` (4,00 PLN, bez źródła) z `price_verified=False` i
`breakdown["wartosc_zastepcza"]=True`. UI i `demo.py` pokazują ją jako „cena niepotwierdzona
(wartość zastępcza, nie z cennika)”, a ranking „Najtańsza” nie stawia takiego wariantu przed
wariantem z potwierdzoną ceną (niżej).

Ryczałt tylko dla krótkich odcinków (`LOCAL_BUS_MAX_KM`): płaskie 4,00 PLN ma sens wyłącznie dla
jazdy w obrębie jednego biletu miejskiego. Próg (20 km, linia prosta, włącznie) to największy
promień koła taryfy miejskiej w `CITY_TARIFF_AREAS` (Berlin 20 km, reszta miast 11-15 km), więc
nie jest nową stawką ani liczbą spoza repo i rośnie razem z tą tabelą. Odcinek BUS/tramwaj od
nieznanego operatora **dłuższy** niż próg idzie `price_long_unknown_local_leg()`: niepotwierdzony
szacunek `GENERIC_FALLBACK_PLN_PER_KM` x km (`price_type="szacunek"`, `price_verified=False`,
`breakdown["powod_szacunku"]="odcinek za długi na ryczałt lokalny"`, bez `wartosc_zastepcza`,
nigdy `oficjalna_taryfa`; etykieta „cena niepotwierdzona”). Brak `distance_km` zostawia ryczałt.
Powód: feed Ksaviego oznacza część kolei regionalnej jako `BUS` (np. RB66 Szczecin -> Angermünde,
58,2 km, przewoźnik „Nahreisezug”, `motis_mode=BUS`), więc gałąź SUBURBAN jej nie łapie; nie
wiemy, czy to pociąg, czy komunikacja zastępcza, i nie zgadujemy. `route_short_name` w stylu
RB/RE/IRE/S/SKM (`is_train_like_line()`) jest tylko sygnałem pomocniczym do opisu
(`breakdown["sygnal_linii"]`, dopisek w `notes`) i nie zmienia ani trybu, ani ceny. Taryfy miejskie,
NRW (eezy.nrw), BVG i FlixBus wołają się PRZED tym progiem i działają bez zmian. Testy:
`tests/test_long_local_leg_pricing.py`.

Kolej podmiejska — tryb MOTIS `SUBURBAN` (SKM, S-Bahn): `motis_client.itinerary_to_legs` mapuje go
na `LegMode.BUS` (jak każdy tryb spoza RAIL/TRAIN), ale to POCIĄG, więc `price_bus_leg()` wycenia go
tak (`is_suburban_leg()`, `leg.extra["motis_mode"] == "SUBURBAN"`):
1. taryfa miejska, gdy oba końce leżą w kole z `CITY_TARIFF_AREAS` — np. S-Bahn Berlin w kole BVG
   dostaje bilet BVG AB/ABC z `fares/data/bvg_berlin.json` (bez zmian),
2. eezy.nrw, gdy oba końce leżą w NRW (bez zmian),
3. w przeciwnym razie `price_suburban_leg()`: **nie** ryczałt autobusowy, tylko jawnie
   niepotwierdzony szacunek `GENERIC_FALLBACK_PLN_PER_KM` x km (`price_type="szacunek"`,
   `breakdown["price_verified"]=False`, `breakdown["tryb_motis"]="SUBURBAN"`, w `notes` powód i
   „cena niepotwierdzona”; brak `wartosc_zastepcza`). Dotyczy m.in. SKM Szczecin (np. Szczecin →
   Angermünde, ok. 70 km), SKM Trójmiasto poza `SKM_TROJMIASTO_AREA` (np. Wejherowo) i S-Bahnów
   poza znanymi taryfami. SKM w Trójmieście i Warszawie oraz ŁKA w Łodzi mają osobne taryfy
   (wyżej, `price_bus_leg()` woła je PRZED taryfami miejskimi).
Cen SKM i pozostałych kolei podmiejskich spoza powyższych taryf NIE ma w `fares/data/*` — kwota
PLN/km jest orientacyjna, a odcinek nie wygrywa rankingu „Najtańsza” z wariantem o potwierdzonej
cenie (`Itinerary.price_verified`, `scoring.pick_recommendations`). Znane ograniczenia: SUBURBAN
nadal ma `LegMode.BUS` (w UI „autobus”), a S-Bahn Berlin poza kołem 20 km (np. Potsdam) nie ma
mapy stref VBB, więc też jest niepotwierdzony. Testy: `tests/test_suburban_pricing.py`.

Berlin (BVG/VBB): koło `CITY_TARIFF_AREAS[BVG_BERLIN]` (20 km) obejmuje też lotnisko BER, które
leży w strefie C. Odcinek, który zaczyna się lub kończy na BER (`BER_AIRPORT_AREA`, 2,5 km wokół
stacji Flughafen BER; bez współrzędnych — nazwa „Flughafen BER”), dostaje bilet ABC (5,00 EUR), a
nie AB (4,00 EUR, na BER nieważny). Obie kwoty pochodzą z `fares/data/bvg_berlin.json` (VBB, ceny
od 1.01.2026). Ograniczenie: inne przystanki strefy C w tym kole (np. Schönefeld, Teltow,
Hennigsdorf) nadal dostają AB — bez mapy stref VBB nie rozstrzygamy tego geograficznie.

`fares/` wymaga teraz `distance_km` dla WSZYSTKICH przewoźników (w tym VRR, taryfa eezy.nrw:
Grundpreis + cena/km w linii prostej) — liczymy je z `lat`/`lon`, które MOTIS podaje dla
każdego przystanku (`motis_client.haversine_km`).

## Wycena autokarów dalekobieżnych: FlixBus ma własny moduł (2026-09-26)

`pricing.price_bus_leg()` rozpoznaje FlixBusa (`"flix"` w nazwie przewoźnika z MOTIS) i kieruje
go do `fares.Carrier.FLIXBUS` (`fares/flixbus.py`) zamiast prosto do `GENERIC_FALLBACK_PLN_PER_KM`
jak inne, nierozpoznane autokary (RegioJet, BlaBlaBus, ...). `fares/flixbus.py` próbuje pobrać
realną cenę z (nieoficjalnego) API FlixBusa dla konkretnej daty (`leg.depart`), z fallbackiem do
tego samego zgrubnego PLN/km gdy API jest niedostępne — patrz `fares/README.md`.

**Cena z fallbacku jest niepotwierdzona.** Źródło ceny jest w `breakdown["zrodlo"]`
(`api_flixbus_live` albo `fallback_km`). Fallback km (0,27 PLN/km) dostaje dodatkowo
`breakdown["price_verified"] = False` — ten sam mechanizm i ten sam dopisek „cena niepotwierdzona”
w UI i `demo.py` co przy innych szacunkach — więc wariant z takim odcinkiem nie wygrywa rankingu
„Najtańsza” z wariantem o potwierdzonej cenie (logika `scoring.pick_recommendations` bez zmian).
Cena z live API zostaje bez flagi. `price_flixbus_leg` przenosi teraz `breakdown` do `PricedLeg`
(wcześniej go gubił, więc źródła ceny nie było widać poza `fares/`). Testy:
`tests/test_unverified_prices.py` (sekcja FlixBus).

## Scoring: "najlepszy stosunek cena/czas"

`Itinerary.price_per_hour = total_price_pln / (total_duration_min / 60)` — jedna prosta,
znormalizowana miara (PLN na godzinę podróży), niżej = lepiej. Wybrana zamiast wagowej sumy
cena+czas, bo nie wymaga ręcznego ustawiania wag (jak ważyć 1 godzinę względem 1 złotówki?) —
PLN/h ma naturalną interpretację ("ile płacę za każdą godzinę w drodze") i jest łatwa do
wyjaśnienia użytkownikowi. Wadą jest to, że bardzo krótkie, drogie warianty (loty) mogą wypadać
źle mimo krótkiego czasu całkowitego — to świadomy trade-off tej metody.

Rekomendacje (`scoring.pick_recommendations`) to zwykłe `min()` po: cenie, czasie,
liczbie przesiadek i `price_per_hour`. Ten sam wariant może wygrać w kilku kategoriach naraz —
to nie błąd, po prostu jest obiektywnie dobry na wielu osiach.

## Scoring: "najlepszy kompromis"

Osobna kategoria od "najlepszy stosunek cena/czas" — celowo bez żadnej stałej do kalibrowania
(jak `VALUE_OF_TIME_PLN_PER_HOUR`). `scoring._compromise_key()` liczy dla każdego wariantu
średnią z dwóch znormalizowanych pozycji WZGLĘDEM znalezionych wariantów tej samej trasy:
`(cena - najtańsza) / (najdroższa - najtańsza)` i analogicznie dla czasu, każda w skali 0
(najlepszy w tej puli) do 1 (najgorszy). Wygrywa wariant z najniższą średnią, czyli ten
najbliżej czołówki jednocześnie w cenie i w czasie — bez ekstremum w żadną stronę, jak
"najtańsza"/"najszybsza". Łatwe do wytłumaczenia: "blisko najlepszego zarówno ceną, jak i
czasem, względem tego, co w ogóle znaleźliśmy na tę trasę". Wadą jest to, że wynik zależy od
puli (dodanie/usunięcie skrajnego wariantu przesuwa skalę i może zmienić zwycięzcę) — to
świadomy trade-off, spójny z resztą metod w tym module.

Wersja bezpieczna (`najlepszy_kompromis_bezpieczny`) liczy to samo, ale tylko na wariantach
bez ryzykownych przesiadek (`safe_pool`, z tym samym fallbackiem co pozostałe kategorie
"_bezpieczna"/"_bezpieczny" — patrz `Itinerary.is_safe_fallback`).

## Scoring: "najszybsza (z Twoimi ulgami)"

Inna filozofia niż "najlepszy kompromis": tu czas zawsze wygrywa, cena rozstrzyga tylko
remisy/prawie-remisy. `scoring._fastest_within_tolerance()` bierze wszystkie warianty, których
czas mieści się w tolerancji od najszybszego (`FASTEST_TOLERANCE_FRACTION = 10%` czasu
najszybszego wariantu, ale nie mniej niż `FASTEST_TOLERANCE_MIN_MINUTES = 10` minut — większa
z tych dwóch wartości), i spośród nich wybiera najtańszy, czyli z uwzględnieniem konkretnych
ulg usera (BahnCard, ulgi PKP itd. już policzone w `total_price_pln`). Dla trasy Lublin →
Gelsenkirchen (~16h) to ~96 min tolerancji; dla krótkiej trasy regionalnej (~1h) to 10 min
(dolny próg). Wersja bezpieczna (`najszybsza_z_ulgami_bezpieczna`) liczy to samo na
`safe_pool`, z tym samym fallbackiem co inne kategorie "_bezpieczna".

## Scoring: "najmniej przesiadek"

Wygrywa wariant z najmniejszą liczbą przesiadek (`Itinerary.num_transfers`, odcinki WALK nie
liczą się). Remis rozstrzyga krótszy czas, potem niższa cena. Wybór jest spośród wariantów
zwróconych przez MOTIS (i naszych wariantów hubowych) — nie szukamy tras, których silnik nie
dał. Wersja bezpieczna (`najmniej_przesiadek_bezpieczna`) działa na `safe_pool` z tym samym
fallbackiem co inne kategorie "_bezpieczna". Kategoria jest pod „Pokaż więcej”, nie w
`TOP_CATEGORY_KEYS`. Nie zmienia żadnych cen.

## Waluty

Ceny z `fares/` bywają w PLN (PKP) i EUR (DB, VRR/eezy.nrw), a `flights/` w walucie
skonfigurowanej w `RouteRequest.flight_currency` (domyślnie PLN). Do porównywania wariantów
(`total_price_pln`, `price_per_hour`) wszystko jest przeliczane do PLN sztywnym,
PLACEHOLDEROWYM kursem w `currency.py` (nie z API kursowego) — każdy `PricedLeg` i tak
zachowuje swoją oryginalną kwotę/walutę w `breakdown`/`amount`/`currency`, więc nic nie jest
"zgubione", przeliczenie służy tylko do rankingu.

Implementacja jest w `common/currency.py` (`routing/currency.py` tylko ją re-eksportuje).
Obsługiwane są tylko waluty z kursem (dziś PLN i EUR); kursu nie zgadujemy. Inna waluta
(np. `flight_currency=GBP`) to `UnsupportedCurrencyError` (podklasa `ValueError`) z listą
obsługiwanych walut: `POST /route` odpowiada wtedy 422 z tym komunikatem (walidacja pola
`flight_currency`), a `RouteRequest` odrzuca ją przy tworzeniu.

Kwoty zapisane w złotych w `flights/` i `routing/pricing.py` (zgrubny szacunek biletu 350 PLN,
bagaż z tabeli relacji i szacunek domyślny 150 PLN) są przy `flight_currency=EUR` przeliczane
tym samym kursem, a nie tylko podpisywane nową walutą; notatka w wyniku podaje kwotę źródłową
w PLN. Bilet z cache Travelpayouts jest pobierany od razu w walucie segmentu.

## Odporność na błędy

`variants.generate_variants()` nigdy nie wywala całego demo z powodu jednego wariantu:
- brak `TRAVELPAYOUTS_TOKEN` (moduł `flights/`) → ten wariant trafia do `SkippedVariant`,
  reszta (warianty czysto kolejowe) i tak się liczy.
- MOTIS nie znajduje połączenia dla danej relacji/daty (np. data poza oknem wczytanego
  rozkładu — patrz błąd `outside of loaded timetable window`) → też `SkippedVariant`.

`demo.py` wypisuje pominięte warianty z powodem, żeby było jasne, czego brakuje (tokena,
działającego MOTIS, itp.), zamiast się wywalić.

## Najbliższe połączenia w innym dniu (pusty wynik)

MOTIS szuka od podanego czasu bez górnej granicy, a `build_rail_only_variants` odrzuca połączenia,
które ruszają w innym dniu niż zapytany. Gdy MOTIS zwrócił połączenia, ale **wszystkie** w innym
dniu (np. Kraków → Gorlice w sobotę 17.10, pociągi dopiero w poniedziałek 19.10), powód „N
połączeń rusza w innym dniu” trafia do `skipped`, a obok niego powstaje osobna sekcja
**„Najbliższe połączenia w innym dniu”** (`OtherDayVariant` w `model.py`):

- **Kiedy:** tylko gdy główny wynik jest pusty (`built == []`) i zapytanie kolejowe
  origin → destination nie miało żadnego połączenia w dniu zapytania. Jest połączenie w dniu
  zapytania, wynik niepusty z innych źródeł (loty, inny dworzec) albo MOTIS nic nie zwrócił =
  sekcji nie ma.
- **Limit:** maks. `OTHER_DAY_MAX_VARIANTS = 3` wariantów (najbliższe wg odjazdu) i tylko z dni
  odległych od zapytanej daty o najwyżej `OTHER_DAY_MAX_DAYS = 3`. Dalsze połączenia nie tworzą sekcji.
- **Etykieta:** każdy wariant ma `date`, `days_offset` (w dniach) i `label` w rodzaju „INNY DZIEŃ:
  2026-10-19 (za 2 dni, zapytano o 2026-10-17) — to NIE jest dzień zapytania”.
- **Poza rankingami:** te warianty nie trafiają do `built`, więc nie wchodzą do „Najtańsza”/
  „Najszybsza” ani żadnej innej rekomendacji (`recommendations` zostaje `{}`).
- **Cena:** liczona tą samą drogą co zwykle (`_price_legs` + `build_itinerary`); wariant
  niewykonalny (przesiadka poniżej minimum) jest pomijany jak w głównym wyniku.

Gdzie widać: `SearchResult.other_day` (`search_service.py`), UI `app.py` (sekcja pod komunikatem
o braku wariantu), `demo.py` (sekcja pod listą pominiętych), API `POST /route` →
`other_day_variants` (lista `{itinerary, date, requested_date, days_offset, label}`, pusta, gdy
sekcji nie ma). Testy: `tests/test_other_day.py` (fixtury: puste na dzień D, połączenia D+2).

## Adres → adres (Sesja 4c)

`variants.request_from_addresses("Krakowskie Przedmieście 50, Lublin", "Bahnhofstraße, Gelsenkirchen", "2026-10-05")`
geokoduje oba adresy przez MOTIS (`/api/v1/geocode`, OSM z Sesji 4b) i podaje do `/plan`
współrzędne, więc MOTIS sam dokłada dojście piesze. Wynik to pełny łańcuch:
pieszo z adresu → autobus/tramwaj miejski → pociągi → pieszo do adresu.

- `LegMode.WALK`: tylko pierwszy i ostatni odcinek pieszy (dojście z/do adresu) są legami;
  piesze przejścia między odcinkami transitu nadal tylko ustawiają `requires_walk`.
  Odcinki WALK nie liczą się jako przesiadki i nie są sprawdzane w `transfers.py`. Cena 0.
- `LegMode.BUS`: autobusy/tramwaje z MOTIS. `pricing.price_bus_leg()` rozpoznaje operatora
  po `agencyName`/nazwach przystanków:
  - autokar dalekobieżny (RegioJet, BlaBlaBus, ...) → wycena za km, `GENERIC_FALLBACK_PLN_PER_KM`
    (Flixbus ma własny moduł, patrz wyżej);
  - oba końce w obszarze miasta z `CITY_TARIFF_AREAS` → taryfa miejska tego miasta (np.
    `fares/ztm_lublin.py`, taryfa czasowa ZTM Lublin, strefa 1+2);
  - oba końce w NRW → `fares/vrr.py` (eezy.nrw, ta sama taryfa obejmuje bus/tramwaj/U-Bahn co
    pociągi regionalne VRR);
  - reszta, do `LOCAL_BUS_MAX_KM` (20 km) → wartość zastępcza `LOCAL_BUS_FLAT_PLN` z
    `price_verified=False` (patrz wyżej);
  - reszta, powyżej `LOCAL_BUS_MAX_KM` → niepotwierdzony szacunek PLN/km (`price_long_unknown_local_leg`).

`python demo.py --from "..." --to "..." --date YYYY-MM-DD`

## Przesiadki niewykonalne vs ryzykowne

Dwa progi w `transfers.py`: **bezpieczny** (20/30 min kolej, 90/120 min z lotem) i **absolutne
minimum wykonalności** (3 min ten sam peron, 8 min ze zmianą dworca/peronu, 60 min kolej→lot,
45 min lot→kolej). Poniżej minimum wykonalności wariant jest **odrzucany** (nie trafia do
rekomendacji; w `generate_variants` ląduje w `SkippedVariant` z powodem). Między minimum a progiem
bezpiecznym wariant zostaje z oznaczeniem RYZYKOWNY. Progi to szacunek.

## Zmiany scoringu i pobierania (Sesja 4e)

- **30 połączeń z MOTIS** (`MAIN_QUERY_ITINERARIES`, ~6 s) zamiast domyślnych ~5, i wszystkie
  wykonalne stają się wariantami (`build_rail_only_variants`, cap 30).
- **`additionalTransferTime=10`**: MOTIS sam szuka przesiadek z 10-min zapasem. Bez tego jedyne
  „proste” trasy przez Berlin miały przesiadki 2–3 min i były (słusznie) odrzucane jako
  niewykonalne, więc nie było czego rekomendować.
- **„Najlepszy stosunek cena/czas” = uogólniony koszt** (`Itinerary.value_score`, niżej = lepiej):
  `cena + VALUE_OF_TIME_PLN_PER_HOUR x godziny` + kary za każdą ryzykowną przesiadkę i za każdego
  dodatkowego przewoźnika (osobny bilet). Stałe w `scoring_config.py` (szacunek, do strojenia).
  Zastępuje PLN/h, które premiowało długie podróże. „Najtańsza”/„najszybsza”/„najmniej
  przesiadek” pozostają czyste (bez kar).
- **„Najtańsza” i „Najtańsza bezpieczna” najpierw wśród cen potwierdzonych**: wariant z choć
  jednym odcinkiem `price_verified=False` (`Itinerary.price_verified`) nie wygrywa z wariantem o
  potwierdzonej cenie, nawet gdy jego suma jest nominalnie niższa. Gdy żaden wariant nie ma
  potwierdzonej ceny, wygrywa najtańszy nominalnie, a UI i `demo.py` piszą o tym wprost
  (`scoring.price_ranking_note`). Pominięte, nominalnie tańsze warianty pokazuje
  `scoring.cheaper_unverified`. Pozostałe kategorie się nie zmieniły.
