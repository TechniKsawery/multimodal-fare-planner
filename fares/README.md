# Moduł taryf (`fares/`)

Szacuje cenę pojedynczego segmentu podróży dla pięciu przewoźników:

- **PKP Intercity** (`fares/pkp.py`) — cena z tabeli pasm odległości × mnożnik ulgi.
- **DB** (`fares/db.py`) — Flexpreis jako górna granica z tabeli pasm odległości × mnożnik BahnCard
  (BahnCard 25 → ×0.75, BahnCard 50 → ×0.5).
- **VRR** (`fares/vrr.py`) — taryfa eezy.nrw: cena = Grundpreis + cena za km (linii prostej),
  z sufitem cenowym. Obejmuje pociągi regionalne VRR ORAZ lokalny bus/tramwaj/U-Bahn w obszarze
  VRR (Zagłębie Rury/NRW) — to jedna, wspólna taryfa strefowa dla całego transportu VRR.
  Zniżka: oficjalny Kindertarif (`DiscountProfile.vrr_dziecko=True`) — 50% rabatu dla dzieci
  6-14 lat, wliczając sufity cenowe (dzieci poniżej 6 lat jeżdżą bez biletu — nie modelowane).
- **ZTM Lublin** (`fares/ztm_lublin.py`) — taryfa czasowa (bilety 15/40/90-minutowe, strefa 1+2):
  dobiera najkrótszy bilet, którego czas ważności pokrywa czas jazdy odcinka z MOTIS.
- **FlixBus** (`fares/flixbus.py` + `fares/_flixbus_api.py`) — REALNA cena z publicznego
  (nieoficjalnego) API FlixBusa dla konkretnej daty przejazdu, z fallbackiem do zgrubnego
  szacunku PLN/km gdy API jest niedostępne/bez wyniku — patrz sekcja niżej.

## Stan danych po researchu (2026-09-26)

| Przewoźnik | Status | Źródło |
|---|---|---|
| PKP Intercity — pasma cenowe (TLK/IC, 2. klasa) | **oficjalne** | [Cennik PKP Intercity](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Cennik_uslug_przewozowych_PKP_Intercity_tekst_ujednolicony_obowiazuje_od_23.07.2026_r.pdf), tekst ujednolicony od 23.07.2026 |
| PKP Intercity — ulgi ustawowe | **oficjalne** | [Tabele ulg ustawowych](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Ulgi%20ustawowe/Tabele_ulg_ustawowych_11-02-2026.pdf), stan na 11.02.2026 |
| VRR — eezy.nrw (Grundpreis + cena/km) | **oficjalne** | [Preistabelle VRR](https://www.vrr.de/fileadmin/user_upload/pdf/service/downloads/Weitere_Broschueren_und_Tarifinformationen/VRR_Preise_2026.pdf), Stand 01.06.2026 |
| VRR — Kindertarif (50% rabatu, dzieci 6-14 lat) | **oficjalne** | tamże, sekcja "Kinder 50% Rabatt pro Person und Fahrt inkl. Deckel" |
| DB — mnożniki BahnCard 25/50 | **oficjalne** | [bahn.de/faq/pk/angebot/flexpreis](https://www.bahn.de/faq/pk/angebot/flexpreis) |
| DB — tabela pasm odległości Flexpreis | **szacunek, skalibrowany do 1 realnej próbki** | DB nie publikuje takiej tabeli (cena dynamiczna); próba żywego wyszukiwania na bahn.de zablokowana jako ruch bota (błąd 751) — użyto zamiast tego realnej ceny Halle→München (373 km, 106–127 EUR) z bahndampf.de + oficjalnie cytowanej górnej granicy (150 EUR 2. klasa) do skalibrowania prostej formuły baza+km |
| ZTM Lublin — bilety czasowe (15/40/90 min, strefa 1+2) | **oficjalne** | [Cennik LUBIKA](https://lubika.zdtm.lublin.eu/cennik/) (system biletu elektronicznego ZDiTM Lublin), ważny od 16.02.2026 |

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
pole `"zrodlo"`: `"api_flixbus_live"` albo `"fallback_km"`.

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
