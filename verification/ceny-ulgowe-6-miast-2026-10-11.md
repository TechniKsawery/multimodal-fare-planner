# Ceny ulgowe (dziecko/uczeń-student/senior/rodzina) dla 61 atrakcji — Warszawa, Hamburg, Monachium, Kolonia, Wrocław, Poznań

Data weryfikacji: 2026-10-11. Zasada: żadna cena nie jest zgadnięta — każda kwota ma `source_url` + `verified_date` i pochodzi wprost ze strony operatora (WebFetch), bez przyjmowania procentowych szacunków.

## Znaleziony i naprawiony błąd: PGE Narodowy

`warszawa_pge_narodowy` miał `normal_price: 39 PLN`, co nie odpowiadało żadnemu realnemu produktowi w cenniku (wycieczki.pgenarodowy.pl/cennik). Opis atrakcji ("szatnie, strefa VIP, murawa") odpowiada wariantowi **"Poczuj się jak VIP"**, który kosztuje **45 PLN** (normalny, indywidualny), 35 PLN ulgowy, 125 PLN rodzinny (2+2 lub 2+1). Poprawiono `normal_price` na 45.0 i dodano `student_price`/`family_price`.

## Sprawdzony, ale NIE błędny: Muzeum Powstania Warszawskiego

`warszawa_muzeum_powstania` (45 PLN) zostało ponownie zweryfikowane na 1944.pl: "Regular (full price): 45 PLN" — zgodne z danymi. Błąd zgłoszony przez wątek weryfikujący próbkę nie potwierdza się przy obecnym stanie cennika operatora (być może cennik zmienił się między próbką a tą weryfikacją, albo wcześniejsza ocena była niepoprawna). Dodano `student_price` (bilet 1 PLN dla uczących się 7-26 lat z polską legitymacją — wyjątkowo niska cena, osobno od ogólnego ulgowego 35 PLN) oraz `family_price` (95 PLN za całą rodzinę).

## Zakres wykonanej pracy

Z 61 atrakcji w 6 miastach:
- **11 jest bezpłatnych** (`normal_price: 0`) — nie wymagają cen grupowych (parki, targowiska, skwer).
- **32 atrakcje dostały nowe pola `child_price`/`student_price`/`senior_price`/`family_price`** — patrz lista commitów w `attractions/data/attractions.json`, każda z `source_url`+`verified_date`+`price_verified: true`.
- **Pozostałe ~18 atrakcji (głównie Kolonia: Museum Ludwig, Wallraf-Richartz, Römisch-Germanisches Museum, NS-Dokumentationszentrum, Kölner Seilbahn, Minigolf Familienpark; Monachium: BMW Museum; Wrocław: Ogród Botaniczny; Kolonia: Zoo, Claudius-Therme, Brewery Tour, Jochen Schweizer Kletterpark, SEA LIFE)** — strony operatorów albo nie publikują rozbicia na kategorie wiekowe, albo blokowały automatyczny dostęp (robots disallowed / brak strony), albo mają w pełni dynamiczne ceny (Kölner Zoo) nieadekwatne do modelu stałej `GroupPrice`. Te pozycje **zostały pozostawione bez zmian** (bez zgadywania) — ich dotychczasowe `normal_price`/`price_verified` NIE zostały ruszone, bo nie udało się ich ponownie potwierdzić ani zaprzeczyć w tej sesji.

## Weryfikacja cen podstawowych (`normal_price`)

Przy okazji sprawdzono zgodność istniejących `normal_price` ze stronami operatorów dla wszystkich 50 płatnych atrakcji. Poza PGE Narodowym wszystkie pozostałe wartości **zgadzają się** z aktualnym cennikiem operatora (dokładnie lub jako wartość "od"/minimalna, analogicznie do precedensu Zeche Zollverein).

## Dalsza praca (nie zrobiona w tej sesji)

- Znaleźć prawidłowe URL-e dla Museum Ludwig, Wallraf-Richartz, Römisch-Germanisches Museum, NS-Dokumentationszentrum, Kölner Seilbahn (obecnie brak `official_url` w danych).
- Ręcznie (przez przeglądarkę RC) sprawdzić BMW Museum i Ogród Botaniczny Wrocław (automatyczny fetch nieskuteczny/zablokowany).
- Kölner Zoo ma ceny dynamiczne — do decyzji, czy modelować jako zakres czy pominąć.
