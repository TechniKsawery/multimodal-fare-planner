# Zestawienie weryfikacji: atrakcje i karty miejskie (2026-10-10)

> Uwaga: sesja działała w lokalnym worktree na Windows (nie w środowisku cloud), więc katalog
> `/mnt/project-files/verification/` wskazany w briefie nie istniał — ten plik zapisano w repo.
> Weryfikacja wykonana w realnej przeglądarce (Claude in Chrome) oraz, tam gdzie strona nie
> blokowała automatycznego dostępu, przez odczyt tekstu strony (WebFetch) — każda pozycja ma
> podany `source_url`. Zero zgadywania: gdzie operator nie podaje kwoty wprost, pole zostaje
> puste z notatką `_UWAGA_*`.

## Aktualizacja 2026-10-11 (kontynuacja na prośbę "próbuj dalej")

- **Signal Iduna Park — ulga doprecyzowana**: po wybraniu KONKRETNEGO terminu zwiedzania (niedziela 11.10.2026, 15:00) w sklepie biletowym (ticket-onlineshop.com) strona pokazała pełny, dokładny cytat operatora: *"Ermäßigter Eintritt für Jugendliche unter 18, Schüler, Studenten, Arbeitslose, Schwerbehinderte, Rentner (alle nur mit gültigem Nachweis)"* za 12,00 EUR. Wcześniej mieliśmy tylko kwotę bez pełnej definicji uprawnionych — teraz w pełni potwierdzone.
- **Fernsehturm Berlin — ceny DYNAMICZNE, nie stałe**: zweryfikowano NA ŻYWO w widżecie rezerwacji (tv-turm.de) po wybraniu terminu — ceny "Standard Ticket" zmieniają się godzinowo/dziennie (np. dorosły 24,00–29,50 EUR w ciągu jednego dnia). Istnieje osobna kategoria "Child" (4-14 lat), potwierdzona przykładowo na 14,00 EUR dla tego samego terminu co dorosły 24,00 EUR, oraz kategoria "Infant" (nie doprecyzowana dalej). To wyjaśnia, czemu strona ogólna podawała tylko "ab 20 EUR" — to literalnie najniższa cena z dynamicznego cennika, nie stała stawka.
- Arena Lublin: ponowna próba (mosir.lublin.pl) — strona nadal nie publikuje żadnej tabeli zniżek, podstrona "zwiedzanie" nie ma odrębnego linku w menu. Pozostaje NIEPOTWIERDZONE.
- Zeche Zollverein — "6 wariantów": premisa briefu POTWIERDZONA jako błędna (patrz sekcja wyżej) — nie podjęto rozbicia na 6 `Attraction`, bo wymagałoby to wymyślenia struktury nieopartej na rzeczywistym cenniku operatora (zgadywanie), a nie weryfikacji.

## Zakres

