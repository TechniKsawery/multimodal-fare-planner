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
- `alternative_origin_stops` / `alternative_destination_stops` — powtarza główne zapytanie
  "tylko kolej" z podmienionym dworcem startu/mety.

Wszystkie warianty kolejowe (główne zapytanie + alternatywy) są odchudzane WSPÓLNYM dedup po
sygnaturze trasy (sekwencja nazw origin/destination odcinków) — ta sama fizyczna trasa
znaleziona kilkoma drogami trafia do wyniku tylko raz, a błąd MOTIS dla jednej alternatywy
(`MotisError`, np. brak połączenia przez dany węzeł) ląduje w `SkippedVariant`, nie przerywa
reszty. Konkretne `stopId` dla `AlternativeStop` trzeba dobrać ręcznie (np. przez
`/api/v1/geocode` albo znajomość sieci) — silnik nie zgaduje sam, które miasta/dworce warto
sprawdzić.

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
przyjazd kolei wokół niego (150 min przed odlotem na dojazd+odprawę, 90 min po przylocie).
To wystarcza do liczenia bufora przesiadki, ale nie jest realnym rozkładem lotów.

## Wycena odcinków kolejowych: mapowanie przewoźnika

`pricing.infer_rail_carrier()` mapuje `agencyName` z MOTIS na przewoźnika z `fares/`:
- `"PKP Intercity"` → `Carrier.PKP_INTERCITY`
- nazwa zawierająca `"DB Fernverkehr"`/`"Deutsche Bahn"` → `Carrier.DB`
- każdy inny niemiecki przewoźnik regionalny (S-Bahn, Abellio, National Express, ...) →
  `Carrier.VRR` **jako uproszczenie** — w rzeczywistości różne związki taryfowe (VRR, VRS, ...)
  obowiązują w różnych regionach Niemiec, nie mamy mapowania geograficznego stacja→związek.
- nieznany przewoźnik (np. polskie koleje regionalne) → zgrubny fallback
  `GENERIC_FALLBACK_PLN_PER_KM` (0.35 PLN/km) zamiast błędu, żeby jeden nierozpoznany
  przewoźnik nie wywalał całego wariantu.

`fares/` wymaga teraz `distance_km` dla WSZYSTKICH przewoźników (w tym VRR, taryfa eezy.nrw:
Grundpreis + cena/km w linii prostej) — liczymy je z `lat`/`lon`, które MOTIS podaje dla
każdego przystanku (`motis_client.haversine_km`).

## Scoring: "najlepszy stosunek cena/czas"

`Itinerary.price_per_hour = total_price_pln / (total_duration_min / 60)` — jedna prosta,
znormalizowana miara (PLN na godzinę podróży), niżej = lepiej. Wybrana zamiast wagowej sumy
cena+czas, bo nie wymaga ręcznego ustawiania wag (jak ważyć 1 godzinę względem 1 złotówki?) —
PLN/h ma naturalną interpretację ("ile płacę za każdą godzinę w drodze") i jest łatwa do
wyjaśnienia użytkownikowi. Wadą jest to, że bardzo krótkie, drogie warianty (loty) mogą wypadać
źle mimo krótkiego czasu całkowitego — to świadomy trade-off tej metody.

Cztery rekomendacje (`scoring.pick_recommendations`) to zwykłe `min()` po: cenie, czasie,
liczbie przesiadek i `price_per_hour`. Ten sam wariant może wygrać w kilku kategoriach naraz —
to nie błąd, po prostu jest obiektywnie dobry na wielu osiach.

## Waluty

Ceny z `fares/` bywają w PLN (PKP) i EUR (DB, VRR/eezy.nrw), a `flights/` w walucie
skonfigurowanej w `RouteRequest.flight_currency` (domyślnie PLN). Do porównywania wariantów
(`total_price_pln`, `price_per_hour`) wszystko jest przeliczane do PLN sztywnym,
PLACEHOLDEROWYM kursem w `currency.py` (nie z API kursowego) — każdy `PricedLeg` i tak
zachowuje swoją oryginalną kwotę/walutę w `breakdown`/`amount`/`currency`, więc nic nie jest
"zgubione", przeliczenie służy tylko do rankingu.

## Odporność na błędy

`variants.generate_variants()` nigdy nie wywala całego demo z powodu jednego wariantu:
- brak `TRAVELPAYOUTS_TOKEN` (moduł `flights/`) → ten wariant trafia do `SkippedVariant`,
  reszta (warianty czysto kolejowe) i tak się liczy.
- MOTIS nie znajduje połączenia dla danej relacji/daty (np. data poza oknem wczytanego
  rozkładu — patrz błąd `outside of loaded timetable window`) → też `SkippedVariant`.

`demo.py` wypisuje pominięte warianty z powodem, żeby było jasne, czego brakuje (tokena,
działającego MOTIS, itp.), zamiast się wywalić.

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
  - autokar dalekobieżny (Flixbus, RegioJet, ...) → wycena za km, `GENERIC_FALLBACK_PLN_PER_KM`;
  - `"Lublin"`/`"ZDiTM"`/`"ZTM"` → `fares/ztm_lublin.py` (taryfa czasowa ZTM Lublin, oficjalna,
    strefa 1+2 — dobiera bilet 15/40/90-minutowy wg czasu jazdy odcinka z MOTIS);
  - reszta (cały niemiecki fragment sieci to NRW) → `fares/vrr.py` (eezy.nrw, ta sama taryfa
    obejmuje bus/tramwaj/U-Bahn co pociągi regionalne VRR);
  - brak rozpoznanego operatora i brak `distance_km` → ryczałt `LOCAL_BUS_FLAT_PLN`
    (placeholder, tylko dla nieobsłużonych miast/operatorów).

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
