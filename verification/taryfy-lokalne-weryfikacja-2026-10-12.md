# Lokalne taryfy kolejowe (SKM Trójmiasto, SKM Warszawa, ŁKA Łódź) — źródła i status, 2026-10-12

Wszystkie pozycje poniżej: **wg Gemini, niezweryfikowane niezależnie**. Zgodnie z CONTRIBUTING.md
(„Dane z zewnętrznych AI”) kod ustawia dla nich `price_verified=False` i `PriceType.ESTIMATE` do
czasu drugiego niezależnego źródła. Raporty:
`research/skm-km-tabele.md` (gałąź `gemini/skm-km-tabele`) i `research/ztm-lka-regio.md`
(gałąź `gemini/ztm-lka-regio`). Domeny przewoźników (`skm.pkp.pl`, `wtp.waw.pl`, `lka.lodzkie.pl`,
`mazowieckie.com.pl`) są z sesji chmurowej zablokowane (egress), więc żadnego z poniższych URL-i
nie otwarto. Liczby przepisano z raportów (tabelę SKM skryptem, bez ręcznego przepisywania) i
sprawdzono wewnętrznie: kwoty ulg 37/49/51% zgadzają się z procentem od ceny normalnej w
każdym z 21 pasm (test `tests/test_local_rail_tariffs.py`).

| Pozycja | Wartość | Źródło (wg raportu) | Data raportu |
|---|---|---|---|
| SKM Trójmiasto, 21 pasm biletu jednorazowego, od 1.03.2026 | 7,00 zł (do 6 km) … 42,00 zł (401-500 km); 19-24 km 11,00 zł, 31-40 km 14,00 zł | https://www.skm.pkp.pl/files/user-uploads/ms/1_marca_2026/Cennik_1_marca_2026_po_zm_1.pdf , Tabela nr 1 s. 15 (ulgi: tab. 4 s. 18, tab. 6 s. 20, tab. 8 s. 22) | 2026-10-12 |
| Bilety ZTM Gdańsk / ZKM Gdynia w SKM | nie honorowane (wyjątek: okresowe imienne ZTM z Gdańską Kartą Mieszkańca, niemodelowane) | ten sam cennik / strona https://www.skm.pkp.pl/dla-pasazera/taryfy-i-przepisy/tabele-oplat | 2026-10-12 |
| SKM Warszawa: bilety czasowe ZTM | 20 min 3,40 zł (strefy 1+2), 75 min 4,40 zł (strefa 1), 90 min 7,00 zł (strefy 1+2); honorowane w S1, S2, S3, S4, S40 | https://www.wtp.waw.pl/ceny-i-rodzaje-biletow/ | 2026-10-12 |
| KM i WKD: bilety czasowe ZTM | nie honorowane; wyjątek: KM Warszawa Płudy - Warszawa Lotnisko Chopina (oba kierunki) | https://www.wtp.waw.pl/integracje/wspolny-bilet-ztm-km-wkd/ | 2026-10-12 |
| ŁKA w Łodzi (Strefa A) | honorowane bilety MPK Łódź; własne bilety 20 min 4,40 zł, 40 min 5,60 zł, 80 min 6,80 zł | https://lka.lodzkie.pl/Honorowanie-biletow-komunikacji-miejskiej-w-Lodzi/ | 2026-10-12 |

## Sprzeczności i braki w raportach

- **SKM:** raport rozstrzyga starą sprzeczność (12,00 zł vs 14,00 zł za 31-40 km; 10,00 zł vs
  11,00 zł za 19-24 km) na korzyść cennika od 1.03.2026; wersja 12,00/10,00 to cennik 2023-2024.
  Wewnętrzna drobna niespójność raportu: Bilet Trójmiejski z ulgą 37% (7,85 zł vs 7,87 zł) —
  dotyczy biletów strefowych, które NIE są wdrożone. Ostatnie pasmo w PDF to 401-500 km, na
  stronie SKM przycisk „401-600”.
- **KM — niewdrożone.** Pasmo 31-40 km: raport `skm-km-tabele` podaje 15,30 zł, raport
  `ztm-lka-regio` 15,60 zł (cytat „31 – 40 km – 15,60 zł”). Poza tym raporty różnią się źródłem
  (cennik od 1.07.2022 z późniejszymi zmianami 1-6).
- **Koleje Małopolskie — niewdrożone.** Dwie tabele (bazowa TP-KMŁ i regionalna Taryfa Małopolska)
  i brak informacji, którą stosuje dany pociąg.
- **ŁKA:** raport nie zawiera cennika MPK Łódź, więc wyceniamy własnym biletem ŁKA. Ulgi i bilety
  okresowe nie są modelowane.
- **SKM Warszawa:** strefy 1/2 nie są znane routingowi (koło 15 km wokół centrum); bilet 75-minutowy
  dotyczy tylko strefy 1.

## Co zrobić przed uznaniem za potwierdzone

Otworzyć w przeglądarce PDF cennika SKM (Tabela nr 1, s. 15), stronę WTP (ceny i honorowanie w
SKM/KM/WKD) oraz stronę ŁKA i porównać z `fares/data/skm_trojmiasto.json`,
`fares/data/ztm_warszawa.json` (`_zrodlo_skm`, `_zrodlo_km_wkd`), `fares/data/lka_lodz.json`.