Branch roboczy: `claude/verify-attractions-cards-2026-10-10`, oparty na `claude/attraction-group-pricing` (PR #45, 4 miasta: Gelsenkirchen/Ruhr, Berlin, Kraków, Lublin). **Dane dla 6 dodatkowych miast (Warszawa, Hamburg, Monachium, Kolonia, Wrocław, Poznań) żyją w innych, niezmergowanych branchach (PR #42 `claude/project-thread-kvfft9`, PR #43 `claude/project-thread-gpd2se`) — NIE edytowano tych plików w tym branchu** (zgodnie z instrukcją koordynatora: scalanie konfliktów robi osobna sesja). Dla Kolonii i Hamburga poniżej są tylko ustalenia faktograficzne do przeniesienia przez tę sesję koordynującą do PR #42.

## Tabela: 4 miasta z PR #45

| Atrakcja/Karta | Status | Potwierdzona kwota | Źródło | Data |
|---|---|---|---|---|
| Signal Iduna Park — Stadiontour (90 min) | Ermäßigt (uczeń/student/bezrobotny/rencista) | **12,00 EUR** (produkt 18,00 EUR) | ticket-onlineshop.com (sklep biletowy BVB), konkretny event | 2026-10-10 |
| Alte Försterei — Stadionführung | Dziecko do 6 lat | **0,00 EUR** | altefoersterei.berlin/de/stadion/stadionfuehrung-xcFo | 2026-10-10 |
| Alte Försterei — Stadionführung | Ermäßigt | **10,00 EUR** | tamże | 2026-10-10 |
| Alte Försterei — Stadionführung | Karta rodzinna (2+2, dzieci do 14) | **34,00 EUR** | tamże | 2026-10-10 |
| Museumsinsel (Bereichskarte) | Dzieci/młodzież do 18 lat | **0,00 EUR (bezpłatnie)** | smb.museum/besuch-planen/preise-tickets/ + /tickets-einlass/ | 2026-10-10 |
| Museumsinsel (Bereichskarte) | Ermäßigt (uczeń/student/bezrobotny) | **NIEPOTWIERDZONE** — ogólna zniżka 50% SMB istnieje, ale nie jest explicite powiązana z tym konkretnym biletem zbiorczym | smb.museum | 2026-10-10 |
| Olympiastadion Berlin | ⚠️ ROZBIEŻNOŚĆ | Obecny `normal_price=15 EUR` **nie odpowiada żadnemu realnemu produktowi** (self-guided 11/8/6/27 EUR; Führungen 17-25 EUR) | olympiastadion.berlin (besichtigung + fuehrungen) | 2026-10-10 |
| Fernsehturm Berlin | Ermäßigt/dziecko | NIEPOTWIERDZONE — strona podaje tylko "ab 20 EUR", ticket widget JS nie oddał pełnej tabeli | tv-turm.de/tickets/ | 2026-10-10 |
| Katedra Wawelska | ⚠️ KOREKTA CENY | `normal_price` poprawiono **22→26 PLN** | bilety-wawel.pl | 2026-10-10 |
| Katedra Wawelska | Bilet ulgowy | **18,00 PLN** (kryteria nie podane wprost) | bilety-wawel.pl | 2026-10-10 |
| Katedra Wawelska | Zniżka Kraków Card | NIEPOTWIERDZONE (nie wymieniona na stronie sprzedaży) | bilety-wawel.pl / discovercracow.com | 2026-10-10 |
| Stadion Wisły Kraków | Istnienie oferty zwiedzania | NIEPOTWIERDZONE, nowy dowód: stara podstrona ma **przeterminowany certyfikat SSL** | archiwum.wisla.krakow.pl (błąd `certificate has expired`) | 2026-10-10 |
| Majdanek | Wstęp na teren i wystawy stałe | **POTWIERDZONE: bezpłatny** (cytat: "Wstęp do Muzeum (w tym na wszystkie wystawy) jest bezpłatny.") | majdanek.eu/zaplanuj-wizyte | 2026-10-10 |
| Arena Lublin | Dziecko/uczeń/senior | NIEPOTWIERDZONE — mosir.lublin.pl nie publikuje tabeli zniżek | mosir.lublin.pl/obiekty/arena-lublin | 2026-10-10 |
| Zamek Lubelski | Dziecko do 7 lat | **0,00 PLN (bezpłatnie)** | zamek-lublin.pl/wizyta/ceny-biletow/ | 2026-10-10 |
| Zamek Lubelski | Bilet ulgowy (uczeń/student/65+/nauczyciel/EKM/kombatant) | **30,00 PLN** | tamże | 2026-10-10 |
| Zamek Lubelski | Rodzic+dziecko do 16 lat / Karta Dużej Rodziny | **30,00 PLN/os.** (cena ulgowa) | tamże | 2026-10-10 |
| Zeche Zollverein | Ermäßigt (wariant 1h, wartość minimalna "ab") | **9,50 EUR** | zollverein.de/besuch-planen/eintrittspreise/ | 2026-10-10 |
| Zeche Zollverein | ⚠️ Premisa "6 wariantów" | **NIEPRAWDA** — operator ma 20+ nazwanych Führungen w 2 kategoriach czasowych (1h/2h), plus Rundfahrten i linię turystyczną. Rozbicie na 6 Attraction wymaga decyzji produktowej, nie tylko weryfikacji | zollverein.de + zollverein.ticketfritz.de | 2026-10-10 |
| Berlin WelcomeCard | Osobne ceny dziecko/student/senior | **POTWIERDZONE: NIE ISTNIEJĄ** — jedna cena karty, do 3 dzieci gratis z dorosłym | bvg.de/de/touristen/welcomecard | 2026-10-10 |
| RUHR.TOPCARD | Osobne ceny student/senior | **POTWIERDZONE: NIE ISTNIEJĄ** — tylko dorosły (70€)/dziecko (43€, bez przedziału wieku) | ruhrtopcard.de/card-kaufen | 2026-10-10 |
| Kraków Card / City Pass | Osobne ceny dziecko/student/senior/rodzina | **POTWIERDZONE: NIE ISTNIEJĄ** — jedna cena per wariant czasowy | discovercracow.com/tickets/ | 2026-10-10 |

## Ustalenia dla PR #42 (do przeniesienia przez sesję koordynującą)

| Pozycja | Ustalenie | Źródło | Data |
|---|---|---|---|
| KölnCard Einzelkarte 48h | **Rozbieżność z PR #42 ROZWIĄZANA**: koelntourismus.de I vrs-ticketshop.de dziś zgodnie podają **18,00 EUR** | koelntourismus.de/buchen/koelncard, vrs-ticketshop.de | 2026-10-10 |
| KölnCard Gruppenkarte 24h | Jak wyżej, zgodnie **19,00 EUR** na obu źródłach — oba warianty mogą dostać `price_verified: true` | tamże | 2026-10-10 |
| KölnCard — Kölner Dom (Domschatzkammer) | **POTWIERDZONE w oficjalnym Infoflyer (Stand 10/2025): 20%** off admission price (ausgenommen Sonderausstellungen) | koelntourismus.pixxio.media (Infoflyer PDF, link z koelntourismus.de/buchen/koelncard) | 2026-10-11 |
| KölnCard — Museum Ludwig | **POTWIERDZONE w oficjalnym Infoflyer: 20%** off admission price | tamże | 2026-10-11 |
| KölnCard — Wallraf-Richartz-Museum & Fondation Corboud | **POTWIERDZONE w oficjalnym Infoflyer: 20%** off admission price | tamże | 2026-10-11 |
| KölnCard — Kölner Zoo | **POTWIERDZONE w oficjalnym Infoflyer: 15%** dla dorosłych i dzieci (zniżkowe bilety TYLKO w kasie zoo, nie online) | tamże | 2026-10-11 |
| KölnCard — Schokoladenmuseum | **POTWIERDZONE: NIE jest partnerem** — nie występuje w żadnej sekcji oficjalnego Infoflyer (Museen/Sightseeing/Erleben/Shopping/Gastronomie); wcześniejszy lead z bloga "Loving Travel" (25%) się NIE potwierdza u źródła | tamże | 2026-10-11 |
| KölnCard — KölnTriangle | **POTWIERDZONE: NIE jest partnerem** — jak wyżej, nieobecny w całym Infoflyer | tamże | 2026-10-11 |
| KölnCard — inni partnerzy znalezieni przy tej okazji | Deutsches Sport & Olympia Museum 20%, Kölnisches Stadtmuseum 20%, MAKK 20%, Museum für Ostasiatische Kunst 20%, Museum Schnütgen 20%, EL-DE Haus/NS-Dok. 20%, Rautenstrauch-Joest-Museum 20%, Römisch-Germanisches Museum 20% (obecnie zamknięte na renowację), Käthe Kollwitz Museum 50%, Die Photographische Sammlung/SK Stiftung 50%, Farina Duftmuseum 10% | tamże | 2026-10-11 |
| Hamburg CARD — Elbphilharmonie Plaza | **POTWIERDZONE: NIE jest partnerem** — nie występuje w ogóle na liście rabatów | hamburg-tourism.de/buchen/hamburg-card/ | 2026-10-10 |
| Hamburg CARD — St. Michaelis (Michel) | **POTWIERDZONE jako partner**, ale dokładny % niepotwierdzony — strona podaje tylko kategoryjne "bis zu 25%" dla całej grupy "Sehenswürdigkeiten & Attraktionen" | tamże | 2026-10-10 |

## Co zostało poza zakresem tej sesji (budżet czasu)

- Pełna weryfikacja wiek/status dla **wszystkich** atrakcji w 10 miastach (54+ atrakcji w PR #42, 4 w PR #43) — nie wykonana, zbyt duży zakres na jedną sesję.
- Fernsehturm Berlin: widget biletowy JS nie oddał pełnej tabeli cen nawet w realnej przeglądarce.
- Arena Lublin: operator nie publikuje żadnej tabeli zniżek online.
- Transport miejski — poza zakresem tego wątku (weryfikuje równoległa sesja).
