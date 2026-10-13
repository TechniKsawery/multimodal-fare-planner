# Przegląd interfejsu Streamlit (`app.py`) pod kątem czytelności dla ucznia i studenta (PL ↔ DE)

Data przeglądu: 13 października 2026  
Środowisko: gałąź `gemini/ui-przeglad` (baza: `main`)  
Plik badany: `app.py` (oraz powiązane moduły pomocnicze widoku: `ui_helpers.py`, `fares/foreigner_eligibility.py`)  
Profil docelowy: **Uczeń szkoły średniej / student podróżujący na trasach Polska ↔ Niemcy** (wiek ~16–26 lat, często z legitymacją szkolną/studencką polską lub niemiecką, podróżujący samodzielnie lub z opiekunem, wrażliwy na koszty i niejednoznaczności taryfowe).

---

## 1. Status cen: oficjalna vs szacunek vs niepotwierdzona

### 1.1. Diagnoza obecnego stanu
* **Cena łączna w metryce (`st.metric` / `c2.metric`):**
  * Pokazuje jedynie `od X.XX PLN` lub `X.XX PLN` bez bezpośredniego wskaźnika poziomu pewności obok liczby.
  * Informacja o niepotwierdzeniu pojawia się dopiero poniżej w małym podpisie `st.caption` (l. 117–120).
  * Gdy cena jest w 100% oficjalna, brakuje jakiegokolwiek potwierdzenia (np. zielonej etykiety lub dopisku „oficjalna taryfa”). Uczeń nie wie, czy brak ostrzeżenia oznacza oficjalną cenę, czy niedopatrzenie systemu.
* **Ceny w tabeli odcinków (`st.dataframe`, kolumna `Cena / dystans`):**
  * Oficjalna taryfa ma po prostu postać `X.XX PLN (taryfa_km)` lub `(cennik)`. Dla studenta termin `(taryfa_km)` brzmi technicznie i nie mówi wprost: „cena gwarantowana / z oficjalnego cennika”.
  * Wartości szacowane lub zastępcze dopisują długie stringi: `— cena niepotwierdzona (wartość zastępcza, nie z cennika)` (z `routing/model.py:64`) lub `| szacunek: od ...`. W wąskiej kolumnie tabeli tekst ten jest ucinany lub zamazuje właściwą kwotę.
* **Karty miejskie i atrakcje:**
  * W tabeli City Card (l. 355) pojawia się jedynie dopisek `(niepotwierdzona)` przy cenie, bez wyjaśnienia, co to oznacza (np. brak danych za bieżący rok vs szacunek historyczny).
  * W kafelkach atrakcji (l. 387–389) pojawia się `(cena niepotwierdzona)`.

---

## 2. Zrozumiałość profilu ulg i kart (bez instrukcji)

### 2.1. Diagnoza obecnego stanu
* **Surowe identyfikatory w `Ulga PKP` (l. 514):**
  * Lista rozwijana wyświetla bezpośrednio klucze z pliku JSON: `student_do_26_lat_doktorant_do_35_lat`, `dzieci_mlodziez_szkolna_do_24_lat`, `brak` (z `fares/data/pkp_intercity.json`).
  * Brakuje czytelnych etykiet, np. „Student do 26 lat / Doktorant do 35 lat (51%)”. Uczeń liceum/technikum często nie wie, czy ma wybrać `dzieci_mlodziez_szkolna_do_24_lat`, a student szuka skrótu „51%”.
* **Rozbicie profilu atrakcji vs biletów transportu (l. 458–481 vs 513–601):**
  * Na samej górze (przed trasą i datą) znajduje się checkbox `Uczeń/student (legitymacja)` w l. 458, który – jak wyjaśnia `help` – wpływa **tylko** na atrakcje, a **nie** na bilety transportu.
  * Z kolei ulgi transportowe (PKP, ZTM, BVG, VRR) znajdują się wewnątrz formularza `search` (l. 514–601).
  * Młody użytkownik zaznacza checkbox na górze, myśląc, że ustawił sobie zniżkę studencką na całą podróż, po czym w formularzu widzi domyślnie `Ulga PKP: brak` i płaci 100% ceny za pociąg.
* **Kraj wydania legitymacji (l. 466–473):**
  * Pytanie `Kraj wydania legitymacji szkolnej/studenckiej` pojawia się w sekcji atrakcji, z pomocą mówiącą, że nie zmienia cen biletów, ale poniżej generuje ostrzeżenia o honorowaniu legitymacji w miastach PL/DE.
  * Student z Niemiec (np. podróżujący Berlin → Warszawa) nie wie, dlaczego legitymacja niemiecka nie działa na pociąg PKP ani MPK, dopóki nie kliknie „Szukaj” i nie przeczyta ostrzeżenia.
