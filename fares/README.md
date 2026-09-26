# Moduł taryf (`fares/`)

Szacuje cenę pojedynczego segmentu podróży dla trzech przewoźników:

- **PKP Intercity** (`fares/pkp.py`) — cena z tabeli pasm odległości × mnożnik ulgi.
- **DB** (`fares/db.py`) — Flexpreis jako górna granica z tabeli pasm odległości × mnożnik BahnCard
  (BahnCard 25 → ×0.75, BahnCard 50 → ×0.5).
- **VRR** (`fares/vrr.py`) — taryfa eezy.nrw: cena = Grundpreis + cena za km (linii prostej),
  z sufitem cenowym.

## Stan danych po researchu (2026-09-26)

| Przewoźnik | Status | Źródło |
|---|---|---|
| PKP Intercity — pasma cenowe (TLK/IC, 2. klasa) | **oficjalne** | [Cennik PKP Intercity](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Cennik_uslug_przewozowych_PKP_Intercity_tekst_ujednolicony_obowiazuje_od_23.07.2026_r.pdf), tekst ujednolicony od 23.07.2026 |
| PKP Intercity — ulgi ustawowe | **oficjalne** | [Tabele ulg ustawowych](https://www.intercity.pl/pl/dokumenty/Przepisy%20i%20taryfy/Ulgi%20ustawowe/Tabele_ulg_ustawowych_11-02-2026.pdf), stan na 11.02.2026 |
| VRR — eezy.nrw (Grundpreis + cena/km) | **oficjalne** | [Preistabelle VRR](https://www.vrr.de/fileadmin/user_upload/pdf/service/downloads/Weitere_Broschueren_und_Tarifinformationen/VRR_Preise_2026.pdf), Stand 01.06.2026 |
| DB — mnożniki BahnCard 25/50 | **oficjalne** | [bahn.de/faq/pk/angebot/flexpreis](https://www.bahn.de/faq/pk/angebot/flexpreis) |
| DB — tabela pasm odległości Flexpreis | **szacunek, skalibrowany do 1 realnej próbki** | DB nie publikuje takiej tabeli (cena dynamiczna); próba żywego wyszukiwania na bahn.de zablokowana jako ruch bota (błąd 751) — użyto zamiast tego realnej ceny Halle→München (373 km, 106–127 EUR) z bahndampf.de + oficjalnie cytowanej górnej granicy (150 EUR 2. klasa) do skalibrowania prostej formuły baza+km |

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
