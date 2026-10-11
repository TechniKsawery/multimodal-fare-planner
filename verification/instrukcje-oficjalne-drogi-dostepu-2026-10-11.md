# Oficjalne drogi dostępu do cen i danych: instrukcja dla Ksaviego (2026-10-11)

Zasada: **konta zakładasz i wiadomości wysyłasz Ty**. Nic tu nie robi się samo. Każdy punkt ma
URL i datę sprawdzenia (2026-10-11, WebFetch). Co NIE zostało potwierdzone u źródła, jest oznaczone
**[niepotwierdzone]**. Tam, gdzie oficjalnej drogi nie ma (ceny DB, PKP IC), kod ma OPCJONALNE
nieoficjalne źródło (patrz `fares/README.md`), a ten dokument opisuje tylko, jak zapytać o zgodę.

Kolejność wg wartości: 1) Tiqets (najłatwiejsze, darmowe), 2) DB (zgoda), 3) ZTP Kraków (licencja),
4) Viator, 5) GetYourGuide.

---

## 1. Tiqets Distributor API (atrakcje: ceny i dostępność)

- **Wejście:** https://www.tiqets.com/partner-program/sign-up-form (opis: https://www.tiqets.com/pl/program-partnerski/program-api/)
- **Co kliknąć:** wypełnij formularz rejestracji partnera (darmowy). Po rejestracji dostajesz dostęp do Affiliate Portal oraz API treści i dostępności (ceny w czasie rzeczywistym).
- **Co podać:** dane firmy/projektu, adres strony, opis modelu ("porównywarka transportu z cenami atrakcji, linkujemy do Tiqets"). Nie deklaruj sprzedaży biletów, której nie robimy.
- **Wymagania:** zwykle potrzebny developer do integracji; **Booking API** (sprzedaż) tylko po ocenie wyników, orientacyjnie min. ok. 200 zamówień/mc. Do samych cen i linków to niepotrzebne.
- **Dokumentacja API:** https://portals.tiqets.com/distributorapi/docs (link z ich strony; adres portalu API sama strona zaznacza jako do potwierdzenia z Tiqets).
- **Kontakt:** https://tiqets-affiliates.kustomer.support/contact/partner-contact-us-HyPGbGDe2
- **Uwaga produktowa:** cena u Tiqets to cena resellera, nie bramkowa. W wyszukiwarce musi być opisana jako "cena w Tiqets", obok `official_url` operatora.

Szkic (EN), do formularza kontaktowego po rejestracji:
> Hello, we are building a multimodal trip planner (rail/bus/flights between Poland and Germany) that shows travellers what a trip really costs, including attractions at the destination. We would like to use the Distributor API (content, availability and prices) for about 80 attractions in Berlin, Kraków, Warsaw, Hamburg, Munich and Cologne, and link users to Tiqets for booking. We do not need the Booking API at this stage. Could you confirm which of these attractions are available through the API, and whether showing prices alongside the operator's official price is permitted? Thank you, [Twoje imię i nazwisko / your name]

---

## 2. Deutsche Bahn: ceny połączeń (zgoda na dostęp)