* **Taryfa miejska – podział na miasta i przejazdy bezpłatne (l. 542–595):**
  * Checkboxy miast mają domyślnie `value=wiek < 18` lub `value=wiek >= 70`. Dla 20-letniego studenta wszystkie checkboxy miast (Warszawa, Kraków, Poznań, Wrocław, Berlin) są domyślnie **odznaczone**, mimo że w Polsce przysługuje mu 50% ulgi na podstawie polskiej legitymacji studenckiej.
  * Z kolei uczeń 17-letni ma zaznaczone wszystkie miasta naraz, niezależnie od tego, czy podróż w ogóle przez te miasta przebiega.
  * Etykiety przejazdów bezpłatnych (np. `Warszawa: uczeń/senior 70+/niepełnosprawność znaczna`, l. 555) łączą w jednym polu skrajnie różne uprawnienia, wprowadzając chaos.

---

## 3. Jednoznaczność komunikatów taryfowych

### 3.1. Diagnoza obecnego stanu
* **„Cena niepotwierdzona” vs „Wartość zastępcza”:**
  * W `app.py:118-120` oraz `routing/model.py:64` komunikaty mieszają dwa pojęcia:
    1. *Cena niepotwierdzona* – taryfa istnieje, ale np. brak aktualnego cennika na dany rok lub brak pewności co do relacji.
    2. *Wartość zastępcza (fallback)* – brak jakiejkolwiek taryfy w bazie, wstawiono sztuczną stawkę ryczałtową (np. średnia cena za km).
  * Dla ucznia/studenta sformułowanie „wartość zastępcza, nie z cennika” brzmi jak błąd programu lub „cena zmyślona”. Wymaga jasnego podziału: „Oficjalny cennik”, „Szacunek orientacyjny”, „Brak taryfy (stawka przybliżona)”.
* **„Przedział cenowy” / „Szacunek”:**
  * W l. 144–147: `price += f" | szacunek: od {zakres['od']:.2f} ({zakres['od_zrodlo']}) do {zakres['do']:.2f} ({zakres['do_zrodlo']}) {zakres['waluta']}"`.
  * Prezentacja w jednej linii z ceną główną w tabeli: student widzi np. `70.00 PLN (taryfa_km) | szacunek: od 19.90 (super_sparpreis) do 39.90 (sparpreis) EUR`. Nie wiadomo, która kwota zostanie faktycznie pobrana przy zakupie.
* **Górna granica ceny w metryce (l. 108–112):**
  * Help: `Górna granica (PKP SPI poziom V albo cennik regularny): X.XX PLN`.
  * Student nie ma pojęcia, co to jest „PKP SPI poziom V” (Super Promo Intercity). Powinno to być nazwane prostym językiem biletów dynamicznych (tani bilet promocyjny vs cena bazowa w kasie).

---

## 4. Konkretne uwagi linia po linii w `app.py` z propozycjami zmian

Poniższa tabela i zestawienie zawierają precyzyjne wskazania linii w `app.py` oraz propozycje nowego tekstu/rozwiązania.

