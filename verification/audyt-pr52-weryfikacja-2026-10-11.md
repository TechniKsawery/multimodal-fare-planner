# Weryfikacja raportu audytowego PR #52 (2026-10-11)

Odtworzone na main (08de294) i gałęzi PR #52. Źródła sprawdzone WebFetch 2026-10-11.

| Zarzut | Werdykt | Dowód / poprawka |
|---|---|---|
| 4 ceny dziecięce bez max_age | POTWIERDZONY (tylko PR) | dorosły 35 l.: St. Michaelis 8→5, Speicherstadt 6→3, Skylift 13→8, Odysseum 22→16. Odysseum: max_age 15 (dorosły "ab 16 Jahren"). St. Michaelis, Speicherstadt (status Schüler), Skylift (limit wzrostu 1,40 m) - źródło nie podaje górnej granicy wieku, więc child_price USUNIĘTE. Kod: child_price bez max_age nie przysługuje już nikomu. |
| best_price ignoruje wiek/kraj dla student/senior | POTWIERDZONY | 30-latek ze studentem dostawał 1 PLN. Kod egzekwuje min/max_age i recognized_countries; Powstanie: ["PL"]; UI ma wybór kraju legitymacji. |
| Kraków Card EUR vs atrakcje PLN | POTWIERDZONY (main) | 83 PLN vs 32 EUR dodawane bez przeliczenia. Teraz konwersja routing.currency, waluta wyniku = waluta atrakcji. |
| Warianty bez transportu liczą transport jako oszczędność | POTWIERDZONY (main) | net_savings rósł 1:1 z kosztem transportu (8,83→38,83). Naprawione. |
| /attractions?category=zla → 500; nieznane miasto bez filtra | POTWIERDZONY (main) | teraz 400 (kategoria, miasto w /attractions i /city-cards). |
| Bavaria Filmstadt student 23 € | POTWIERDZONY | filmstadt.de/infos-preise/preise: ermäßigt dla grup 20+, seniorów 60+, niepełnosprawnych, MVV; studenci brak. Przeniesione do senior_price (min_age 60). |
| Botanischer Garten 0 € do 18 lat vs 12 | CZĘŚCIOWO | źródło (botmuc.snsb.de): dzieci <12 wolne ORAZ młodzież <18 wolna, więc cena nie była błędna; poprawiono off-by-one max_age 18→17 i etykietę. |
| Hydropolis miks weekend/dzień powszedni | NIEPOTWIERDZONY | bilety.hydropolis.pl/cennik: dzień powszedni 45/36/130, weekend 47/38/140; dane PR spójnie dzień powszedni. Rodzinny 2+2 (wariant 2+3 dotyczy Dużej Karty Rodziny, której nie ma w danych). |
| Panorama Racławicka family_price | NIEPOTWIERDZONY jako błąd danych | mnwr.pl: 35 zł od osoby; etykieta już to mówi, pole nieużywane w obliczeniach. |
| Ceny zewnętrzne (Jugend BahnCard, Narodowy, Poznań Zoo, Termy, VRS, ZTM, BahnCard 25, WelcomeCard 72h, Kraków Card) | NIESPRAWDZONE | poza zakresem tego przejścia; bez zmian w danych (zasada: nie zgadujemy). |

Demo Gelsenkirchen: MOTIS niedostępny w chmurze (connection refused) - sprawdzono ścieżkę atrakcji/kart na Gelsenkirchen, testy mockowane zielone.
