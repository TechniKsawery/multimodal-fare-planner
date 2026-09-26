# Moduł taryf (`fares/`)

Szacuje cenę pojedynczego segmentu podróży dla trzech przewoźników:

- **PKP Intercity** (`fares/pkp.py`) — cena z tabeli pasm odległości × mnożnik ulgi.
- **DB** (`fares/db.py`) — Flexpreis jako górna granica z tabeli pasm odległości × mnożnik BahnCard
  (BahnCard 25 → ×0.75).
- **VRR** (`fares/vrr.py`) — sztywna tabela cen dla wybranych relacji.

## ⚠️ Dane cenowe to placeholdery

Wszystkie liczby w `fares/data/*.json` są **przykładowe, nie oficjalne**. Nie mieliśmy dostępu
do żadnego prawdziwego cennika PKP Intercity, DB czy VRR — struktura modułu jest gotowa,
ale trzeba podmienić dane, żeby wyniki były wiarygodne. Każdy wynik (`PriceEstimate.price_type`)
jest oznaczony jako `PriceType.ESTIMATE` ("szacunek"); `PriceType.OFFICIAL` ("oficjalna_taryfa")
istnieje w modelu i można go ustawić, gdy dane będą pochodzić z faktycznego cennika przewoźnika.

### Czego potrzeba, żeby podmienić placeholdery

1. **PKP Intercity** — aktualny cennik (np. tabela IC/TLK/EIC 2. klasy wg pasm odległości,
   z osobna dla poszczególnych kategorii pociągów jeśli się różnią) + lista kodów ulg ustawowych
   i ich wysokości. Najlepiej PDF/XLS z cennika PKP IC albo link do API.
2. **DB** — Flexpreis nie jest funkcją samej odległości w rzeczywistym systemie DB (zależy od
   konkretnej trasy, klasy pociągu, popytu). Potrzeba albo próbek cen dla konkretnych relacji
   PL↔DE, które nas interesują, albo dostępu do API DB (np. przez cenę zwracaną w wyszukiwarce),
   żeby zastąpić tabelę pasm realnym źródłem. Same wysokości rabatu BahnCard 25/50/100 są znane
   i publiczne (25%/50%/100% odpowiednio), ale warto potwierdzić dla Flexpreis konkretnie.
3. **VRR** — cennik VRR (PDF `Preisliste` / `Preisstufen`) z cenami dla stref/relacji, które
   nas interesują (np. Gelsenkirchen, Duisburg, Essen, Dortmund, Düsseldorf i okolice) — obecna
   tabela ma tylko kilka przykładowych relacji.

Po dostarczeniu tych danych: zaktualizować pliki w `fares/data/`, usunąć pole `_uwaga`
z każdego JSON-a i przełączyć `price_type` na `PriceType.OFFICIAL` w odpowiednim kalkulatorze
(`pkp.py` / `db.py` / `vrr.py`).

## Użycie

```python
from fares import estimate_price
from fares.model import Carrier, DiscountProfile, Segment

segment = Segment(
    carrier=Carrier.PKP_INTERCITY,
    origin="Lublin",
    destination="Warszawa Wschodnia",
    distance_km=170,
    discounts=DiscountProfile(pkp_ulga_kod="ulga_37"),
)
result = estimate_price(segment)
print(result)  # np. "30.87 PLN (szacunek) — pkp_intercity"
print(result.breakdown)
```

## Testy

```
pytest tests/test_fares.py
```
