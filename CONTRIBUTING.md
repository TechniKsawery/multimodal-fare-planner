English | Polski: [wersja polska](CONTRIBUTING.pl.md)

# Jak wnosić zmiany

Projekt przyjmuje poprawki i ulepszenia od społeczności. Zmiany powinny być
zgodne z [PolyForm Noncommercial License 1.0.0](LICENSE). Autorzy zachowują
prawa autorskie do swoich oryginalnych wkładów, a ich autorstwo powinno być
widoczne w historii GitHub oraz w opisie pull requesta.

Przed przesłaniem pull requesta upewnij się, że masz prawo udostępnić zmianę
oraz że nie zawiera ona kluczy API, danych prywatnych ani materiałów objętych
niezgodną licencją. Wkład nie zmienia licencji istniejącego kodu projektu.

## Przed merge

- CI (`.github/workflows/tests.yml`) uruchamia `pytest` na każdym pull requeście do `main`.
  Musi być zielone. Testy wymagające MOTIS są w CI pomijane (skip), więc zielone CI to NIE jest
  dowód, że wyniki zgadzają się z rzeczywistością.
- `tests/test_data_consistency.py` pilnuje reguł danych: każda cena ulgowa ma granicę wieku lub
  status, każda potwierdzona cena ma źródło (URL) i datę, karta miejska bez potwierdzonego
  istnienia nie trafia do rekomendacji, waluty nie są mieszane. Dodając dane, nie dopisuj wyjątków
  do list `KNOWN_*` — uzupełnij rekord.

## Duża zmiana wymaga testu na żywo PRZED merge

Za dużą zmianę uważamy m.in.: nowe miasto lub kategorię danych, zmianę kalkulatora cen/zniżek/kart,
zmianę routingu lub konfiguracji MOTIS, zmianę łączącą kilka PR-ów naraz.

Przed merge takiej zmiany uruchom ją na realnym MOTIS (`docker compose up`, potem `demo.py` lub
UI) i sprawdź na żywo kilka tras oraz kilka cen z oficjalnym cennikiem operatora. Wynik (co
sprawdzono, na jakich trasach) wpisz w opis PR. Zielone testy bez takiego sprawdzenia nie
wystarczają do merge dużej zmiany.

## Zasada źródeł

Nigdy nie zgaduj ceny, zniżki ani partnera: podaj URL źródła i datę weryfikacji albo ustaw
`price_verified: false`.

## Dane z zewnętrznych AI i wklejek

Dane i liczby pochodzące od zewnętrznych AI lub z wklejek z innych czatów (ceny, zniżki, zasady,
nazwy partnerów) wolno wpisać do repo dopiero po weryfikacji w źródle pierwotnym (oficjalny cennik,
regulamin, strona operatora). Zewnętrzne AI w tym projekcie wielokrotnie myliły liczby i mieszały
dokumenty. Każda cena ma `source_url` i datę weryfikacji; jeśli źródła nie da się sprawdzić, pole
zostaje puste lub `price_verified: false`.