| Linia w `app.py` | Bieżący kod / tekst | Problem dla ucznia/studenta PL↔DE | Proponowany nowy tekst / rozwiązanie |
| :--- | :--- | :--- | :--- |
| **48** | `st.title("Multimodalna wyszukiwarka tras")` | Brak kontekstu relacji i przeznaczenia dla podróżnego transgranicznego. | `st.title("Multimodalna wyszukiwarka tras PL ↔ DE")`<br>`st.caption("Pociągi, autobusy, komunikacja miejska i loty z uwzględnieniem ulg uczniowskich i studenckich.")` |
| **108–112** | `c2.metric("Cena łączna", f"od {it.total_price_pln:.2f} PLN", help=f"Górna granica (PKP SPI poziom V albo cennik regularny): {it.total_price_pln_high:.2f} PLN")` | Termin „PKP SPI poziom V” jest całkowicie niezrozumiały dla młodego pasażera. | `c2.metric("Cena łączna", f"{it.total_price_pln:.2f} – {it.total_price_pln_high:.2f} PLN", help=f"Cena dynamiczna: od najtańszej puli promocyjnej (Super Promo) do ceny maksymalnej w taryfie standardowej ({it.total_price_pln_high:.2f} PLN).")` |
| **114** | `c2.metric("Cena łączna", f"{it.total_price_pln:.2f} PLN")` | Gdy cena jest zweryfikowana i stała, brak potwierdzenia, że to taryfa oficjalna. | `c2.metric("Cena łączna", f"{it.total_price_pln:.2f} PLN", help="Oficjalna cena wg stałych cenników przewoźników.")` |
| **117–120** | `st.caption("⚠️ Cena łączna niepotwierdzona: zawiera odcinki bez potwierdzonej taryfy (szacunek albo wartość zastępcza) — porównuj ostrożnie.")` | Niejednoznaczne wrzucenie szacunku i wartości zastępczej do jednego worka. | `st.warning("⚠️ Uwaga: Cena łączna ma charakter orientacyjny. Trasa zawiera odcinki bez oficjalnego cennika (zastosowano stawkę szacunkową). Sprawdź cenę przed zakupem u przewoźnika.")` |
| **128–130** | `price = f"{p.amount:.2f} {p.currency} ({p.price_type})"`<br>`if p.unverified_label:`<br>`    price += f" — {p.unverified_label}"` | W tabeli pojawia się techniczny kod `(taryfa_km)` oraz długi ciąg `— cena niepotwierdzona (wartość zastępcza, nie z cennika)`. | Formatowanie czytelne dla użytkownika:<br>• Jeśli oficjalna: `f"{p.amount:.2f} {p.currency} (oficjalna taryfa)"`<br>• Jeśli niepotwierdzona/zastępcza: `f"~{p.amount:.2f} {p.currency} (szacunek orientacyjny)"` |
| **142–147** | `price += f" \| szacunek: od {zakres['od']:.2f} ({zakres['od_zrodlo']}) do {zakres['do']:.2f} ({zakres['do_zrodlo']}) {zakres['waluta']}"` | Za dużo technicznych źródeł w jednej linijce tabeli, nieczytelne na telefonie/laptopie. | `price += f" [widełki: {zakres['od']:.0f}–{zakres['do']:.0f} {zakres['waluta']}]"` |
| **150–152** | `zrodlo_oferty = "DB Super Sparpreis Europa" if alt["zrodlo"] == "db" else "PKP Oferta Polska-Niemcy"`<br>`alternatywa = f"{alt['cena']:.2f} {alt['waluta']} ({zrodlo_oferty})"` | Dobre, ale warto dodać podpowiedź, że to bilet międzynarodowy, który kupuje się z wyprzedzeniem. | `alternatywa = f"{alt['cena']:.2f} {alt['waluta']} ({zrodlo_oferty} — bilet promocyjny)"` |
| **180–184** | `st.info(f"🟡 Prawie bezpieczna przesiadka w {stacja} — brakuje {shortfall:.0f} min do progu bezpieczeństwa ({w.gap_minutes:.0f} z wymaganych {w.minimum_required_minutes:.0f} min).")` | „Prawie bezpieczna” brzmi uspokajająco, podczas gdy na stacji węzłowej w Niemczech (DB) opóźnienia ICE/RE są częste i student może uciec ostatni pociąg. | `st.warning(f"⏱️ Krótki czas na przesiadkę: {stacja} ({w.gap_minutes:.0f} min, zalecane minimum: {w.minimum_required_minutes:.0f} min). Przy opóźnieniu pociągu istnieje ryzyko utraty połączenia.")` |
| **190–193** | `st.caption("💳 Ten wariant nie zawiera odcinka DB (kolej niemiecka) — BahnCard nie ma tu zastosowania.")` | Zrozumiałe, ale brakuje informacji o polskich odpowiednikach (Karta Dużej Rodziny / REGIOkarta). | `st.caption("💳 Odcinki kolejowe poza siecią Deutsche Bahn — zniżki BahnCard nie obowiązują.")` |
| **235–238** | `st.caption("Wybierz interesujące Cię kategorie miejsc (np. stadiony sportowe, zabytki) i sprawdź, czy dedykowana Karta Miejska (City Card) pozwoli Ci zaoszczędzić na wstępach i komunikacji.")` | Brak wskazania, że karta miejska często ma wersję ulgową dla studentów. | `st.caption("Wybierz miejsca, które chcesz odwiedzić w mieście docelowym. Sprawdzimy, czy Karta Miejska (City Card) z nielimitowaną komunikacją i zniżkami studenckimi opłaca się bardziej niż pojedyncze bilety.")` |
| **268–271** | `st.caption("Kilka osób korzysta z tego samego demo? Podaj swoją nazwę profilu, by zapisać zaznaczenia pod sobą i wrócić do nich później, bez nadpisywania cudzych wyborów.")` | Żargon deweloperski („z tego samego demo”). Uczeń nie wie, czym jest demo. | `st.caption("Zapisz swój plan zwiedzania: podaj imię lub nazwę, aby zachować wybrane miejsca i wrócić do nich później.")` |
| **317** | `st.subheader("💳 Analiza opłacalności Karty Miejskiej")` | Poprawne, ale warto podkreślić korzyść dla młodego podróżnika. | `st.subheader("💳 Czy Karta Miejska (City Card) Ci się opłaca?")` |
| **320–326** | `st.number_input(f"Szacowany wydatek na komunikację miejską bez karty ({all_city_attrs[0].currency})", ... help="Jeśli karta miejska zawiera nielimitowany transport, ten koszt odpada i staje się Twoją oszczędnością.")` | Uczeń/student PL przyjeżdżający do Niemiec nie wie, ile wyda na transport bez karty (np. bilet dobowy BVG/VRR). | Dodać podpowiedź z typową stawką dobową: `st.number_input(..., help="Wpisz, ile planujesz wydać na zwykłe bilety tramwajowe/metra (np. bilet 24h w Berlinie AB to ok. 9,90 EUR, bilet ulgowy ok. 6,50 EUR). Jeśli karta miejska ma darmowy transport, ten koszt odpada.")` |
| **354–355** | `"Cena karty": f"{ev.card_price:.2f} {ev.currency}" + ("" if ev.variant.price_verified else " (niepotwierdzona)")` | `(niepotwierdzona)` bez wyjaśnienia. | `"Cena karty": f"{ev.card_price:.2f} {ev.currency}" + ("" if ev.variant.price_verified else " (cena szacunkowa)")` |
| **380–392** | `price_text = f"{price_val:.2f} {attr.currency}" if price_val > 0 else "Wstęp bezpłatny"`<br>`... price_text += " (cena niepotwierdzona)"` | Kumulacja nawiasów i niejednoznaczność: `od 12.00 EUR (bilet ulgowy) (cena niepotwierdzona) — cena od...`. | Uproszczenie etykiet: `12.00 EUR (ulga studencka, cennik orientacyjny)`. |
| **433–443** | `wiek = st.number_input("Wiek pasażera", ... help="Używany tylko do PODPOWIEDZI zniżek zależnych od wieku (VRR Kindertarif 6-14 lat, ZTM Lublin ulgowy)...")` | Student (np. 21 lat) czyta, że wiek to tylko podpowiedź, ale w formularzu transportu nie ma ogólnego przełącznika „jestem studentem”. | `wiek = st.number_input("Wiek pasażera", min_value=0, max_value=120, value=21, step=1, help="Wiek pozwala automatycznie dobrać taryfy młodzieżowe (np. taryfa dziecięca 6–14 lat w Niemczech). Ulgi studenckie i szkolne zaznaczysz poniżej.")` |
| **444–456** | `obywatelstwo = st.selectbox("Obywatelstwo", [None, "PL", "UE", "poza_UE"], ... help="Nie zmienia ceny — po wyszukaniu pokażemy ostrzeżenia...")` | Etykieta `nie podano` sugeruje brak wpływu, a student z Ukrainy lub Niemiec nie wie, że to kluczowe dla PKP. | `format_func: {None: "Wybierz obywatelstwo (wymóg ulg ustawowych)", "PL": "Polska (obywatel RP)", "UE": "Inny kraj Unii Europejskiej / EOG", "poza_UE": "Kraj spoza UE (np. Ukraina, Wielka Brytania)"}` |
| **458–461** | `uczen_student = c_attr_profile1.checkbox("Uczeń/student (legitymacja)", help="Wpływa na cenę ATRAKCJI (nie biletów transportu)...")` | **Krytyczna pułapka UX:** użytkownik myśli, że zaznacza ulgę na całą podróż! | Zmiana etykiety na: `uczen_student = c_attr_profile1.checkbox("Zniżka studencka/szkolna na wstępy do muzeów i atrakcji", help="Dotyczy wyłącznie biletów do muzeów, stadionów i obiektów turystycznych. Zniżki na pociągi i komunikację miejską wybierz poniżej w sekcji biletowej.")` |
| **466–473** | `_kraj_legitymacji = st.selectbox("Kraj wydania legitymacji szkolnej/studenckiej", ["Nie podaję", "Polska", "Niemcy", "Inny kraj"], ...)` | Opcja `Nie podaję` utrudnia kalkulację. Student z polską legitymacją jadący do Berlina lub niemiecką jadący do Warszawy musi wiedzieć, po co to pole istnieje. | Etykieta: `"Gdzie została wydana Twoja legitymacja?"`<br>Opcje: `["Wybierz kraj wydania", "Polska (legitymacja szkolna / mLegitymacja / studencka)", "Niemcy (Schülerausweis / Studierendenausweis)", "Inny kraj (np. ISIC / Euro26)"]` |
| **504–512** | `bagaz_rejestrowany = st.checkbox("Bagaż rejestrowany (loty)", value=True, help="Zaznaczone: cena lotu zawiera bagaż rejestrowany, a po lądowaniu liczymy 90 min do kolei...")` | Studenci rzadko dokupują drogi bagaż rejestrowany (20 kg), częściej podróżują z plecakiem/kabinówką. Domyślny `value=True` zawyża cenę lotu o 150–300 zł. | Zmienić domyślnie na `value=False` (podróż studencka z bagażem podręcznym) lub dać wybór radiowy: `Bagaż podręczny (w cenie / taniej)` vs `Duży bagaż rejestrowany (+opłata)`. |
| **514** | `pkp = c1.selectbox("Ulga PKP", PKP_ULGI)` | Wyświetla surowe klucze z bazy: `student_do_26_lat_doktorant_do_35_lat`, `dzieci_mlodziez_szkolna_do_24_lat`. Totalnie nieczytelne! | Zastosować `format_func` mapujący klucze na czytelny język:<br>• `student_do_26_lat_doktorant_do_35_lat` → `Student do 26 lat (ulga 51%)`<br>• `dzieci_mlodziez_szkolna_do_24_lat` → `Uczeń szkoły w Polsce do 24 lat (ulga 37%)`<br>• `brak` → `Bilet normalny (brak ulgi PKP)` |
| **515** | `bc = c2.selectbox("BahnCard", ["brak", "25", "50", "100"])` | Niemiecki uczeń/student często posiada młodzieżową kartę: *My BahnCard 25* lub *My BahnCard 50*. Polski uczeń nie wie, co oznacza liczba 25/50. | Zastosować `format_func`:<br>• `"brak"` → `"Brak karty DB"`<br>• `"25"` → `"BahnCard 25 / My BahnCard 25 (zniżka 25%)"`<br>• `"50"` → `"BahnCard 50 / My BahnCard 50 (zniżka 50%)"` |
| **517–522** | `ztm_ulgowy = c3.checkbox("Bilet ulgowy ZTM Lublin", value=wiek < 18, help="Podpowiedź wg wieku (<18 lat)...")` | Dlaczego Lublin jest wyróżniony w głównej linii obok taryfy VRR dla Niemiec? Dziwna asymetria interfejsu. | Zgrupować ulgi miejskie w logiczne zakładki lub sekcje: `Komunikacja miejska w Polsce (ZTM/MPK)` oraz `Komunikacja miejska w Niemczech (Verkehrsverbünde)`. |
| **523–527** | `vrr_dziecko = c4.checkbox("Taryfa dziecięca VRR (Kindertarif)", value=6 <= wiek <= 14, ...)` | Uczeń szkoły średniej (16–18 lat) myśli, że to ulga dla niego, a w Niemczech Kindertarif kończy się na 14. roku życia! | `checkbox("Taryfa dziecięca VRR / Zagłębie Ruhry (Kindertarif, wyłącznie 6–14 lat)")` + dopisek: `W Niemczech uczniowie 15+ i studenci bez lokalnego biletu semestralnego płacą 100% ceny za bilet jednorazowy.` |
| **530–536** | `child_with_guardian = st.checkbox("Dziecko (6-14 lat) podróżuje z opiekunem (15+)", ...)` | Znakomita funkcja taryfowa DB, ale powinna pojawiać się tylko wtedy, gdy pasażer ma poniżej 15 lat. | Utrzymać warunek `if wiek < 15:`, ale uprościć tekst: `"Podróż z rodzicem/opiekunem (darmowy przejazd w kolejach niemieckich DB)"`. |
| **537–541** | `st.caption("Taryfa dziecięca (Kindertarif, 6-14 lat) w innych miastach niemieckich")`<br>`hvv_dziecko = k1.checkbox("Hamburg (HVV)", ...)` | J.w. – wyraźne zaznaczenie granicy wieku 14 lat, by 17-letni uczeń nie zaznaczał jej omyłkowo. | `st.caption("Niemcy — taryfy dziecięce (6–14 lat; uwaga: od 15 lat bilet normalny)")` |
| **542–548** | `st.caption("Bilety ulgowe w innych miastach (50% — zaznacz, jeśli dotyczy)")`<br>`u1...u5: Warszawa, Kraków, Poznań, Wrocław, Berlin` | W Polsce student (do 26 lat) ma prawo do ulgi 50% w każdym z tych miast, ale checkbox ma `value=wiek < 18` (czyli dla studenta 21 lat jest odznaczony!). Ponadto w Berlinie (BVG) NIE MA ulgi studenckiej 50% na pojedyncze bilety. | Rozdzielić:<br>1. `Polska (50% — uczniowie i studenci z ważną legitymacją)`: domyślnie zaznaczone dla uczniów/studentów.<br>2. `Berlin (BVG Regeltarif / Ermäßigungstarif)`: dodać ostrzeżenie w etykiecie: `Berlin (tylko dzieci 6–14 lat; brak ulgi studenckiej na bilet 1-przejazdowy)`. |
| **549–595** | `st.caption("Przejazdy bezpłatne (100%...)")`<br>`Warszawa: uczeń/senior 70+/niepełnosprawność znaczna`<br>`Kraków: uczeń/senior 70+...`<br>`Lublin: uczeń podstawówki` | Prawdziwy gąszcz przepisów i skomplikowanych nazw prawnych. Student gubi się w symbolach medycznych (04-O/05-R). | Przenieść do rozwijanego panelu `st.expander("Specjalne uprawnienia do przejazdów bezpłatnych (100% — Karta Ucznia, seniorzy, orzeczenia)")` i rozdzielić uprawnienia szkolne od medycznych/senioralnych. |
| **589–595** | `bvg_berlin_schwerbehindert = b6.checkbox("Berlin: Schwerbehindertenausweis + Wertmarke", ...)` | Niemiecka nazwa prawna bez polskiego tłumaczenia. Uczeń nie wie, co to znaczy. | `checkbox("Berlin: Niemiecka legitymacja osoby o znacznym stopniu niepełnosprawności (Schwerbehindertenausweis + Wertmarke)")` |
| **716** | `pokaz_wiecej = st.checkbox(f"Pokaż więcej ({len(more_keys)})", value=False)` | Nie wiadomo, co to są te „więcej” (inne kryteria rekomendacji, warianty alternatywne?). | `pokaz_wiecej = st.checkbox(f"Pokaż dodatkowe kategorie rekomendacji ({len(more_keys)})", value=False, help="Wyświetla dodatkowe filtry, np. najmniej przesiadek, opcje z bezpiecznym zapasem czasu itp.")` |
| **731–733** | `st.caption(f"Ta sama trasa co „{RECOMMENDATION_LABELS[owner_key]}” — to nie duplikat, po prostu ten wariant wygrywa na obu osiach naraz.")` | Dobry komunikat, ale język warto dostosować do młodego użytkownika. | `st.info(f"💡 Ta trasa jest identyczna jak w zakładce „{RECOMMENDATION_LABELS[owner_key]}” — okazała się jednocześnie najkorzystniejsza pod oboma względami.")` |
| **734–737** | `st.info("Żaden wariant nie był w pełni bezpieczny — to najmniej ryzykowny z dostępnych.")` | Brzmi groźnie. Warto doprecyzować, że chodzi o czas na przesiadkę, a nie zagrożenie fizyczne. | `st.warning("⚠️ Uwaga na przesiadki: Żadne z dostępnych połączeń nie ma pełnego zapasu czasowego. Ten wariant wybrano jako najmniej ryzykowny pod kątem spóźnienia.")` |
| **762–772** | `f"{it.variant_name} — {it.total_duration_min / 60:.1f} h, ... (cena niepotwierdzona), przesiadek: {it.num_transfers} 🟡 prawie bezpieczna"` | W nagłówku expandera skumulowane są kody, brak wyraźnego rozbicia. | Czytelny nagłówek z piktogramami:<br>`f"🚆 {it.variant_name} | ⏱️ {it.total_duration_min / 60:.1f} godz. | 💰 {it.total_price_pln:.0f} PLN | 🔄 Przesiadki: {it.num_transfers}"` |

