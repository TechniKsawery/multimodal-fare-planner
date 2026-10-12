"""Wspólny model danych dla modułu taryf: segment podróży i wynik szacowania ceny."""

from dataclasses import dataclass, field
from enum import Enum


class PriceType(str, Enum):
    """Czy cena jest oficjalną taryfą przewoźnika, czy naszym szacunkiem (np. z placeholderów)."""

    ESTIMATE = "szacunek"
    OFFICIAL = "oficjalna_taryfa"


class Carrier(str, Enum):
    PKP_INTERCITY = "pkp_intercity"
    DB = "db"
    VRR = "vrr"
    FLIXBUS = "flixbus"
    ZTM_LUBLIN = "ztm_lublin"
    ZTM_WARSZAWA = "ztm_warszawa"
    MPK_KRAKOW = "mpk_krakow"
    ZTM_POZNAN = "ztm_poznan"
    MPK_WROCLAW = "mpk_wroclaw"
    BVG_BERLIN = "bvg_berlin"
    HVV = "hvv"  # Hamburger Verkehrsverbund (Hamburg)
    MVV = "mvv"  # Münchner Verkehrsverbund (Monachium)
    VRS_KOLN = "vrs_koln"  # Verkehrsverbund Rhein-Sieg, obszar Kolonii (Rheinlandtarif)
    POLREGIO_PODSTAWOWA = "polregio_taryfa_podstawowa"  # POLREGIO / Koleje Dolnośląskie / Koleje
    # Śląskie: degresywna tabela odległościowa Taryfy Podstawowej (fares/polregio.py)
    INTERNATIONAL_PL_DE = "international_pl_de"  # bilet PL<->DE przekraczający granicę jednym
    # ciągłym odcinkiem kolejowym (np. Berlin-Warszawa-Express) — SZTYWNE kategorie cenowe
    # (Super Sparpreis Europa), nie tabela pasm jak krajowe kalkulatory PKP/DB. Zob. fares/international.py.


