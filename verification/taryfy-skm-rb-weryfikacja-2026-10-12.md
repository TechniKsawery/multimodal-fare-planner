# Weryfikacja taryf SKM i pociągów regionalnych (raport Gemini) — 2026-10-12

Zadanie: niezależnie sprawdzić klucz liczb z `research/skm-rb-taryfy.md`
(gałąź `gemini/skm-rb-taryfy`) i wdrożyć tylko to, co potwierdzone.

## Dostęp do źródeł

Wszystkie cztery domeny pierwotne były niedostępne z sesji weryfikującej: `polregio.pl`,
`www.skm.pkp.pl`, `www.mazowieckie.com.pl`, `www.vbb.de` (`CONNECT` → 403 z polityki egress
środowiska; `WebFetch` też nie rozwiązuje tych domen ani portali pośrednich). Nie omijano blokady.
Zostało wyszukiwanie (streszczenia wyników), które nie pozwala przeczytać wierszy tabel.

## Klucz liczb

| Liczba | Wynik | Co znaleziono |
|---|---|---|
| Polregio do 5 km 6,10 zł | niepotwierdzone | Brak kwoty w wynikach. Wynik wskazuje cennik POLREGIO „Załącznik 2 — bilety jednorazowe od 1.03.2026" (polregio.pl/media/28288), którego wierszy nie widać; raport opiera się na tabeli z 15.12.2024, więc możliwa nieaktualność. |
| Polregio 74-80 km 25,90 zł | niepotwierdzone | j.w. |
| Polregio 91-100 km 29,70 zł | niepotwierdzone | j.w.; wyniki tylko wskazują PDF-y z tabelami (2018, 2022, 15.12.2024) bez czytelnych wierszy. |
| SKM Trójmiasto 1-6 km 7,00 zł | tylko źródło wtórne | Zgodność z serwisem konsumenckim (konskieuroczysko.pl, cennik od 1.03.2026); oficjalny załącznik nieotwarty. Wrzesień 2024: 5,50 zł (oficjalny cennik SKM), czyli wartość jest nowsza i plausibilna, ale bez źródła pierwotnego. |
| SKM Trójmiasto 31-40 km 14,00 zł | tylko źródło wtórne | j.w. |
| KM do 5 km 4,20 zł | częściowo | Fragment oficjalnego załącznika TP-KM obowiązującego od 1.07.2022 zawiera wiersz „do 5" = 4,20 zł. Nie wiadomo, czy to nadal aktualny cennik (raport powołuje się na zmiany nr 1-6). |
| KM 41-50 km 17,90 zł | niepotwierdzone | Wiersz nieodczytany (obcięty fragment). |
| VBB Szczecin Gł. – Angermünde 13,50 EUR | niepotwierdzone | Brak kwoty w wynikach. Polregio podaje, że RE66/RB66 między Szczecinem Gł. a Angermünde NIE kursują w 2026 (pełne zamknięcie, komunikacja zastępcza ZKA). |
| VBB Szczecin – Tantow 4,40 EUR | niepotwierdzone | Brak kwoty w wynikach. |

Sygnał niespójności raportu: VBB (tabela Berlin–Szczecin) podaje 15,90 EUR (pełny) i 11,50 EUR
(ulgowy), raport Gemini 16,80 EUR i 12,20 EUR dla Berlin AB – Szczecin.

## Decyzje

- POLREGIO/KD/KŚ: tabela wdrożona jako **niepotwierdzony szacunek** (mechanizm potwierdzania
  per pasmo gotowy, patrz fares/README.md). Żadnego pasma nie oznaczono jako potwierdzone.
- SKM Trójmiasto, Koleje Mazowieckie, VBB Teil E (Szczecin – Angermünde/Tantow): NIE wdrożone.
  Warunek „jeśli potwierdzone" niespełniony; dodatkowo RB66 na tym odcinku nie kursuje.
- ZTM Warszawa, ŁKA: nie ruszane (patrz PR).

## Do zrobienia po otwarciu domen (lub ręcznym odczycie PDF-ów)

1. Odczytać tabelę nr 1 w aktualnym cenniku POLREGIO (Załącznik 2 od 1.03.2026) i wpisać
   `potwierdzone` per pasmo w `fares/data/polregio_taryfa_podstawowa.json`; poprawić kwoty,
   jeśli różnią się od raportu.
2. Ustalić, w których województwach POLREGIO nie stosuje Taryfy Podstawowej.
3. SKM Trójmiasto i KM: odczytać tabele z oficjalnych PDF-ów i dodać osobne kalkulatory.
4. VBB Teil E (s. 123 broszury taryfowej): odczytać Angermünde/Tantow i wycenić odcinek w EUR
   dopiero, gdy RB66 realnie kursuje.
5. ZTM Warszawa w SKM i ŁKA w Łodzi: bilety czasowe, nie kilometrowe; wymaga decyzji, czy model
   (odcinek → cena) ma wprowadzić taryfę czasową dla pociągów.