---

## 5. Inwentaryzacja tekstów do tłumaczenia wielojęzycznego (PL ➔ EN / DE / ES)

Aplikacja jest narzędziem transgranicznym, z którego bezpośrednio korzystać będą studenci niemieckojęzyczni (Niemcy, Austria), polskojęzyczni oraz międzynarodowi z programu Erasmus+ (używający angielskiego lub hiszpańskiego). 

Wszystkie teksty interfejsu `app.py` zostały zinwentaryzowane i podzielone na logiczne kategorie słownikowe:

### Kategoria A: Nagłówki, nawigacja i układ główny
1. `"Multimodalna wyszukiwarka tras"`  
   * **EN:** `Multimodal Route Planner`  
   * **DE:** `Multimodale Routensuche`  
   * **ES:** `Buscador de rutas multimodal`
2. `"Skąd i dokąd"`  
   * **EN:** `Origin & Destination`  
   * **DE:** `Start und Ziel`  
   * **ES:** `Origen y destino`
3. `"Skąd (adres)"` / `"Dokąd (adres)"`  
   * **EN:** `From (address)` / `To (address)`  
   * **DE:** `Von (Adresse)` / `Nach (Adresse)`  
   * **ES:** `Desde (dirección)` / `Hasta (dirección)`
4. `"Data"` / `"Najwcześniejsza godzina wyjazdu"`  
   * **EN:** `Departure date` / `Earliest departure time`  
   * **DE:** `Reisedatum` / `Früheste Abfahrtszeit`  
   * **ES:** `Fecha de viaje` / `Hora de salida más temprana`