@dataclass
class DiscountProfile:
    """Profil ulg pasażera, wspólny dla wszystkich przewoźników w segmencie."""

    pkp_ulga_kod: str = "brak"  # klucz z fares/data/pkp_intercity.json -> ulgi_procent
    bahncard: str | None = None  # None, "25", "50" lub "100" (DB, oficjalne rabaty Flexpreis)
    ztm_lublin_ulgowy: bool = False  # ZTM Lublin: bilet ulgowy zamiast normalnego
    ztm_lublin_bezplatny: bool = False  # ZTM/ZDiTM Lublin: przejazd bezpłatny (100%) -
    # uczniowie publicznych i niepublicznych szkół PODSTAWOWYCH (oraz artystycznych) prowadzonych
    # przez Gminę Lublin lub działających na jej terenie, z ważną legitymacją szkolną (uchwała Rady
    # Miasta Lublin, obecna podstawa prawna: uchwała nr 206/VII/2024 z 19.12.2024). NIE potwierdzone
    # dla szkół ponadpodstawowych (licea itd.) - tam zostaje ulgowy. Potwierdzone na żywej stronie
    # zdtm.lublin.eu 2026-10-10 (patrz fares/data/ztm_lublin.json::_zrodlo_bezplatny).
    ztm_warszawa_ulgowy: bool = False  # ZTM/WTP Warszawa: bilet ulgowy (50%) - m.in. uczniowie
    # szkół ponadpodstawowych, studenci, emeryci/renciści DO 70 roku życia (polski organ
    # emerytalno-rentowy), osoby z UMIARKOWANYM stopniem niepełnosprawności 26+, uczniowie/
    # studenci szkół zagranicznych do 26 lat (wtp.waw.pl/ulgi-znizki, zweryfikowano 2026-10-10).
    ztm_warszawa_bezplatny: bool = False  # ZTM/WTP Warszawa: przejazd bezpłatny (100%) -
    # "Karta Ucznia", uczniowie szkół PODSTAWOWYCH w Warszawie (potwierdzone warszawa19115.pl
    # 2026-10-10; NIE potwierdzone dla szkół ponadpodstawowych/liceów - tam zostaje ulgowy).
    # Ta sama flaga obejmuje też: osoby 70+ (bez wymogu zamieszkania w Warszawie), osoby ze
    # ZNACZNYM stopniem niepełnosprawności 26+, osoby całkowicie niezdolne do pracy I do
    # samodzielnej egzystencji 26+, dzieci/młodzież z niepełnosprawnością do 26 lat (wszystko
    # potwierdzone wtp.waw.pl/ulgi-znizki + warszawa19115.pl, zweryfikowano 2026-10-10 - patrz
    # fares/data/ztm_warszawa.json::_zrodlo_senior_niepelnosprawnosc).
    mpk_krakow_ulgowy: bool = False  # MPK Kraków (ZTP): bilet ulgowy (50%) - m.in. emeryci DO
    # 70 roku życia, UMIARKOWANY stopień niepełnosprawności (poza wąskimi wyjątkami niżej),
    # uczniowie/studenci szkół zagranicznych do 26 lat z ważną kartą ISIC (ztp.krakow.pl,
    # zweryfikowano 2026-10-10).
    mpk_krakow_bezplatny: bool = False  # MPK Kraków: przejazd bezpłatny (100%) - uczniowie
    # szkół PODSTAWOWYCH z Krakowa i gmin Metropolii Krakowskiej, cały rok (potwierdzone
    # krakow.pl 2026-10-10). POTWIERDZONE WYKLUCZENIE ponadpodstawowych dwoma OFICJALNYMI
    # źródłami z bip.krakow.pl: tekst Załącznika nr 2 do uchwały (bazowa: Uchwała Nr XXI/231/11
    # RMK z 6.07.2011) ogranicza ogólne uprawnienie uczniów do szkół PODSTAWOWYCH - liceiści/
    # technicy są objęci TYLKO wąską pozycją dla uczniów ze specjalnymi potrzebami edukacyjnymi,
    # nie ogółem - potwierdzone też projektem uchwały zmieniającej ten załącznik. Tam (poza tą
    # wąską kategorią) zostaje ulgowy. Zob. fares/data/mpk_krakow.json::_zrodlo_bezplatny.
    # Ta sama flaga obejmuje też: osoby 70+ (bez wymogu zamieszkania w Krakowie, tylko dokument
    # z datą urodzenia), ZNACZNY stopień niepełnosprawności / całkowita niezdolność do pracy I
    # do samodzielnej egzystencji / I grupa inwalidztwa, oraz kilka WĄSKICH wyjątków gdzie nawet
    # "umiarkowany" stopień jest bezpłatny (konkretne symbole przyczyny: wzrok 04-O, ruch
    # 05-R/10-N, intelekt 01-U) - w przeciwieństwie do Warszawy, gdzie "umiarkowany" to zawsze
    # tylko 50%. Potwierdzone ztp.krakow.pl/kmk/przewodnik-po-biletach-kmk, zweryfikowano
    # 2026-10-10 - patrz fares/data/mpk_krakow.json::_zrodlo_senior_niepelnosprawnosc.
    ztm_poznan_ulgowy: bool = False  # ZTM Poznań: bilet ulgowy (50%) - m.in. uczniowie,
    # emeryci/renciści (dowolny wiek, status emeryta wystarczy), UMIARKOWANY stopień
    # niepełnosprawności / II grupa inwalidzka (ztm.poznan.pl, zweryfikowano 2026-10-10)
    ztm_poznan_bezplatny: bool = False  # ZTM Poznań: przejazd bezpłatny (100%) - osoby 70+
    # (BEZ wymogu zamieszkania w Poznaniu, tylko dokument tożsamości) oraz osoby z orzeczeniem:
    # znaczny stopień niepełnosprawności / całkowita niezdolność do pracy i do samodzielnej
    # egzystencji / I grupa inwalidztwa - w Poznaniu BEZ dolnej granicy wieku 26 lat (w
    # odróżnieniu od Warszawy/Krakowa, gdzie ta kategoria dotyczy dopiero od 26 roku życia -
    # osoby młodsze mają odrębną kategorię "dzieci i młodzież z niepełnosprawnością").
    # Potwierdzone ztm.poznan.pl/wszystko-o-biletach/ulgi-i-zwolnienia, niezależnie przez
    # centrumis.pl i PDF CUPT (Centrum Unijnych Projektów Transportowych), zweryfikowano
    # 2026-10-10 - patrz fares/data/ztm_poznan.json::_zrodlo_senior_niepelnosprawnosc.
    mpk_wroclaw_ulgowy: bool = False  # MPK Wrocław: bilet ulgowy (50%) - studenci/doktoranci,
    # emeryci/renciści, uczniowie szkół policealnych/zagranicznych do 24 lat
    mpk_wroclaw_bezplatny: bool = False  # MPK Wrocław: przejazd bezpłatny (100%) - m.in.
    # uczniowie szkół podstawowych/ponadpodstawowych do 21 lat (legitymacja, bez wymogu
    # zamieszkania we Wrocławiu, obowiązuje od 1.09.2018), dzieci do 7 lat, seniorzy 65+.
    # Potwierdzone DWOMA niezależnymi źródłami wroclaw.pl 2026-10-10, zob. [[wroclaw-pelna-
    # tabela-ulg-mpk-2026-10-10]] w pamięci projektu. Ma priorytet nad mpk_wroclaw_ulgowy
    # jeśli oba byłyby ustawione (bezpłatny < ulgowy cenowo, więc zawsze wygrywa).
    bvg_berlin_ulgowy: bool = False  # BVG/VBB Berlin: taryfa ulgowa (Ermäßigungstarif) - dzieci
    # 6-14 lat. BRAK ulgi wiekowej/bezpłatnej dla seniorów w BVG/VBB - 65+ to osobny, PŁATNY
    # produkt abonamentowy "VBB-Abo 65plus" (miesięczny/roczny bilet okresowy w obniżonej
    # cenie), nie ulga per-przejazd, więc nie modelujemy go tu (jak Bilet dla uczniów podstawówek
    # w Poznaniu). Samo orzeczenie o niepełnosprawności (np. niemiecki GdB 50) też NIE daje
    # żadnej ulgi ani bezpłatnego przejazdu bez spełnienia warunków `bvg_berlin_schwerbehindert`
    # poniżej - zweryfikowano bvg.de + vbb.de, 2026-10-10.
    bvg_berlin_schwerbehindert: bool = False  # BVG/VBB Berlin: przejazd bezpłatny (100%) -
    # TYLKO dla osób posiadających Schwerbehindertenausweis z odpowiednim Merkzeichen (np. G,
    # aG, H, Bl) ORAZ ważną, OSOBNO WYKUPIONĄ Wertmarke (104 EUR/12 mies. lub 53 EUR/6 mies.,
    # stan na 2025) doklejoną/wpisaną do Beiblatt. Bez Wertmarke sam dokument niepełnosprawności
    # nie uprawnia do niczego - to NIE jest automatyczna ulga/zwolnienie jak w polskich miastach,
    # tylko opcjonalny płatny "abonament" doczepiony do legitymacji. Potwierdzone niezależnie:
    # bvg.de/mitnahmebestimmungen ("Schwerbehinderte Menschen können öffentliche Verkehrsmittel
    # kostenfrei nutzen" + wymóg Wertmarke) i vbb.de/barrierefrei ("Wer etwa einen
    # Schwerbehindertenausweis mit gültiger Wertmarke besitzt, fährt kostenfrei"). Zweryfikowano
    # 2026-10-10 - patrz fares/data/bvg_berlin.json::_zrodlo_schwerbehindert.
    vrr_dziecko: bool = (
        False  # VRR/eezy.nrw: Kindertarif (6-14 lat), 50% rabatu wliczając sufity cenowe
    )
    hvv_dziecko: bool = False  # HVV (Hamburg): cena dziecka (6-14 lat) z oficjalnego cennika
    mvv_dziecko: bool = False  # MVV (Monachium): cena dziecka (6-14 lat) z oficjalnego cennika
    vrs_koln_dziecko: bool = False  # VRS/Rheinlandtarif (Kolonia): cena dziecka (6-14 lat)
    schwerbehinderte_wertmarke_de: bool = False
    """Bezpłatny przejazd w niemieckim transporcie lokalnym dla osób z ciężką niepełnosprawnością
    (Merkzeichen G/aG/H/Bl/Gl + ważna Wertmarke w legitymacji) — § 228 SGB IX. To zasada
    OGÓLNONIEMIECKA (nie taryfa poszczególnego związku), więc jedno pole obsługuje identycznie
    HVV, MVV i VRS/Köln (fares/hvv.py, mvv.py, kvb.py) — nie dotyczy VRR/BVG, które nie mają
    jeszcze tej kategorii zamodelowanej (możliwe do dociągnięcia później, poza zakresem tej
    zmiany). Sama Wertmarke bywa płatna (104 EUR/12 mies. lub 53 EUR/6 mies.) lub bezpłatna
    (Merkzeichen H/Bl, określone świadczenia socjalne) — to nie wpływa na cenę PRZEJAZDU, którą
    liczy ten kalkulator, tylko na koszt samej legitymacji, który tu nie jest modelowany."""
    age: int | None = None
    """Wiek pasażera w dniu podróży. Używany przez fares/international.py (bilet DB PL-DE) do
    wyboru taryfy wiekowej: dziecko/niemowlę (bis 5 lat gratis, 6-14 lat zależnie od
    `child_with_guardian`), "Super Sparpreis Europa Young" (15-26 lat) albo taryfa normalna —
    i przez fares/international_pkp.py (własna oferta PKP) do ulgi dziecięcej (6-14 -50%,
    <6 gratis) — nie wpływa na żaden INNY moduł taryf (PKP/DB/VRR/ZTM krajowe mają własne,
    osobne pola ulg wyżej, bo te zniżki zależą od STATUSU, nie samego wieku). Przed tym polem
    `age` z CLI/API trafiał tylko do routing/card_suggestions.py (sugestia zakupu BahnCard),
    nigdy do ceny biletu — zob. audyt zniżek w projekcie (2026-10-07)."""
    child_with_guardian: bool = False
    """Tylko bilet międzynarodowy PL-DE, dziecko 6-14 lat (`age`): czy dziecko podróżuje w
    towarzystwie osoby od 15 lat zgłoszonej przy tej samej rezerwacji — bahn.de: takie dziecko
    jedzie bezpłatnie na ofercie DB (zob. fares/data/international_pl_de.json::_zrodlo_dziecko).
    Domyślnie False (dziecko liczone jako podróżujące SAMODZIELNIE -> tylko 50% zniżki na
    niemiecki odcinek, NIE za darmo) — bezpieczniejszy domyślny wybór: nie zakładamy opiekuna,
    którego nie potwierdzono, żeby nie zaniżyć ceny biletu. PKP (fares/international_pkp.py) nie
    rozróżnia opiekuna — jego ulga dziecięca 50%/100% obowiązuje niezależnie od tego pola."""

    obywatelstwo: str | None = None
    """Jedna z: None (nie podano), "PL", "UE" (kraj UE/EOG inny niż Polska), "poza_UE".
    NIE zmienia samej kalkulacji ceny (użytkownik i tak sam zaznacza checkboxy ulg) — używane
    WYŁĄCZNIE przez fares/foreigner_eligibility.py do wygenerowania ostrzeżeń informacyjnych,
    czy zaznaczona ulga realnie przysługuje cudzoziemcowi wg zweryfikowanych źródeł (2026-10-10,
    zob. pamięć projektu [[zagraniczne-legitymacje-transport-status]]). Np. PKP ulga ustawowa
    studencka wymaga karty pobytu dla obywateli UE i jest całkowicie niedostępna spoza UE
    (rozporządzenie MI z 20.04.2017); Poznań/Lublin nie uznają zagranicznych legitymacji
    studenckich wcale; Kraków wymaga konkretnie ISIC; Wrocław wymaga tłumaczenia przysięgłego
    zagranicznej legitymacji (chyba że ISIC/Euro26)."""

    legitymacja_zagraniczna: bool = False
    """Czy legitymacja szkolna/studencka jest ZAGRANICZNA (wydana poza Polską). Niezależna od
    `obywatelstwo`: steruje wyłącznie ostrzeżeniami o uznawaniu legitymacji w MPK/ZTM
    (Warszawa, Kraków, Poznań, Lublin, Wrocław) w fares/foreigner_eligibility.py — nie zmienia ceny."""


