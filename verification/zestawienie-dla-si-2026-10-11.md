# Zestawienie dla SI (stan: main po PR #56 i #57 + PR #58, 2026-10-11)

Podstawa: kod i dane w repozytorium oraz pliki `verification/`. Każda kwota ma źródło i datę odczytu w przeglądarce (2026-10-11), chyba że napisano inaczej.

## Co robi produkt
Multimodalna wyszukiwarka połączeń PL + DE (np. Lublin → Gelsenkirchen): routing kolejowy (MOTIS na danych GTFS/OSM), do każdego odcinka szacunek ceny z oznaczeniem "oficjalna taryfa" lub "szacunek", plus atrakcje z cenami, karty miejskie i sugestia kart/BahnCard.

## Pokrycie
- Atrakcje: 82 w 10 miastach (Berlin 6, Gelsenkirchen 6, Hamburg 6, Kolonia 15, Kraków 5, Lublin 4, Monachium 18, Poznań 7, Warszawa 9, Wrocław 6), dane w `attractions/data/attractions.json`.
- Moduły taryf (`fares/data/`): PKP Intercity, DB Flexpreis, BahnCard, Deutschlandticket, FlixBus (fallback), PKP IC PL-DE oraz DB PL-DE, komunikacja miejska: ZTM Lublin, ZTM Warszawa, ZTM Poznań, MPK Kraków, MPK Wrocław, BVG Berlin, HVV, MVV, VRR, VRS Kolonia.
- Karty miejskie: Berlin WelcomeCard, RUHR.TOPCARD, Kraków City Pass, Hamburg Card, München CityTourCard, Köln Card, Warsaw Pass, Poznań City Card.

## Zweryfikowane kwoty (odczyt w przeglądarce 2026-10-11)
| Pozycja | Kwota | Źródło |
|---|---|---|
| Jugend BahnCard 25 | 0 EUR od 7.10 do 12.12.2026, potem 7,90 EUR | bahn.de/angebot/bahncard/bahncard25/jugendbahncard25 |
| BahnCard 25 / 50 | 62,90 / 244 EUR (2. klasa) | bahn.de/angebot/bahncard/vergleich |
| My BahnCard 25 / 50 | 39,90 / 79,90 EUR | j.w. |
| VRS Kolonia, Preisstufe 1b | 4,00 EUR dorosły, 1,80 EUR dziecko (6-14); Kolonia = 1b wg KVB | vrs.de/tickets/ticketsortiment/einzelticket (Stand 01.06.2026); kvb.koeln/tickets/tarifgebiete/koeln.html |
| ZTM Lublin (bilety czasowe) | 3,40 / 4,60 / 5,20 PLN (15/40/90 min) | lubika.zdtm.lublin.eu/cennik (od 16.02.2026) |
| ZTM Warszawa | 3,40 (20 min) / 4,40 (75 min, strefa 1) / 7,00 PLN (90 min) | warszawa19115.pl (akt. 2025-11-20) |
| Berlin WelcomeCard | 48h AB 28,50; 72h AB 39,50; Museumsinsel 62 EUR | bvg.de |
| Kraków City Pass | 32 / 40 / 50 EUR (1/2/3 dni) | discovercracow.com/tickets |
| Muzeum Powstania Warszawskiego | 35 PLN normalny, 30 PLN ulgowy, czwartki wstęp wolny | bilety.1944.pl/cennik.html |
| Museum Ludwig | 15,40 EUR (ermäßigt 10,40) | museum-ludwig.de |
| Termy Maltańskie | 46 zł (bilet 1h) | termymaltanskie.com.pl/cenniki |
| Zoo Poznań | 45 zł dzień powszedni mar-paź; od listopada do lutego 20 zł | zoo.poznan.pl |
| PGE Narodowy | 45 / 35 / 125 PLN (trasa VIP) | wycieczki.pgenarodowy.pl/cennik |
| Römisch-Germanisches Museum | 6 EUR | roemisch-germanisches-museum.de |
| NS-Dokumentationszentrum | 4,50 EUR (student 2 EUR) | nsdok.de/Ihr-Besuch |
| Kölner Seilbahn | 9,50 EUR tam i z powrotem (dziecko 4,80) | koelner-seilbahn.de/fahrten.html |
| Claudius Therme | 36,50 EUR bilet dzienny pon-pt, brak ulg | claudius-therme.de |
| SEA LIFE Monachium | 20 EUR online / 25 EUR na miejscu | visitsealife.com/muenchen/tickets |
| Jochen Schweizer Kletterpark | od 19,90 EUR | jochen-schweizer-arena.de/kletterpark |
| Brewery Tour Kolonia | od 27,50 EUR | willkommen.koelntourismus.de |
| Zollverein | Führungen od 12,50 EUR, ermäßigt od 9,50 EUR (strona nie określa uprawnionych) | zollverein.de/besuch-planen/eintrittspreise |

Ceny "od" i ceny dynamiczne (Zollverein, Fernsehturm, Kölner Zoo) są w danych oznaczone adnotacją (PR #57).

## Niezweryfikowane
- Brak potwierdzenia ceny: Wallraf-Richartz (muzeum zamknięte), BMW Museum (cena tylko w rezerwacji), Ogród Botaniczny Wrocław i Minigolf Familienpark (brak strony operatora) mają `price_verified:false`.
- Fernsehturm: Standard od 20 EUR, ale widżet rezerwacji pokazuje kwoty dopiero po wyborze terminu, ceny dynamiczne.
- PKP IC PL-DE (Warszawa/Kraków/Gdynia-Berlin 69, Lublin/Przemyśl 79, Poznań 47 EUR): kwoty z odczytu 2026-10-09, PDF cennika (intercity.pl, od 19.08.2026) nie czytany ponownie.
- FlixBus: stawka 0,35 zł/km to zgrubny fallback, nie cennik operatora.
- Rozbicie cen ulgowych: wiele pozycji ma warunek ulgi tylko w opisie; ceny dla dzieci SEA LIFE, Jochen Schweizer nie są publikowane.
- Wiadomość z bahn.de/VRS może się zmienić; ceny są stanem na dzień odczytu.