5. `"Szukaj"` / `"Szukam połączeń..."`  
   * **EN:** `Search` / `Searching for connections...`  
   * **DE:** `Suchen` / `Verbindungen werden gesucht...`  
   * **ES:** `Buscar` / `Buscando conexiones...`
6. `"Rekomendacje"` / `"Wszystkie warianty"` / `"Pominięte warianty"`  
   * **EN:** `Recommended routes` / `All route options` / `Skipped options`  
   * **DE:** `Empfehlungen` / `Alle Varianten` / `Übersprungene Optionen`  
   * **ES:** `Recomendaciones` / `Todas las opciones` / `Opciones descartadas`

### Kategoria B: Metryki podróży i statusy taryfowe
7. `"Czas podróży"` / `"Cena łączna"` / `"Przesiadki"`  
   * **EN:** `Travel time` / `Total price` / `Transfers`  
   * **DE:** `Reisezeit` / `Gesamtpreis` / `Umstiege`  
   * **ES:** `Tiempo de viaje` / `Precio total` / `Transbordos`
8. `"Cena łączna niepotwierdzona: zawiera odcinki bez potwierdzonej taryfy (szacunek albo wartość zastępcza) — porównuj ostrożnie."`  
   * **EN:** `⚠️ Total price unverified: includes legs without confirmed fare data (estimate or fallback value) — compare with caution.`  
   * **DE:** `⚠️ Gesamtpreis unbestätigt: enthält Abschnitte ohne verbindliche Tarifdaten (Schätzwert oder Richtpreis) – bitte vorsichtig vergleichen.`  
   * **ES:** `⚠️ Precio total no confirmado: incluye tramos sin tarifa oficial (estimación o tarifa de referencia) — compare con precaución.`
