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
| Międzynarodowy PL↔DE — 3 kategorie cenowe (krótka/średnia/długa) | **oficjalne ceny "od", progi km SZACUNEK** | [Super Sparpreis Europa Polska](https://www.bahn.de/angebot/sparpreis-flexpreis/super-sparpreis-europa-polen), [zasada BahnCard tylko na niemiecki odcinek](https://int.bahn.de/en/offers/saver-fare-flexible-fare/super-saver-fare-europe-poland) — sprawdzone 2026-09-29 |
| Międzynarodowy PL↔DE — taryfa Young (15-26 lat) | **oficjalna cena "od" (MINIMUM, nie realna cena — bahn.de explicite nie podaje górnej granicy, "je nach Verfügbarkeit"), flat (bez progów km — tak reklamuje to bahn.de)** | [Super Sparpreis Europa Young Polen](https://www.bahn.de/angebot/sparpreis-flexpreis/super-sparpreis-europa-young-polen), [FAQ cena](https://www.bahn.de/bahnbusiness/faq/preis-super-sparpreis-europa-polen), [FAQ Young](https://www.bahn.de/faq/pk/angebot/sparpreis/young/super-sparpreis-young) — sprawdzone 2026-10-07 (2x, niezależnie) |

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

Warianty i ceny (`fares/data/bahncard.json`, sprawdzone 2026-09-27 na bahn.de/angebot/bahncard):

| Wariant | Cena roczna | Rabat na Flexpreis | Wiek |
|---|---|---|---|
| BahnCard 25 (standard) | 62,90 EUR | 25% | dowolny |
| BahnCard 50 (standard) | 244,00 EUR | 50% | dowolny |
| My BahnCard 25 | 39,90 EUR | 25% | 19–26 lat |
| My BahnCard 50 | 79,90 EUR | 50% | 19–26 lat |
| Jugend BahnCard 25 | 7,90 EUR (**0 EUR promocyjnie do 2026-09-30**) | 25% | 6–18 lat |

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
