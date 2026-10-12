# Koleje Małopolskie – Tabela nr 1 TP-KMŁ: źródła i status, 2026-10-12

Wszystkie kwoty poniżej: **wg Gemini, niezweryfikowane niezależnie**. Zgodnie z CONTRIBUTING.md
(„Dane z zewnętrznych AI”) kod ustawia dla nich `price_verified=False` i `PriceType.ESTIMATE` do
czasu drugiego niezależnego źródła. Raport: `research/km-malopolskie.md` (gałąź
`gemini/km-malopolskie`, sprawdzenie 2026-10-12). Domena `kolejemalopolskie.com.pl` jest z sesji
chmurowej zablokowana (egress), więc żadnego z poniższych URL-i nie otwarto. Tabelę przepisano z
raportu skryptem (30 pasm, bez ręcznego wpisywania) i sprawdzono wewnętrznie (test
`tests/test_koleje_malopolskie_tariff.py`: pasma rosnące, granice zgodne z napisami z raportu).

## Co jest wdrożone

| Pozycja | Wartość | Źródło (wg raportu) | Data raportu |
|---|---|---|---|
| Tabela nr 1, bilet jednorazowy wg taryfy normalnej, klasa 2, pociąg osobowy, cena z 8% VAT | 30 pasm: 8,00 zł (do 5 km) … 62,40 zł (701-800 km); 91-100 km = 31,30 zł | https://kolejemalopolskie.com.pl/brepo/panel_repo/2026/03/19/cpt2dx/taryfa-przewozowa-kml-zm8-ost.pdf (85 stron, Tabela nr 1 na s. 66) | 2026-10-12 |
| Dokument | „Załącznik nr 2 do Uchwały Zarządu „Koleje Małopolskie” sp. z o.o. nr 43/2026 z dnia 17 marca 2026 r.” (tekst jednolity po zmianie nr 8) | strona: https://kolejemalopolskie.com.pl/pl/dla-pasazera/oferty-taryfy-przepisy/regulamin-przewozu-i-taryfa-przewozowa | 2026-10-12 |
| Cytat tytułu tabeli | „Opłaty za bilety jednorazowe wg taryfy normalnej, klasa 2 pociąg osobowy”, „cena (zawiera 8% VAT)” | j.w. | 2026-10-12 |
| Zakres | „Nie obowiązuje do/z Kraków Lotnisko” | j.w. | 2026-10-12 |

Raport odnotowuje zgodność z wcześniejszym raportem Gemini dla do 5 km = 8,00 zł i 91-100 km =
31,30 zł. To nadal nie jest niezależne źródło (oba raporty pochodzą z tego samego narzędzia).

## Braki i niepewności (nic nie uzupełniono „z głowy”)

- **Data wejścia w życie: BRAK.** Raport jej nie odczytał z okładki dokumentu. W danych jest to
  `"obowiazuje_od": null` z opisem „brak … (NIEZWERYFIKOWANE)”, a w `notes` ceny: „data wejścia w
  życie: brak w raporcie, niezweryfikowana”. Znana jest tylko data uchwały (17.03.2026) oraz
  ścieżka URL PDF zawierająca `2026/03/19`; żadna z nich nie jest potwierdzoną datą obowiązywania.
- **Cena 28,50 zł Kraków Główny - Jasło nie pasuje do Tabeli nr 1.** Ten sam raport (sekcja 3)
  cytuje z rozkładu K71 (PDF `k71-zrj-30-viii-24-x-26.pdf`): „Kraków Główny - Jasło: bilet
  jednorazowy: 28,50 zł”. Kwoty 28,50 zł nie ma w Tabeli nr 1 (sąsiednie pasma: 74-80 km =
  27,60 zł, 81-90 km = 29,50 zł). Odległość taryfowa Kraków Główny - Jasło nie jest w raporcie;
  gdyby przekraczała 100 km, Tabela nr 1 dałaby co najmniej 35,30 zł. Przyczyny nie ustalono (inna
  taryfa, np. regionalna „Taryfa Małopolska”, oferta promocyjna, inna odległość albo błąd w
  raporcie). **Do sprawdzenia w PDF-ie przed uznaniem tabeli za potwierdzoną.**
- **Druga tabela (Taryfa Małopolska).** Wcześniejsza uwaga w repo mówiła o dwóch tabelach (bazowa
  TP-KMŁ i regionalna „Taryfa Małopolska”) i braku rozstrzygnięcia, którą stosuje dany pociąg.
  Raport `km-malopolskie` tego nie rozstrzyga. Wdrożona jest wyłącznie Tabela nr 1.
- **Przykład Stróże → Gorlice (~13 km).** Odległość ok. 13 km pochodzi z zadania, nie z raportu.
  Raport potwierdza tylko, że KMŁ obsługują Gorlice (relacja Kraków - Jasło, K7/K71; lista stacji
  zawiera Gorlice Zagórzany, Gorlice Glinik, Gorlice). Pasmo 11-15 km = 9,80 zł (szacunek,
  niepotwierdzone). Czy są kursy Kraków Główny - Gorlice bez przesiadki: NIEZWERYFIKOWANE.
- **Ulgi, bilety okresowe i łączne (np. WSPÓLNY KMK+KMŁ)** nie są w raporcie ani w modelu: pasażer
  z ulgą dostaje cenę normalną jako górną granicę, oznaczoną jako niepotwierdzoną.
- **Odcinek do/z Kraków Lotnisko** nie dostaje tej tabeli (rozpoznanie po nazwie stacji), tylko
  niepotwierdzony szacunek 0,35 zł/km.
- **Km:** `leg.distance_km` z MOTIS to linia prosta (zaniża pasmo); km po torach z
  `leg.extra["distance_along_track_km"]`, gdy routing je ustawi.

## Czego NIE ruszono

Koleje Mazowieckie (tabela niepotwierdzona: 15,30 zł vs 15,60 zł za 31-40 km), POLREGIO / Koleje
Dolnośląskie / Koleje Śląskie, SKM, ŁKA – bez zmian. Testy pilnują, że KMŁ nie trafia do
`PL_REGIONAL_RAIL_KEYWORDS` i że POLREGIO w Małopolsce dalej dostaje Taryfę Podstawową.

## Co zrobić przed uznaniem za potwierdzone

1. Otworzyć w przeglądarce PDF taryfy (Tabela nr 1, s. 66) i porównać 30 pasm z
   `fares/data/koleje_malopolskie.json`; odczytać z okładki datę wejścia w życie.
2. Wyjaśnić 28,50 zł dla Kraków Główny - Jasło (rozkład K71) względem Tabeli nr 1.
3. Dla każdego sprawdzonego pasma zmienić `potwierdzone.status` na inny niż „wg Gemini,
   niezweryfikowane niezależnie” (np. „potwierdzone w PDF TP-KMŁ”) i uzupełnić `obowiazuje_od`.