9. `"cena niepotwierdzona"` / `"wartość zastępcza"` / `"oficjalna taryfa"` / `"szacunek"`  
   * **EN:** `unverified price` / `fallback estimate` / `official fare` / `price estimate`  
   * **DE:** `unbestätigter Preis` / `Richtwert` / `offizieller Tarif` / `Preisschätzung`  
   * **ES:** `precio no verificado` / `valor de referencia` / `tarifa oficial` / `estimación`
10. `"Przesiadki: bezpieczne (wg przyjętych minimów)"`  
    * **EN:** `Transfers: safe (meets minimum transfer buffer)`  
    * **DE:** `Umstiege: gesichert (nach empfohlenen Mindestzeiten)`  
    * **ES:** `Transbordos: seguros (según los tiempos mínimos recomendados)`
11. `"Ryzykowna przesiadka"` / `"Prawie bezpieczna przesiadka"`  
    * **EN:** `Risky transfer` / `Tight transfer`  
    * **DE:** `Knapper Umstieg` / `Kritischer Umstieg`  
    * **ES:** `Transbordo ajustado` / `Transbordo con poco margen`

### Kategoria C: Profile pasażera, ulgi i legitymacje
12. `"Wiek pasażera"` / `"Obywatelstwo"`  
    * **EN:** `Passenger age` / `Citizenship`  
    * **DE:** `Alter des Fahrgasts` / `Staatsangehörigkeit`  
    * **ES:** `Edad del pasajero` / `Nacionalidad`
