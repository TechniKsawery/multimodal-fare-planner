# Weryfikacja cennika PKP Super Promo International PL–DE (2026-10-11)

Źródło: PKP Intercity, „Cennik oferty Super Promo International w komunikacji Polska – Niemcy",
ważny od 19.08.2026, 33 strony (`oryginalny PDF PKP IC (link w źródłach)`,
sha256 `38d58ffc…cf6088`). Pobrane z intercity.pl
2026-10-11. Wszystko poniżej odczytane z tego PDF-a, nie z opisu zewnętrznej AI.

## Co się zgadza
- Warszawa–Berlin, 2. kl., Berlin, strefa V: poziomy I–V = **34,90 / 39,90 / 44,90 / 54,90 / 59,90 EUR**.
- Tabele cen **wszystkich 7** pociągów Berlin-Warszawa-Express (40/41, 42/43, 44/45, 46/47, 48/49,
  246/247, 248/249) są identyczne, tak samo listy stref (I Rzepin; II Świebodzin, Zbąszynek;
  III Poznań; IV Kutno, Konin; V Warszawa). Sprawdzone programowo.
- Strefy: Poznań = III (BWE; 24,90–44,90), Konin = IV (27,90–44,90), Rzepin = I (19,90–27,90).
- Lista pociągów w PDF (20 tabel) zgadza się z opisem.

## Co się NIE zgadza / jest nowe
- **Lublin NIE jest w Wawelu ani Galicji** (te kończą się w Przemyślu, bez Lublina). Lublin występuje
  **tylko w Ursa 440/441 (Chełm–Berlin), strefa VI**: Berlin 2. kl. poziom I–V = 34,90 / 39,90 /
  44,90 / 54,90 / **69,90 EUR**. Przedział Lublin–Berlin = 34,90–69,90 EUR (dolny koniec jak
  Warszawa, górny wyższy). Ursa 430/431 (Przemyśl) nie obejmuje Lublina.
- Kurs w kodzie (`routing/currency.py`) to już 4,3775 PLN/EUR (NBP 2026-10-09), nie 4,30 jak w opisie.
- Wzmianka o cenach „DB Young 18,99 stałe" i „dorośli 19,99/29,99/39,99" dotyczy innego pliku, nie SPI.
- Niektóre pociągi mają 6 stref (Wawel, Galicja, Ursa) zamiast 5; strefa VI ma wyższe poziomy.

## Co wdrożono
Przedział „od X do Y" w `breakdown["zakres_cen"]` dla 13 pociągów z relacją Berlin (BWE×7, Odra,
Wawel, Galicja, Gedania, Ursa×2). Nie wdrożono: Saxonia/Via Regia (Lipsk), Chopin/Carpatia
(Monachium, miejsca sypialne). Reguły poziomów popytowych — brak w cenniku, nie modelujemy.
Pomiar e-IC 2026-10-09 (Warszawa–Berlin 44,90 EUR, wyjazd 16.10) = poziom III, w przedziale.

## Wynik dla trasy demo (Lublin → Berlin, dorosły)
SPI 34,90–69,90 EUR, regularne PKP 79 EUR (górna ogólna). Przy kursie 4,3775: 152,78–305,99 PLN.
Oferta DB „od" jako dolna granica ogólna zostaje (źródło nie podaje górnej granicy).
