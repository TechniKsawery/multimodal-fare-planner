# Weryfikacja cen w przeglądarce (2026-10-11)

Źródła: strony operatorów, odczyt w przeglądarce. Zasada: nic nie zgadujemy; brak publikacji = `price_verified:false` z notatką.

| Pozycja | Wynik | Dowód |
|---|---|---|
| Jugend BahnCard 25 | ZMIENIONE: 0 EUR od 2026-10-07 do 2026-12-12 (potem 7,90) | bahn.de/angebot/bahncard/bahncard25/jugendbahncard25 |
| BahnCard 25 | POTWIERDZONE 62,90 EUR (59,90 nie występuje); BC50 244, My BC 39,90/79,90 | bahn.de/angebot/bahncard/vergleich |
| VRS | ZMIENIONE: 1b 4,00/1,80 (było 3,50); tabela K/1a/1b/2/3 | vrs.de/tickets/ticketsortiment/einzelticket (Stand 01.06.2026) |
| ZTM Lublin | POTWIERDZONE 3,40/4,60/5,20 | lubika.zdtm.lublin.eu/cennik (od 16.02.2026) |
| ZTM Warszawa | POTWIERDZONE 3,40/4,40/7,00 | warszawa19115.pl (akt. 2025-11-20) |
| Berlin WelcomeCard 72h AB | POTWIERDZONE 39,50 EUR (34 nie występuje); 48h 28,50; Museumsinsel 62 | bvg.de |
| Kraków Card | POTWIERDZONE 32/40/50 EUR (blog 34/40/45 nie) | discovercracow.com/tickets |
| Termy Maltańskie | POTWIERDZONE 46 zł = bilet 1-godzinny | termymaltanskie.com.pl/cenniki |
| Nowe Zoo Poznań | POTWIERDZONE 45 zł tylko dzień powszedni mar-paź; sob/święta 55; listopad-luty 20 zł | zoo.poznan.pl |
| PGE Narodowy | POTWIERDZONE 45/35/125 (trasa VIP) | wycieczki.pgenarodowy.pl/cennik |
| Muzeum Powstania Warszawskiego | ZMIENIONE: normalny 35, ulgowy 30 (było 45); 45 to bilet z przewodnikiem; w czwartki wstęp wolny; usunięto niepotwierdzone studenckie 1 zł i rodzinne 95 zł | bilety.1944.pl/cennik.html |
| Museum Ludwig | ZMIENIONE: 15,40 (było 10), ermäßigt 10,40 | museum-ludwig.de |
| Römisch-Germanisches Museum | POTWIERDZONE 6 EUR (ermäßigt 3,50 bez listy uprawnionych) | roemisch-germanisches-museum.de |
| NS-Dokumentationszentrum | POTWIERDZONE 4,50; student 2 EUR dodane | nsdok.de/Ihr-Besuch |
| Kölner Seilbahn | POTWIERDZONE 9,50 tam i z powrotem; dziecko 4,80 (4-12) dodane | koelner-seilbahn.de/fahrten.html |
| Wallraf-Richartz | NIEPOTWIERDZONE: muzeum tymczasowo zamknięte, brak cennika | wallraf.museum |
| BMW Museum | NIEPOTWIERDZONE: cena tylko w procesie rezerwacji | tkts.bmw-welt.com |
| Ogród Botaniczny Wrocław | NIEPOTWIERDZONE: nie znaleziono strony operatora | - |
| Minigolf Familienpark | NIEPOTWIERDZONE: brak źródła | - |
| Claudius Therme | POTWIERDZONE 36,50 EUR (Tageskarte pon-pt), operator: brak ulg | claudius-therme.de/oeffnungszeiten-preise |
| Nie sprawdzone | Kölner Zoo (osobny wątek), Brewery Tour, Jochen Schweizer, SEA LIFE, Fernsehturm, Zollverein, FlixBus fallback, PKP IC PL-DE, ok. 48 cen z warunkiem w opisie | - |

## Uzupełnienie (druga tura)

| Pozycja | Wynik |
|---|---|
| SEA LIFE Monachium | POTWIERDZONE: online od 20 EUR, na miejscu 25 EUR (dorosły 15+); brak cen ulgowych |
| Jochen Schweizer Kletterpark | POTWIERDZONE: od 19,90 EUR (hochseilklettergarten); brak rozbicia wiekowego |
| PKP IC PL-DE | Dodano URL cennika (PDF z 19.08.2026); kwoty 69/79/47 EUR z 2026-10-09, PDF nie czytany ponownie |
| Brewery Tour Köln | POTWIERDZONE 27,50 EUR (od), brak ulg |
| FlixBus fallback | Bez zmian, niesprawdzone (: zgrubny fallback bez cennika operatora) |
| Fernsehturm | Standard od 20 EUR (ceny dynamiczne, widżet nie pokazuje kwot bez daty) | tv-turm.de |
| Zollverein | Führungen ab 12,50 / ermäßigt ab 9,50 EUR; strona nie określa uprawnionych do ulgi przy Führungen (zdanie o uczniach/studentach dotyczy tylko linii autobusowej); Ruhr Museum: uczniowie i studenci <25 wolny wstęp | zollverein.de |
| Kölner Zoo | Pominięty: zweryfikowany osobnym fetchem (#57) |
| Zoo Poznań (sezon) | Cena 45 zł = dzień powszedni mar-paź; od 1.11 do końca lutego 20 zł (opisane w polu `_weryfikacja`) |
