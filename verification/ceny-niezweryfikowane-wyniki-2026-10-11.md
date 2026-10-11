# Dokończenie weryfikacji cen (2026-10-11)

## PKP IC Polska-Niemcy — POTWIERDZONE z PDF
PDF pobrany do `oryginalny PDF PKP IC (link w źródłach)` (+ tekst `cennik.txt`). Opłata podstawowa, 2 klasa, do Berlina:
Warszawa, Kraków, Gdynia = 69 EUR; Lublin, Przemyśl = 79 EUR; Poznań = 47 EUR. Zgodne z `fares/data/international_pl_de_pkp.json`.

## Fernsehturm Berlin — potwierdzone "od"
tv-turm.de/tickets: Standard od 20,00 EUR (BESTPREIS, jeśli dostępny), wariant z napojem od 31,00 EUR. Ceny dynamiczne, dokładna kwota dopiero po wyborze terminu — zostaje oznaczone jako "od".

## Nadal niepotwierdzone u operatora (zostają `price_verified:false`)
- BMW Museum: źródła wtórne sprzeczne (10 EUR vs 17 EUR; 17 może być biletem łączonym). Strona operatora nie pokazuje ceny. Do ręcznego sprawdzenia.
- Wallraf-Richartz: muzeum zamknięte (remont, otwarcie ok. końca 2028). koeln.de podaje 13 EUR normalny / 9 ulgowy (dane mają 8). Rekomendacja: usunąć z ofert do otwarcia.
- Ogród Botaniczny Wrocław: wroclaw.pl (sezon 2025) 30/20 zł; cennik 2026 niepublikowany, strona operatora niedostępna z tego środowiska.

## Aktualizacja 2026-10-11 (weryfikacja na PC przez przeglądarkę, bez płatności)
- **BMW Museum:** potwierdzone 17 EUR normalny / 9 EUR ulgowy / 16 EUR grupowy (tkts.bmw-welt.com, produkt "BMW Museum entry", termin 14.10.2026). `price_verified: true` dla 17 EUR; ulgowy 9 EUR niemodelowany.
- **Wallraf-Richartz:** zamknięte do końca 2028 (wallraf.museum/aktuell/voruebergehend-geschlossen/). Oznaczone w danych, ceny nie zgadywane.
- **Ogród Botaniczny Wrocław:** 30/20 zł potwierdzone u operatora (ogrodbotaniczny.wroclaw.pl/cennik.html), `price_verified: true`.
- **PKP IC:** kwoty 69/79/47 EUR (2 kl., do Berlina) potwierdzone w PDF `zrodla-pdf/`; do Frankfurtu Odra odpowiednio 65/68/38.
