English | Polski: [wersja polska](README.pl.md)

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
   - **Przywrócenie ze źródłem 2026-10-12** (raport `research/zrodla-znizek-kart.md`, gałąź
     `gemini/zrodla-znizek`; źródła **wg Gemini, niezweryfikowane niezależnie** — domeny operatorów
     niedostępne z chmury). Przywrócono tylko zniżki jednoznacznie potwierdzone cytatem i zgodną ceną
     bazową (10): Fernsehturm 25%, Olympiastadion 22,7% (8,50 z 11,00 EUR wg cen źródła, nie
     deklarowane 25%), Speicherstadtmuseum 25%, FC Bayern 8%, Residenz 13,3%, Frauenkirche 33,3%,
     SEA LIFE 20%, Bavaria Filmstadt 10%, Brama Poznania 40%, Fotoplastykon 100%. Zniżki kwotowe w euro
     przeliczono na % tylko przy zgodnej cenie bazowej. URL, data, cytat i uwagi: pole
     `_zrodla_znizek_2026_10_12` na karcie w `city_cards.json`.
     Pozycje, które w tym raporcie zostały jeszcze 0% z flagą, rozstrzygnęła kontrola krzyżowa niżej.
     **Wawel**: jawne `0.0` bez flagi — znany brak zniżki (krakow.travel: „Nie obejmuje zwiedzania Wawelu i Kopalni Soli
     Wieliczka.”).
   - **Kontrola krzyżowa 2026-10-12** (raport `research/zrodla-krzyzowa-kontrola.md`, gałąź
     `gemini/zrodla-krzyz`; **wg Gemini, niezweryfikowane niezależnie**). Potwierdzone bez zmian:
     Fernsehturm, Frauenkirche, Residenz, SEA LIFE, Brama Poznania, Fotoplastykon, Speicherstadtmuseum.
     Rozstrzygnięte pozycje:

     | Atrakcja | Karta | Wynik |
     |---|---|---|
     | Fabryka Schindlera | Krakow City Pass | **jawne 0% bez flagi** — produkt jej nie obejmuje (sprzedawana osobno); zastrzeżenie: wariant `krakow_museum_pass_student_3d` nie był sprawdzany, a 0% działa na wszystkie warianty karty |
     | Museumsinsel | Berlin WelcomeCard Classic | **jawne 0% bez flagi** — Classic bez zniżki; 100% tylko wariant `bwc_72h_museumsinsel` (kod) i „all inclusive” (poza katalogiem) |
     | Zamek Lubelski | Lublin TripPass | **jawne 0% bez flagi** — Pakiet Lubelski bez zniżek muzealnych, Zamek nie honoruje karty |
     | IMM Hamburg | Hamburg CARD | cena normalna poprawiona **17 → 18 EUR**; z kartą 14 EUR = **22,2%** (źródło imm-hamburg.de/preise-infos/, 2026-10-12). Ulgi z tego samego cennika podniesione: Ermäßigt 12 → **13 EUR**, Familie 36 → **38 EUR** (oznaczone `price_verified: false`, „wg Gemini, niezweryfikowane niezależnie”) |
     | Nymphenburg (combo) | München CityTourCard | **0% z flagą niezweryfikowanej zniżki.** CityTourCard daje 2 EUR na combo: **lato 10%** (combo 20 EUR), **zima 12,5%** (combo 16 EUR; sezon zmienia się w połowie października). Model nie ma cen sezonowych (`normal_price` 20 EUR to cena letnia), więc wpisanie zniżki wymaga modelu sezonowego. 1 EUR na bilet pojedynczy do pałacu dotyczy pozycji spoza katalogu |

     Jawne `0.0` w `custom_discounts` to znany brak zniżki (bez flagi). Wyjątek z definicji produktu:
     wariant `bwc_72h_museumsinsel` daje 100% na Museumsinsel (wstęp wliczony w zweryfikowaną cenę wariantu).
   - **Zerowanie 2026-10-12**: zniżki bez pola źródła w Berlinie, Krakowie, Hamburgu, Monachium, Poznaniu
     i Lublinie (16 atrakcji) wyzerowano; stara wartość zostaje w `city_cards.json`
     (`_zerowane_znizki_bez_zrodla_2026_10_12` na karcie) i `attractions.json` (`_UWAGA_zniezka_karty`).
     Żeby zniżkę przywrócić: wpisz wartość w `custom_discounts` i URL + datę w `custom_discount_sources`
     (albo `default_card_discount_percent` + `card_discount_source`) — wpis bez źródła nadal da 0%.
   - **Przywrócenie ze źródłem 2026-10-12** (raport `research/zrodla-znizek-kart.md`, gałąź
     `gemini/zrodla-znizek`; źródła **wg Gemini, niezweryfikowane niezależnie** — domeny operatorów
     niedostępne z chmury). Przywrócono tylko zniżki jednoznacznie potwierdzone cytatem i zgodną ceną
     bazową (10): Fernsehturm 25%, Olympiastadion 22,7% (8,50 z 11,00 EUR wg cen źródła, nie
     deklarowane 25%), Speicherstadtmuseum 25%, FC Bayern 8%, Residenz 13,3%, Frauenkirche 33,3%,
     SEA LIFE 20%, Bavaria Filmstadt 10%, Brama Poznania 40%, Fotoplastykon 100%. Zniżki kwotowe w euro
     przeliczono na % tylko przy zgodnej cenie bazowej. URL, data, cytat i uwagi: pole
     `_zrodla_znizek_2026_10_12` na karcie w `city_cards.json`.
     Pozycje, które w tym raporcie zostały jeszcze 0% z flagą, rozstrzygnęła kontrola krzyżowa niżej.
     **Wawel**: jawne `0.0` bez flagi — znany brak zniżki (krakow.travel: „Nie obejmuje zwiedzania Wawelu i Kopalni Soli
     Wieliczka.”).
   - **Kontrola krzyżowa 2026-10-12** (raport `research/zrodla-krzyzowa-kontrola.md`, gałąź
     `gemini/zrodla-krzyz`; **wg Gemini, niezweryfikowane niezależnie**). Potwierdzone bez zmian:
     Fernsehturm, Frauenkirche, Residenz, SEA LIFE, Brama Poznania, Fotoplastykon, Speicherstadtmuseum.
     Rozstrzygnięte pozycje:

     | Atrakcja | Karta | Wynik |
     |---|---|---|
     | Fabryka Schindlera | Krakow City Pass | **jawne 0% bez flagi** — produkt jej nie obejmuje (sprzedawana osobno); zastrzeżenie: wariant `krakow_museum_pass_student_3d` nie był sprawdzany, a 0% działa na wszystkie warianty karty |
     | Museumsinsel | Berlin WelcomeCard Classic | **jawne 0% bez flagi** — Classic bez zniżki; 100% tylko wariant `bwc_72h_museumsinsel` (kod) i „all inclusive” (poza katalogiem) |
     | Zamek Lubelski | Lublin TripPass | **jawne 0% bez flagi** — Pakiet Lubelski bez zniżek muzealnych, Zamek nie honoruje karty |
     | IMM Hamburg | Hamburg CARD | cena normalna poprawiona **17 → 18 EUR**; z kartą 14 EUR = **22,2%** (źródło imm-hamburg.de/preise-infos/, 2026-10-12). Uwaga: ten cennik podaje też Ermäßigt 13 EUR i Familie 38 EUR (w danych 12 i 36) — niezmienione, do osobnej aktualizacji |
     | Nymphenburg (combo) | München CityTourCard | **10%** = 2 EUR z biletu combo 20 EUR (lato). **Sezonowość**: zimą (od połowy października do 31 marca) combo kosztuje 16 EUR, 2 EUR to wtedy 12,5% — przy zmianie sezonu trzeba zaktualizować `normal_price` i zniżkę (model nie ma cen sezonowych). 1 EUR na bilet pojedynczy do pałacu (10 EUR) dotyczy pozycji spoza katalogu — niemodelowane |

     Jawne `0.0` w `custom_discounts` to znany brak zniżki (bez flagi), cytat i URL są w
     `_zrodla_znizek_2026_10_12` na karcie.
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