@dataclass
class Segment:
    """Jeden odcinek podróży u jednego przewoźnika."""

    carrier: Carrier
    origin: str
    destination: str
    distance_km: float | None = None  # wymagane dla PKP, DB i VRR (VRR: odległość w linii prostej)
    ride_duration_min: float | None = None  # wymagane dla ZTM Lublin (taryfa czasowa)
    discounts: DiscountProfile = field(default_factory=DiscountProfile)
    travel_date: str | None = None  # "YYYY-MM-DD"; wymagane dla FlixBus (ceny dynamiczne per data)
    distance_along_track: bool = False
    """Tylko Carrier.POLREGIO_PODSTAWOWA: czy distance_km to kilometry TARYFOWE (po torach), a nie
    linia prosta. Domyślnie False — MOTIS daje linię prostą (leg.distance_km), która zaniża pasmo
    taryfy, więc nawet potwierdzone pasmo daje wtedy PriceType.ESTIMATE (fares/polregio.py)."""
    german_portion_fraction: float | None = None
    """Tylko Carrier.INTERNATIONAL_PL_DE: szacowany udział (0-1) niemieckiego odcinka trasy w
    całym dystansie (linia prosta), używany do proporcjonalnego naliczenia rabatu BahnCard,
    który oficjalnie dotyczy TYLKO niemieckiej części trasy (patrz fares/international.py).
    None = brak danych geograficznych do oszacowania -> rabat naliczany od całej ceny
    (zawyża realny rabat, ale to jedyny dostępny fallback bez współrzędnych stacji)."""
    tariff_zone: str | None = None
    """Tylko Carrier.BVG_BERLIN: "ABC", gdy któryś koniec odcinka leży w strefie C (lotnisko
    BER, patrz routing/pricing.py::BER_AIRPORT_AREA) — bilet AB tam nie obowiązuje. None =
    dobór biletu jak dotąd (Kurzstrecke/AB wg czasu jazdy)."""


@dataclass
class PriceEstimate:
    """Wynik wyceny segmentu."""

    carrier: Carrier
    amount: float
    currency: str
    price_type: PriceType
    breakdown: dict
    notes: str = ""

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency} ({self.price_type.value}) — {self.carrier.value}"
