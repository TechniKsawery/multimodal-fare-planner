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
