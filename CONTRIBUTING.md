# Jak wnosić zmiany

## Przed merge

- CI (`.github/workflows/tests.yml`) uruchamia `ruff` i `pytest` na każdym pull requeście do `main`.
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
