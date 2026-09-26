# `routing/` — silnik optymalizacji trasy (Sesja 4)

Dla podanej pary miast (jako `stopId` z MOTIS) i daty generuje kilka **wariantów** podróży
łączących routing kolejowy z MOTIS (Sesja 2) z modułami taryf `fares/` i `flights/` (Sesja 3,
3b), liczy dla każdego cenę/czas/przesiadki, sprawdza bezpieczeństwo przesiadek i wybiera
4 rekomendacje.

## Świadome ograniczenie zakresu

**Nie przeszukujemy alternatywnych węzłów przesiadkowych** (np. lot przez Berlin vs Wrocław
vs Düsseldorf zamiast Dortmundu) — to odłożone do Sesji 6, bo wymagałoby wielu kosztownych
zapytań routingowych i mogłoby zablokować pierwsze działające demo. Huby (lotnisko wylotu +
lotnisko przylotu + stacje dojazdowe po obu stronach) są ustalone RAZ, w konfiguracji
(`HubConfig`, patrz `demo_route.py` dla przykładu Lublin→Gelsenkirchen). Silnik generuje jeden
sensowny wariant na hub, nie kilka konkurujących.

Warianty "tylko kolej" **są** różnicowane — ale tylko między itinerariami, które MOTIS i tak
zwraca dla JEDNEJO zapytania origin→destination (różne trasy/liczby przesiadek, które silnik
uznał za sensowne dla tej samej relacji), nie z przeszukiwania innych hubów.

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
- `LegMode.BUS`: autobusy/tramwaje z MOTIS (np. ZTM Lublin), ryczałt `LOCAL_BUS_FLAT_PLN`
  (placeholder, brak modułu taryf komunikacji miejskiej).

`python demo.py --from "..." --to "..." --date YYYY-MM-DD`

## Przesiadki niewykonalne vs ryzykowne

Dwa progi w `transfers.py`: **bezpieczny** (20/30 min kolej, 90/120 min z lotem) i **absolutne
minimum wykonalności** (3 min ten sam peron, 8 min ze zmianą dworca/peronu, 60 min kolej→lot,
45 min lot→kolej). Poniżej minimum wykonalności wariant jest **odrzucany** (nie trafia do
rekomendacji; w `generate_variants` ląduje w `SkippedVariant` z powodem). Między minimum a progiem
bezpiecznym wariant zostaje z oznaczeniem RYZYKOWNY. Progi to szacunek.
