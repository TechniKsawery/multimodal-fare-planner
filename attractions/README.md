# Moduł atrakcji i kart miejskich (`attractions/`)

Moduł odpowiada za:
1. Katalogowanie rekomendowanych miejsc i atrakcji w miastach docelowych/przesiadkowych (m.in. Gelsenkirchen & Ruhrgebiet, Berlin, Kraków, Lublin).
2. Kategoryzację atrakcji:
   - **Sport** (stadiony, kluby piłkarskie, muzea sportowe — np. Veltins-Arena Schalke 04, Olympiastadion Berlin, Signal Iduna Park Dortmund)
   - **Turystyka & zabytki** (UNESCO, zamki, muzea, ikony architektury — np. Museumsinsel, Zeche Zollverein, Wawel)
   - **Rozrywka** (punkty widokowe, ogrody zoologiczne nowej generacji — np. Berliner Fernsehturm, ZOOM Erlebniswelt)
   - **Gastronomia** (kultowe smaki i targowiska — np. berliński currywurst, lubelskie cebularze, krakowskie zapiekanki)
   - **Natura** (parki poprzemysłowe, ogrody)
3. Sugestie i kalkulator opłacalności kart miejskich (**City Cards**):
   - **Berlin WelcomeCard** (strefy AB, ABC, wariant 72h + Museumsinsel)
   - **RUHR.TOPCARD** (roczna karta regionu Ruhry — Gelsenkirchen, Essen, Bochum, Dortmund; BEZ transportu publicznego w cenie, zastąpiła tu dawną WelcomeCard Ruhr, która okazała się martwym produktem)
   - **Kraków Card** (Krakowska Karta Turystyczna)
   - Wyliczanie oszczędności netto: czy koszt karty zwraca się przy wybranych atrakcjach i darmowym transporcie miejskim.
   - Karta pojawia się w kalkulatorze i rekomendacji TYLKO gdy jej istnienie i działanie DZIŚ jest potwierdzone u źródła (`existence_verified` + URL + data w `city_cards.json`) — niepotwierdzona może być co najwyżej jej cena, nigdy sam fakt, że produkt nadal istnieje. `get_all_city_cards()` pokazuje też karty niepotwierdzone (do audytu danych); `get_city_cards()` i kalkulator — nie.
   - Zniżka karty na atrakcję jest liczona TYLKO tam, gdzie jest zapisana: `custom_discounts` karty
     (id atrakcji -> %) albo `default_card_discount_percent` atrakcji. Atrakcja bez wpisu dostaje 0%
     — nie ma "domyślnego rabatu karty" (dawne `default_discount_percent` dawało np. 100% na Katedrę
     Wawelską z Kraków Card, bo zgadywało). Nowy wpis dodawaj dopiero z potwierdzeniem u źródła.
   - **Zniżka > 0% wymaga pola źródła** (`source_url` + `verified_date`, model `DiscountSource`):
     dla `custom_discounts` karty — `custom_discount_sources` (id atrakcji -> źródło), dla
     `default_card_discount_percent` atrakcji — `card_discount_source`. Zapisana zniżka bez
     kompletnego źródła jest liczona jako **0%** i trafia do `CityCardEvaluation.unverified_discount_attraction_ids`
     (+ zdanie „niezweryfikowane” w `summary`) — ten sam mechanizm co Katedra Wawelska w Kraków Card.
     Jawne `0.0` w `custom_discounts` to znany brak zniżki (bez flagi). Wyjątek z definicji produktu:
     wariant `bwc_72h_museumsinsel` daje 100% na Museumsinsel (wstęp wliczony w zweryfikowaną cenę wariantu).
   - **Zerowanie 2026-10-12**: zniżki bez pola źródła w Berlinie, Krakowie, Hamburgu, Monachium, Poznaniu
     i Lublinie (16 atrakcji) wyzerowano; stara wartość zostaje w `city_cards.json`
     (`_zerowane_znizki_bez_zrodla_2026_10_12` na karcie) i `attractions.json` (`_UWAGA_zniezka_karty`).
     Żeby zniżkę przywrócić: wpisz wartość w `custom_discounts` i URL + datę w `custom_discount_sources`
     (albo `default_card_discount_percent` + `card_discount_source`) — wpis bez źródła nadal da 0%.
     Zniżki RUHR.TOPCARD zostały (źródło z notatki `_UWAGA_partnerzy` przepisane do pól).
4. Zniżki z dowolnego tytułu (wiek/uczeń-student/senior), niezależnie od posiadania karty miejskiej: `best_price_for_attraction(attraction, DiscountProfile(...))` wybiera najtańszą potwierdzoną cenę spośród ceny standardowej i pól `child_price`/`student_price`/`senior_price`/`family_price` (typu `GroupPrice`: konkretna kwota + źródło + data, nigdy procent). Zniżki się nie sumują — bierzemy minimum.

## Użycie

```python
from attractions import get_attractions, evaluate_city_cards, suggest_best_city_card, AttractionCategory

# Pobranie atrakcji sportowych w Berlinie
sport_places = get_attractions(city="Berlin", category=AttractionCategory.SPORT)

# Kalkulacja karty miejskiej dla zestawu wybranych atrakcji + transportu
best_card = suggest_best_city_card(
    city="Berlin",
    selected_attractions=sport_places,
    estimated_transit_cost=15.0,
)
if best_card:
    print(best_card.summary)
```
