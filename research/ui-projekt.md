# Projekt interfejsu wyszukiwarki tras PL ↔ DE dla uczniów i studentów

**Dokument projektowy UI/UX (Makiety & Specyfikacja Ekranów)**  
**Baza analityczna:** [`research/ui-przeglad.md`](file:///%USERPROFILE%/.gemini/antigravity/scratch/mw-ui-przeglad/research/ui-przeglad.md)  
**Grupa docelowa:** Uczniowie szkół średnich i studenci podróżujący pomiędzy Polską a Niemcami (wiek 16–26 lat), uczestnicy wymian (Erasmus+, Polsko-Niemiecka Współpraca Młodzieży DPJW), wrażliwi na koszty, podróżujący z polską lub niemiecką legitymacją, kartami BahnCard lub biletami miejskimi/semestralnymi.  
**Języki interfejsu:** Polski (PL), Niemiecki (DE), Angielski (EN), Hiszpański (ES), Francuski (FR), Niderlandzki (NL).  
**Kluczowa zasada UX:** **Jeden zintegrowany ekran wyniku** łączący cenę dla konkretnego użytkownika, bezwzględną przejrzystość statusu ceny (*oficjalna taryfa / szacunek / brak ceny*), źródło danych z datą weryfikacji, pełną responsywność (Mobile-First) oraz brak żargonu programistycznego i surowych kluczy bazodanowych.

---

## 1. Założenia projektowe i zasady UX/UI

### 1.1. Rozwiązanie problemów zidentyfikowanych w `research/ui-przeglad.md`
1. **Pewność ceny (Status Transparency):**
   * Likwidacja niejasnych dopisków typu `(taryfa_km)`, `— cena niepotwierdzona (wartość zastępcza, nie z cennika)` czy `PKP SPI poziom V`.
   * Wprowadzenie ujednoliconego, 3-stopniowego systemu statusu taryfowego z wyraźnymi znacznikami wizualnymi (badge) i kolorystyką:
     * 🟢 **OFICJALNA TARYFA** (*Official fare / Offizieller Tarif*) – cena z gwarantowanego cennika przewoźnika (np. taryfa bazowa PKP IC z ulgą ustawową 51%, taryfa strefowa BVG Berlin, bilet VBB).
     * 🟡 **SZACUNEK** (*Estimate / Schätzung*) – dynamiczny przedział cenowy z bazowej puli promocyjnej lub uśredniona stawka rynkowa (np. PKP Super Promo / DB Super Sparpreis Europa od–do).
     * ⚪ **BRAK CENY** (*No confirmed fare / Kein Tarif*) – brak aktywnego cennika dla danego odcinka w bazie, kwota oznaczona jako orientacyjny koszt kilometrowy/zastępczy z wyraźnym ostrzeżeniem.
2. **Audytowalność i zaufanie (Źródło + Data weryfikacji):**
   * Każdy wariant i odcinek zawiera metryczkę: `Źródło: [Nazwa cennika/API] • Zweryfikowano: [DD.MM.RRRR]`.
   * Uczeń/student widzi, czy cennik uwzględnia najnowszą korektę rozkładu i taryf (np. cennik PKP IC z 01.03.2026, tabela DB Sparpreis z 10.2026).
3. **Spójny profil zniżek (Koniec z pułapką "ulga tylko na atrakcje"):**
   * Jeden nadrzędny profil pasażera: Wiek + Status (Uczeń / Student) + Kraj wydania legitymacji + Karty (BahnCard itp.).
   * Automatyczna i bezbłędna dystrybucja uprawnień:
     * Legitymacja polska (mLegitymacja/plastik) → 51% na pociągi PKP IC/Polregio w PL, 50% na komunikację miejską w miastach PL, zniżka studencka na muzea.
     * Legitymacja niemiecka (*Studierendenausweis*) → brak ulgi ustawowej na PKP w PL (chyba że obywatel RP studiujący za granicą do 26 lat – obsłużone dedykowanym przełącznikiem), normalne bilety miejskie w DE (poza biletem semestralnym), zniżki studenckie na atrakcje w obu krajach.
     * Karta BahnCard (25/50) → automatycznie uwzględniana wyłącznie na odcinkach kolejowych w Niemczech (DB ICE/IC/RE).
4. **Wielojęzyczność (PL, DE, EN, ES, FR, NL):**
   * Przełącznik języka dostępny w stałym nagłówku aplikacji (kompaktowy selektor z flagami/kodami ISO).
   * Wszystkie statusy, nazwy ulg, ostrzeżenia i etykiety posiadają ustandaryzowane odpowiedniki w 6 językach.

---

## 2. Kategoryzacja statusów cenowych i źródeł danych

Każda cena cząstkowa i cena łączna w interfejsie posługuje się standaryzowanym systemem identyfikacji:

| Identyfikator | Etykieta UI (PL) | Kolorystyka i ikona | Definicja biznesowa | Przykładowy komunikat dla studenta |
| :--- | :--- | :--- | :--- | :--- |
| `OFFICIAL` | **OFICJALNA TARYFA** | Zielony badge (`#0F5132` na `#D1E7DD`), ikona `✓` lub `🟢` | Cena pochodzi ze sztywnego, obowiązującego cennika przewoźnika lub oficjalnej tabeli kilometrowej z uwzględnieniem ulgi ustawowej/handlowej. | „Gwarantowana cena biletowa z kasy/biletomatu (cennik PKP IC z 01.03.2026 z ulgą studencką 51%).” |
| `ESTIMATE` | **SZACUNEK** | Żółty/bursztynowy badge (`#664D03` na `#FFF3CD`), ikona `~` lub `🟡` | Cena zależna od dynamicznego systemu sprzedaży, puli biletów promocyjnych lub taryfy globalnej. Podawane są widełki `od–do`. | „Cena dynamiczna (Super Sparpreis Europa / PKP Promo). Cena zależy od dostępności miejsc w momencie zakupu u przewoźnika.” |
| `NO_PRICE` | **BRAK CENY** | Neutralny/szary badge (`#41464B` na `#E2E3E5`), ikona `?` lub `⚪` | Brak oficjalnego cennika dla tej relacji w bazie systemu. Zastosowano pomocniczą stawkę kilometrową lub średnią. | „Brak oficjalnego cennika w bazie. Pokazano orientacyjny koszt zastępczy (~X PLN). Przed wyjazdem sprawdź cenę u przewoźnika.” |

### Matryca metadanych weryfikacji (Źródło + Data):
* Każdy odcinek w schemacie danych przekazuje:
  * `source_name` (np. *PKP Intercity Taryfa D*, *DB Tarifverzeichnis Ausland*, *ZTM Warszawa Cennik Biletowy*, *BVG Berlin VBB-Tarif*)
  * `verification_date` (np. *12.10.2026*)
  * `ticket_buy_url` (bezpośredni link do zakupu, np. `intercity.pl`, `bahn.de`)

---

## 3. Matryca wielojęzyczności (PL / DE / EN / ES / FR / NL)

Wybór języka w prawym górnym rogu ekranu (`[ 🌐 Język: PL ▾ ]`) dynamicznie lokalizuje kluczowe komponenty widoku:

| Klucz semantyczny | PL (Polski) | DE (Deutsch) | EN (English) | ES (Español) | FR (Français) | NL (Nederlands) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `app_title` | Multimodalna wyszukiwarka PL ↔ DE | Multimodale Reisesuche PL ↔ DE | PL ↔ DE Multimodal Travel Planner | Buscador multimodal PL ↔ DE | Planificateur multimodal PL ↔ DE | Multimodale Reisplanner PL ↔ DE |
| `profile_student_pl` | Student w PL (ulga 51%) | Student in PL (51% Rabatt) | Polish Student (51% off) | Estudiante en PL (51% dto.) | Étudiant en PL (-51%) | Student in PL (51% korting) |
| `profile_school_pl` | Uczeń szkoły w PL (ulga 37%) | Schüler in PL (37% Rabatt) | School Pupil in PL (37% off) | Escolar en PL (37% dto.) | Élève en PL (-37%) | Scholier in PL (37% korting) |
| `profile_student_de` | Student w DE (Studierendenausweis) | Student in DE (Semesterticket/Ausweis) | Student in DE (German Student ID) | Estudiante en DE (Carné alemán) | Étudiant en DE (Carte étu. DE) | Student in DE (Duitse studentenpas) |
| `profile_regular` | Bilet normalny (brak ulg) | Normaltarif (keine Ermäßigung) | Standard fare (no discount) | Tarifa estándar (sin descuento) | Plein tarif (sans réduction) | Vol tarief (geen korting) |
| `badge_official` | 🟢 OFICJALNA TARYFA | 🟢 OFFIZIELLER TARIF | 🟢 OFFICIAL FARE | 🟢 TARIFA OFICIAL | 🟢 TARIF OFFICIEL | 🟢 OFFICIEEL TARIEF |
| `badge_estimate` | 🟡 SZACUNEK | 🟡 SCHÄTZUNG | 🟡 ESTIMATE | 🟡 ESTIMACIÓN | 🟡 ESTIMATION | 🟡 SCHATTING |
| `badge_no_price` | ⚪ BRAK CENY | ⚪ KEIN TARIF | ⚪ NO CONFIRMED FARE | ⚪ SIN TARIFA OFICIAL | ⚪ SANS TARIF FIXE | ⚪ GEEN TARIEF |
| `label_total_price` | Twoja cena łączna | Dein Gesamtpreis | Your Total Price | Tu precio total | Votre prix total | Jouw totale prijs |
| `label_transfers` | Przesiadki | Umstiege | Transfers | Transbordos | Correspondances | Overstappen |
| `label_verified_on` | Zweryfikowano | Geprüft am | Verified on | Verificado el | Vérifié le | Geverifieerd op |
| `label_source` | Źródło cennika | Tarifquelle | Fare source | Fuente de la tarifa | Source du tarif | Tariefbron |
| `btn_buy_ticket` | Kup u przewoźnika | Beim Anbieter buchen | Book with operator | Comprar en operador | Réserver transporteur | Boeken bij vervoerder |

---

## 4. Architektura jednego ekranu wyniku (Desktop & Mobile)

Układ eliminuje rozbicie na odrębne, odległe formularze i surowe tabele DataFrame. Zamiast tego wdraża jeden harmonijny ekran, podzielony na 4 zintegrowane strefy:

```
┌────────────────────────────────────────────────────────────────────────┐
│ [1] PASEK GŁÓWNY (Header): Logo | Trasa i Data | Przełącznik PL/EN...  │
├────────────────────────────────────────────────────────────────────────┤
│ [2] KOMPAKTOWY PASEK PROFILU UCZNIA/STUDENTA (Kto podróżuje? Ulgi)      │
├────────────────────────────────────────────────────────────────────────┤
│ [3] KARTY REKOMENDACJI: [Najtańsza 🏆] [Najszybsza ⚡] [Bezpieczna 🛡️]   │
├────────────────────────────────────────────────────────────────────────┤
│ [4] KARTA GŁÓWNA WYNIKU (Jeden zintegrowany widok):                    │
│     ┌────────────────────────────────────────────────────────────┐     │
│     │ • PODSUMOWANIE: Cena dla Ciebie | Status Taryfy | Czas      │     │
│     │ • METRYCZKA: Źródło danych taryfowych + Data weryfikacji   │     │
│     ├────────────────────────────────────────────────────────────┤     │
│     │ • OŚ CZASU TRASY (Timeline odcinków):                      │     │
│     │   - Odcinek 1 (np. Tramwaj MPK) → Kwota + Badge + Źródło   │     │
│     │   - Przesiadka (bufor czasowy: bezpieczny / ryzykowny)     │     │
│     │   - Odcinek 2 (np. Pociąg PKP IC / DB ICE) → Kwota + Badge │     │
│     │   - Odcinek 3 (np. Metro BVG) → Kwota + Badge + Źródło     │     │
│     ├────────────────────────────────────────────────────────────┤     │
│     │ • OSTRZEŻENIA KONTROLNE (Honorowanie legitymacji PL w DE)  │     │
│     │ • KARTA MIEJSKA / ATRAKCJE DLA STUDENTÓW (Opcjonalny zrzut)│     │
│     └────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Makiety interfejsu w ASCII

### 5.1. Widok Desktop (Ekran Szeroki / Tablet Poziomo)

```text
========================================================================================================================
 🚆 EduTrip PL ↔ DE | Wyszukiwarka dla uczniów i studentów               [ 🔍 Szukaj nowej trasy ]   [ 🌐 Język: PL ▾ ]
========================================================================================================================

 📍 Trasa: Poznań Główny ➔ Berlin Alexanderplatz    📅 Data: Śr, 21.10.2026 | Wyjazd: od 07:00    👥 Pasażer: 1 osoba
------------------------------------------------------------------------------------------------------------------------
 🎓 TWÓJ PROFIL ULGI:
 [ 🎓 Student w Polsce (do 26 lat, ulga 51%) ▾ ]  [ 🇵🇱 Polska legitymacja / mLegitymacja ▾ ]  [ 💳 Brak karty BahnCard ▾ ]
 [✓] Podróżuję z bagażem podręcznym (plecak)       [ ] Mam bilet semestralny w Berlinie (BVG/VBB)
========================================================================================================================

 WYBIERZ WARIANT PODRÓŻY:
 +-----------------------------------+ +-----------------------------------+ +-----------------------------------+
 | 🏆 NAJTAŃSZA DLA CIEBIE (Wybór)   | | ⚡ NAJSZYBSZA                     | | 🛡️ BEZSTRESOWA PRZESIADKA         |
 | 59,20 PLN  [ 🟢 OFICJALNA TARYFA ]| | 114,50 PLN  [ 🟡 SZACUNEK ]       | | 74,00 PLN  [ 🟢 OFICJALNA TARYFA ]|
 | ⏱️ 3h 18min • 1 przesiadka         | | ⏱️ 2h 45min • Bezpośredni ICE/EC  | | ⏱️ 3h 50min • 1 przesiadka (35m)  |
 +-----------------------------------+ +-----------------------------------+ +-----------------------------------+

========================================================================================================================
 SZCZEGÓŁY WYBRANEGO POŁĄCZENIA: Poznań Gł. ➔ Berlin Alexanderplatz
========================================================================================================================

 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │  TWOJA CENA ŁĄCZNA:                       STATUS TARYFY:               CZAS CAŁKOWITY:       PRZESIADKI:           │
 │  59,20 PLN                                [ 🟢 OFICJALNA TARYFA ]      ⏱️ 3 godz. 18 min     🔄 1 przesiadka (OK)  │
 │  (zamiast 112,00 PLN bilet normalny)                                                                               │
 │                                                                                                                    │
 │  📋 Baza taryfowa: PKP Intercity Taryfa D + VBB Berlin Tarif | 📅 Data weryfikacji danych: 12.10.2026               │
 └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 🗺️ PRZEBIEG TRASY I CENY ODCINKÓW:
 ----------------------------------------------------------------------------------------------------------------------
  Czas      Odcinek / Przewoźnik             Cena z Twoją ulgą      Status taryfy          Źródło & Weryfikacja
 ----------------------------------------------------------------------------------------------------------------------
  07:15     Poznań Główny                    
    │       🚆 PKP Intercity (IC 58)         41,65 PLN              [ 🟢 OFICJALNA TARYFA] Źródło: PKP IC Cennik Ustawowy
    │       Miejsca: Wag. 12, M. 45          (zamiast 85,00 PLN)                           Zweryfikowano: 10.10.2026
  08:52     Rzepin                           Ulga: Student 51%                             [ 🔗 Kup na intercity.pl ]
 ----------------------------------------------------------------------------------------------------------------------
  ⏳ PRZESIADKA: Rzepin | Czas na przejście: 22 minuty (Zalecane min. 10 min)  🟢 Bezpieczny czas na przesiadkę
 ----------------------------------------------------------------------------------------------------------------------
  09:14     Rzepin                           
    │       🚆 Polregio / RB91 (Transgran.)  17,55 PLN              [ 🟢 OFICJALNA TARYFA] Źródło: Taryfa Frankfurt-Polska
    │       Relacja: Rzepin - Ffo            (zamiast 27,00 PLN)                           Zweryfikowano: 05.10.2026
  09:41     Frankfurt(Oder)                  Ulga: Uczeń/Student                           [ 🔗 Kup u konduktora/kasa ]
 ----------------------------------------------------------------------------------------------------------------------
  ⏳ PRZESIADKA: Frankfurt(Oder) | Czas: 11 min | Przejście na peron 3  🟢 Czas zgodny z normą stacji
 ----------------------------------------------------------------------------------------------------------------------
  09:52     Frankfurt(Oder)
    │       🚆 DB Regio (RE 1)               0,00 PLN *             [ 🟡 SZACUNEK ]        Źródło: VBB Berlin-Brandenburg
    │       Kierunek: Magdeburg Hbf          (lub 4,40 EUR bilet)                          Zweryfikowano: 12.10.2026
  10:33     Berlin Alexanderplatz            * Patrz uwaga VBB                             [ 🔗 Kup na bahn.de ]
 ----------------------------------------------------------------------------------------------------------------------

 ℹ️ WAŻNE INFORMACJE DLA STUDENTA / UCZNIA NA TEJ TRASIE:
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ 🪪 KONTROLA BILETÓW:                                                                                               │
 │  • Odcinek PL (Poznań - Rzepin): Wymagana ważna polska legitymacja studencka (fizyczna lub mLegitymacja w mObywatel)│
 │  • Odcinek DE (Frankfurt - Berlin): Niemiecka kolej nie honoruje polskiej ulgi 51%. Jeśli nie posiadasz biletu     │
 │    semestralnego uczelni w Berlinie/Brandenburgii ani Deutschlandticket, wymagany bilet VBB Regeltarif (4,40 EUR).│
 └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 🏛️ KARTA MIEJSKA & ZNIŻKI W BERLINIE:
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │  Planujesz zwiedzanie Berlina?                                                                                     │
 │  • Berlin WelcomeCard (72h) ze zniżką studencką: 36,00 EUR [ 🟢 OFICJALNA TARYFA | Zweryfikowano: 01.10.2026 ]     │
 │  • Czy to się opłaca? Jeśli odwiedzisz Museum Island + TV Tower, oszczędzasz ~14,50 EUR w porównaniu do osobnych wejść.│
 └────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5.2. Widok Mobilny (Smartfon, szerokość ~375–430px)

Układ mobilny zoptymalizowany pod obsługę kciukiem, eliminujący konieczność przewijania horyzontalnego. Statusy i ceny są wyeksponowane na samej górze.

```text
┌─────────────────────────────────────────┐
│ 🚆 EduTrip PL↔DE         [🌐 PL ▾] [⚙️] │
├─────────────────────────────────────────┤
│ 📍 Poznań Gł. ➔ Berlin Alex.           │
│ 📅 Śr, 21.10 • 07:15 • 1 pasażer       │
├─────────────────────────────────────────┤
│ 🎓 PROFIL: Student PL (51%)             │
│    Legitymacja: Polska [Zmień ✎]       │
├─────────────────────────────────────────┤
│ WYBIERZ WARIANT:                        │
│ ┌─────────────────────────────────────┐ │
│ │ 🏆 NAJTAŃSZY (Wybrany)              │ │
│ │ 59,20 PLN   [ 🟢 OFICJALNA ]        │ │
│ │ ⏱️ 3h 18m  •  🔄 1 przesiadka       │ │
│ └─────────────────────────────────────┘ │
│ [ ⚡ Najszybszy: 114,50 zł | 2h 45m ]   │
│ [ 🛡️ Bezpieczny: 74,00 zł | 3h 50m ]    │
├─────────────────────────────────────────┤
│ PODSUMOWANIE KOSZTÓW                    │
│ ┌─────────────────────────────────────┐ │
│ │ Twoja cena:                         │ │
│ │ 59,20 PLN                           │ │
│ │ Cennik normalny: 112,00 PLN (-47%)  │ │
│ │                                     │ │
│ │ Status: 🟢 OFICJALNA TARYFA         │ │
│ │ Źródło: PKP IC + VBB Berlin         │ │
│ │ Weryfikacja: 12.10.2026             │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ PLAN PODRÓŻY KROK PO KROKU:             │
│                                         │
│ 🔘 07:15 Poznań Główny                  │
│  │ 🚆 IC 58 (PKP Intercity)             │
│  │ 💰 41,65 PLN [ 🟢 OFICJALNA ]        │
│  │ 🪪 Ulga: Student 51% (mLegitymacja)  │
│  │ ℹ️ Źródło: PKP IC (10.10.2026)       │
│  │ [ 🔗 Kup bilet PKP ]                 │
│ 🔘 08:52 Rzepin                         │
│                                         │
│ ⏱️ PRZESIADKA: Rzepin (22 min)          │
│    🟢 Bezpieczny czas na przejście      │
│                                         │
│ 🔘 09:14 Rzepin                         │
│  │ 🚆 RB91 Polregio (Transgraniczny)    │
│  │ 💰 17,55 PLN [ 🟢 OFICJALNA ]        │
│  │ ℹ️ Źródło: Taryfa Ffo-PL (05.10.2026)│
│ 🔘 09:41 Frankfurt(Oder)                │
│                                         │
│ ⏱️ PRZESIADKA: Frankfurt(O.) (11 min)   │
│    🟢 Czas wystarczający na peron 3     │
│                                         │
│ 🔘 09:52 Frankfurt(Oder)                │
│  │ 🚆 RE 1 (DB Regio)                   │
│  │ 💰 ~19,00 PLN / 4,40 € [ 🟡 SZACUNEK]│
│  │ ℹ️ Źródło: VBB Berlin (12.10.2026)   │
│ 🔘 10:33 Berlin Alexanderplatz          │
├─────────────────────────────────────────┤
│ ⚠️ WAŻNE PRZY KONTROLI:                 │
│ • Przygotuj mLegitymację na trasie w PL │
│ • Ulga 51% NIE działa w Niemczech!      │
├─────────────────────────────────────────┤
│ 🏛️ ATRAKCJE DLA STUDENTÓW W BERLINIE:   │
│ • Bilet 24h BVG ulgowy: 6,50 EUR        │
│ • Karta Berlin WelcomeCard: 36,00 EUR   │
│ [ Rozwiń szczegóły zniżek turystycznych]│
└─────────────────────────────────────────┘
```

---

## 6. Warianty prezentacji statusów cenowych

Aby zrealizować wymóg jednoznacznego oznaczenia poziomu wiarygodności ceny, wdrożono trzy dedykowane komponenty wizualne dla każdego stanu:

### Przypadek 1: 🟢 OFICJALNA TARYFA (Gwarantowana)
* **Kiedy występuje:** Trasa kolejowa krajowa w Polsce (PKP IC z ustawową zniżką 51% lub szkolną 37%) lub bilet jednorazowy komunikacji miejskiej ze sztywnego cennika uchwalonego przez miasto (np. bilet 20-minutowy ZTM Warszawa, bilet pojedynczy BVG).
* **Komponent w UI:**
  ```text
  ┌────────────────────────────────────────────────────────┐
  │ 💰 41,65 PLN   [ 🟢 OFICJALNA TARYFA ]                 │
  │ ℹ️ Gwarantowana cena z oficjalnego cennika PKP IC      │
  │    (uwzględniono ulgę ustawową 51% dla studenta)       │
  │ 📋 Źródło: PKP IC Taryfa D • Zweryfikowano: 10.10.2026  │
  └────────────────────────────────────────────────────────┘
  ```

### Przypadek 2: 🟡 SZACUNEK (Cena dynamiczna / przedział od–do)
* **Kiedy występuje:** Połączenia międzynarodowe (np. Berlin-Warszawa-Express / EuroCity), bilety dalekobieżne DB Sparpreis / PKP Super Promo, bilety lotnicze lub autokarowe (FlixBus), gdzie cena zmienia się w zależności od popytu.
* **Komponent w UI:**
  ```text
  ┌────────────────────────────────────────────────────────┐
  │ 💰 od 89,00 do 149,00 PLN   [ 🟡 SZACUNEK ]            │
  │ ℹ️ Cena dynamiczna (pula promocyjna Super Promo / DB)   │
  │    Rzeczywisty koszt zależy od momentu zakupu u przewoźnika.
  │ 📋 Źródło: PKP/DB Sparpreis Europa • Zweryfikowano: 12.10.2026 │
  └────────────────────────────────────────────────────────┘
  ```

### Przypadek 3: ⚪ BRAK CENY (Koszt orientacyjny / zastępczy)
* **Kiedy występuje:** Brak aktualnego cennika danego przewoźnika prywatnego w bazie, bilet zintegrowany na nietypowym węźle przesiadkowym, odcinek pieszy lub taksówkowy/miejski bez danych taryfowych.
* **Komponent w UI:**
  ```text
  ┌────────────────────────────────────────────────────────┐
  │ 💰 ~25,00 PLN (orientacyjnie)   [ ⚪ BRAK CENY ]       │
  │ ⚠️ Brak oficjalnego cennika dla tego odcinka w systemie.│
  │    Wyliczono szacunkowy koszt na podstawie kilometrów. │
  │ 📋 Źródło: Stawka ryczałtowa • Weryfikacja: Brak       │
  └────────────────────────────────────────────────────────┘
  ```

---

## 7. Specyfikacja selektora języków (PL / DE / EN / ES / FR / NL)

### 7.1. Umiejscowienie i zachowanie (UX)
1. **Lokalizacja:** Prawy górny róg paska nawigacyjnego (Header), dostępny na każdym urządzeniu. Na telefonie dostępny w nagłówku jako rozwijane menu (dropdown).
2. **Persistence (Trwałość wyboru):** Wybór języka jest natychmiast zapisywany w `session_state` (lub parametrze URL `?lang=de`), co umożliwia bezpośrednie dzielenie się linkami do wyników w wybranym języku (np. wysłanie linku do trasy koledze z Niemiec lub Hiszpanii).
3. **Komponent Dropdown:**
   * 🇵🇱 **Polski (PL)**
   * 🇩🇪 **Deutsch (DE)**
   * 🇬🇧 **English (EN)**
   * 🇪🇸 **Español (ES)**
   * 🇫🇷 **Français (FR)**
   * 🇳🇱 **Nederlands (NL)**

---

## 8. Specyfikacja pól danych pojedynczego wyniku (Kontrakt widoku)

Aby zapewnić pełną spójność danych pomiędzy silnikiem wyszukiwarki a prezentacją UI, pojedynczy wynik trasy definiuje następujący kontrakt:

```typescript
interface SingleRouteResultView {
  // Podsumowanie główne
  route_id: string;
  variant_type: 'cheapest' | 'fastest' | 'safest_transfer';
  total_price_user: {
    amount: number;
    currency: 'PLN' | 'EUR';
    formatted: string;               // np. "59,20 PLN"
    regular_amount: number;          // cena bez ulgi, np. 112.00
    saving_percent: number;          // np. 47
    status: 'OFFICIAL' | 'ESTIMATE' | 'NO_PRICE';
    status_label_i18n: string;       // np. "OFICJALNA TARYFA"
  };
  total_duration_minutes: number;    // np. 198 (3h 18m)
  transfer_count: number;
  transfer_safety_status: 'SAFE' | 'TIGHT' | 'RISKY';
  
  // Audyt i wiarygodność
  verification_summary: {
    primary_sources: string[];       // ["PKP Intercity Taryfa D", "VBB Berlin"]
    last_verified_date: string;      // "2026-10-12"
    all_legs_verified: boolean;
  };

  // Szczegółowe odcinki podróży
  legs: Array<{
    leg_index: number;
    origin_name: string;
    destination_name: string;
    departure_time: string;          // "07:15"
    arrival_time: string;            // "08:52"
    carrier_name: string;            // "PKP Intercity"
    line_code: string;               // "IC 58"
    leg_price: {
      amount: number;
      currency: string;
      status: 'OFFICIAL' | 'ESTIMATE' | 'NO_PRICE';
      source_name: string;           // "PKP IC Cennik Ustawowy"
      verified_date: string;         // "2026-10-10"
      applied_discount_name: string; // "Student w Polsce (51%)"
      booking_url?: string;
    };
    transfer_after?: {
      station_name: string;
      duration_minutes: number;
      safety_level: 'SAFE' | 'TIGHT' | 'RISKY';
      advice_text_i18n: string;      // "Bezpieczny czas na przesiadkę (22 min)"
    };
  }>;

  // Informacje prawne i ostrzeżenia dla ucznia/studenta
  student_notices: Array<{
    severity: 'info' | 'warning';
    country_scope: 'PL' | 'DE' | 'CROSSBORDER';
    text_i18n: string;
  }>;

  // Moduł turystyczny / Karta miejska (opcjonalny)
  city_card_addon?: {
    city_name: string;
    recommended_card: string;
    card_price_student: string;
    status: 'OFFICIAL' | 'ESTIMATE';
    verification_date: string;
    savings_estimate_text: string;
  };
}
```

---

## 9. Podsumowanie korzyści nowego projektu

1. **Dla ucznia i studenta:**
   * Koniec z przykrymi niespodziankami podczas kontroli biletów (wyraźne ostrzeżenie, że polska legitymacja studencka nie uprawnia do 51% ulgi w pociągach DB Regio / ICE w Niemczech).
   * Natychmiastowa wiedza, ile dokładnie zapłaci ze swoją legitymacją oraz ile zaoszczędził w stosunku do biletu normalnego.
   * Pewność co do ceny – uczeń widzi, kiedy cena jest gwarantowana w kasie, a kiedy jest jedynie szacunkiem internetowym.
2. **Dla studentów z zagranicy (Erasmus+, Niemcy, kraje UE):**
   * Pełna dostępność językowa (DE, EN, ES, FR, NL obok PL).
   * Jasne instrukcje dotyczące rodzajów akceptowanych dokumentów (Schülerausweis, mLegitymacja, legitymacja plastikowa, ISIC).
3. **Dla ergonomii mobilnej:**
   * Czytelny, 1-kolumnowy układ na smartfonie z dużymi elementami dotykowymi, idealny do sprawdzania trasy na dworcu lub peronie.