13. `"Uczeń/student (legitymacja)"`  
    * **EN:** `School pupil / University student (valid ID)`  
    * **DE:** `Schüler / Student (mit Ausweis)`  
    * **ES:** `Estudiante escolar / universitario (con carné)`
14. `"Kraj wydania legitymacji szkolnej/studenckiej"`  
    * **EN:** `Country of student ID issuance`  
    * **DE:** `Ausstellungsland des Schüler-/Studentenausweises`  
    * **ES:** `País de expedición del carné de estudiante`
15. `"Ulga PKP"` (wraz z nazwami ulg):  
    * *student do 26 lat:* **EN:** `Polish Student up to 26 (51% discount)` | **DE:** `Polnischer Student bis 26 J. (51 % Ermäßigung)` | **ES:** `Estudiante en Polonia hasta 26 años (51% de descuento)`  
    * *dzieci i młodzież szkolna do 24 lat:* **EN:** `School student up to 24 (37% discount)` | **DE:** `Schüler bis 24 J. (37 % Ermäßigung)` | **ES:** `Estudiante escolar hasta 24 años (37% de descuento)`
16. `"BahnCard"`:  
    * **EN:** `German Rail BahnCard discount`  
    * **DE:** `Deutsche Bahn BahnCard`  
    * **ES:** `Descuento BahnCard de tren alemán`