Stan faktyczny: katalog DB API Marketplace (https://developers.deutschebahn.com/db-api-marketplace/apis/product) ma m.in. OpenStation, RIS::Transports, Shared Mobility GBFS, **bez cen biletów**. Biblioteka db-vendo-client, której używa nasze opcjonalne źródło, sama pisze: "permission is necessary to use this library with the DB APIs" (https://github.com/public-transport/db-vendo-client).

- **Krok 1, sprawdź warunki:** https://developers.deutschebahn.com/db-api-marketplace/apis/nutzungsbedingungen
- **Krok 2, załóż konto (opcjonalnie, do innych API DB):** https://developers.deutschebahn.com/db-api-marketplace/apis/user/login (rejestracja z tej strony; kroki startowe: https://developers.deutschebahn.com/db-api-marketplace/apis/start)
- **Krok 3, napisz z prośbą o zgodę/dostęp do cen:** formularz https://developers.deutschebahn.com/db-api-marketplace/apis/contact (strona nie podaje, czy to właściwy kanał do takiej prośby, **[niepotwierdzone]**; jeśli odeśle Cię gdzie indziej, użyj podanego adresu).
- **Czego się spodziewać:** brak publicznej ścieżki do cen; odpowiedź może brzmieć "nie". Dopóki jej nie ma, źródło nieoficjalne zostaje wyłączone domyślnie i oznaczone jako szacunek.

Szkic (DE):
> Sehr geehrte Damen und Herren,
> wir entwickeln einen Multimodal-Reiseplaner (Bahn, Bus, Flug, Polen–Deutschland), der Reisenden zeigt, was eine Reise tatsächlich kostet. Für Bahnverbindungen in Deutschland würden wir gern Preisinformationen (z. B. Sparpreis/Flexpreis je Verbindung und Datum) anzeigen und auf bahn.de zum Kauf verlinken. Wir haben in den API-Marketplace-Katalogen keine API mit Preisen gefunden. Gibt es einen offiziellen Weg (API, Datenpartnerschaft oder schriftliche Erlaubnis), Preisinformationen für diesen Zweck abzurufen? Wir würden Abfragen stark begrenzen und Ergebnisse zwischenspeichern. Vielen Dank und freundliche Grüße, [Twoje imię i nazwisko / your name]

Szkic (EN):
> Hello, we build a multimodal trip planner (rail, bus, flights, Poland–Germany) that shows what a journey really costs. We would like to display DB fares per connection and date and link to bahn.de for purchase. We found no price API in the API Marketplace. Is there an official way (API, data partnership or written permission) to retrieve fare information for this use? We would rate-limit and cache requests. Thank you, [Twoje imię i nazwisko / your name]

---

## 3. ZTP Kraków: licencja rozkładów GTFS

- **Stan:** https://gtfs.ztp.krakow.pl/ nie podaje licencji ani kontaktu (2026-10-11); Mobility Database wskazuje tylko stronę https://ztp.krakow.pl (https://mobilitydatabase.org/feeds/gtfs/mdb-1326). Pliki: `GTFS_KRK_A/M/T.zip`; znaczenie liter A/M/T **[niepotwierdzone]**.
- **Co zrobić:** sprawdź regulamin/informacje o danych otwartych na https://ztp.krakow.pl i w BIP (https://bip.krakow.pl/uslugi/ZTP-1); jeśli licencji brak, napisz do ZTP (adres kontaktowy weź ze strony ztp.krakow.pl, nie zgaduję go).
- **Do czasu odpowiedzi:** feed Krakowa zostaje tylko testowy.

Szkic (PL):
> Dzień dobry, budujemy wyszukiwarkę połączeń łączącą transport międzymiastowy i lokalny. Chcielibyśmy wykorzystać publikowane przez ZTP dane GTFS (https://gtfs.ztp.krakow.pl/) do wyznaczania tras w Krakowie. Na stronie nie znaleźliśmy licencji. Czy dane są udostępnione na wolnej licencji (np. CC BY 4.0) i jakiej atrybucji wymagacie? Czy dopuszczalne jest użycie w usłudze, która w przyszłości może być komercyjna? Pozdrawiam, [Twoje imię i nazwisko / your name]

---

## 4. Viator Partner API

- **Stan:** dokumentacja https://docs.viator.com/partner-api/ opisuje dwa typy: **affiliate** (pełna treść, sprzedaż tylko na viator.com, prowizja z linków) i **merchant** (wymaga infrastruktury płatności, nie dla nas). Dokumentacja nie podaje URL formularza ani wymagań dla affiliate; wskazuje "Partner Resource Center" i "Partner Help Center" bez linków (**[niepotwierdzone]**).
- **Co zrobić:** wejdź na docs.viator.com/partner-api, znajdź link "Partner Resource Center" i zgłoś się jako **affiliate**. Pytaj o: dostęp do cen w API dla affiliate, zasady wyświetlania cen.

Szkic (EN):
> Hello, we operate a travel planner comparing total trip costs. We would like to apply as an affiliate partner for the Partner API (content, availability, prices) to show indicative activity prices for Berlin, Kraków, Warsaw, Hamburg, Munich and Cologne and link to viator.com. Could you confirm that affiliate access includes pricing data and what the display rules are? Thank you, [Twoje imię i nazwisko / your name]

---

## 5. GetYourGuide

- **Stan:** `integrator.getyourguide.com` i program "Connectivity Partner" są dla **dostawców systemów rezerwacji** (https://www.getyourguide.supply/connectivity/connectivity-partners), nie dla nas. Spec API: https://github.com/getyourguide/partner-api-spec. Strona dla partnerów afiliacyjnych (https://partner.getyourguide.com/) wymaga JavaScriptu i **nie dała się odczytać**: warunki i dostęp do cen **[niepotwierdzone]**.
- **Co zrobić:** otwórz https://partner.getyourguide.com/ w przeglądarce, sprawdź program afiliacyjny/API i zgłoś się. Jeśli API z cenami nie jest dostępne dla affiliate, zostajemy przy linkach bez cen z GYG.

Szkic (EN):
> Hello, we run a multimodal travel planner and would like to join your partner programme. Is there API access (availability and prices) for affiliate/distribution partners, and under what conditions? We would link users to GetYourGuide for booking. Thank you, [Twoje imię i nazwisko / your name]

---

## Co dalej po Twoich odpowiedziach

- Tiqets/Viator zgoda: dopiszemy moduł atrakcji z etykietą "cena u resellera".
- DB zgoda: przełączymy źródło z nieoficjalnego na oficjalne i zdejmiemy etykietę "nieoficjalne".
- ZTP odpowiedź: włączamy feed Krakowa na stałe lub usuwamy.