17. `"Taryfa dziecięca (Kindertarif, 6-14 lat)"`  
    * **EN:** `Child fare (Kindertarif, ages 6–14 only)`  
    * **DE:** `Kindertarif (nur 6–14 Jahre)`  
    * **ES:** `Tarifa infantil (Kindertarif, solo de 6 a 14 años)`
18. `"Bagaż rejestrowany (loty)"`  
    * **EN:** `Checked baggage (flights)`  
    * **DE:** `Aufgabegepäck (Flüge)`  
    * **ES:** `Equipaje facturado (vuelos)`

### Kategoria D: Atrakcje, zniżki turystyczne i Karty Miejskie (City Cards)
19. `"Miejsca warte odwiedzenia i zniżki: {miasto}"`  
    * **EN:** `Places of interest & student discounts: {city}`  
    * **DE:** `Sehenswürdigkeiten & Rabatte: {city}`  
    * **ES:** `Lugares de interés y descuentos: {city}`
20. `"Analiza opłacalności Karty Miejskiej"`  
    * **EN:** `City Card Cost-Benefit Analysis`  
    * **DE:** `City-Card Wirtschaftlichkeitsanalyse`  
    * **ES:** `Análisis de rentabilidad de la City Card`
21. `"Szacowany wydatek na komunikację miejską bez karty"`  
    * **EN:** `Estimated public transit spend without City Card`  
    * **DE:** `Geschätzte Nahverkehrskosten ohne City-Card`  
    * **ES:** `Gasto estimado en transporte público sin la tarjeta`
22. `"Wstęp bezpłatny"` / `"Zniżka z kartą"`  
    * **EN:** `Free admission` / `Discount with card`  
    * **DE:** `Freier Eintritt` / `Rabatt mit Karte`  
    * **ES:** `Entrada gratuita` / `Descuento con tarjeta`
23. `"Zapisz profil"` / `"Wczytaj profil"`  
    * **EN:** `Save profile` / `Load profile`  
    * **DE:** `Profil speichern` / `Profil laden`  
    * **ES:** `Guardar perfil` / `Cargar perfil`

---

## 6. Rekomendacje architektoniczne dla zespołu (bez modyfikacji logiki)

1. **Wdrożenie słownika tłumaczeń (i18n):**
   * Utworzenie pliku `i18n.py` lub słowników JSON `locales/{pl,de,en,es}.json`.
   * Zamiana surowych ciągów tekstowych w `app.py` na funkcję pomocniczą `t("string_key", lang)`.
2. **Rozdzielenie kontekstu ulg biletowych od ulg turystycznych:**
   * Umieszczenie wyboru profilu studenta/ucznia w jednym wspólnym panelu preferencji na samej górze („Twój profil podróżnego”), z którego automatycznie propagowane są zniżki:
     * do biletów kolejowych PKP (51% jeśli student PL),
     * do biletów miejskich (ZTM/MPK ulgowy 50%),
     * do wstępów na atrakcje (bilet studencki/szkolny).
3. **Standaryzacja plakietek taryfowych w UI:**
   * Zamiast nieczytelnych dopisków w kolumnie ceny, zastosowanie standaryzowanych piktogramów statusu w Streamlit:
     * 🟢 `Oficjalna taryfa`
     * 🟡 `Szacunek orientacyjny`
     * ⚪ `Wartość przybliżona (brak taryfy)`
