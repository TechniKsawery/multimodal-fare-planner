"""Zasada kompletnego miasta: miasto wdrożone w projekcie ma mieć taryfę lokalną, atrakcje i kartę
miejską (albo jawny wpis, że jej nie ma), każde ze źródłem i datą weryfikacji.

Test nic nie zgaduje i nie dopisuje danych: czyta tylko pliki JSON. Luki wypisuje czytelną listą
per miasto (pytest -s tests/test_city_completeness.py). Znane, zaakceptowane luki są w
KNOWN_GAPS z uzasadnieniem; nowa luka albo wpis, który przestał być potrzebny, kończy test błędem.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FARES = ROOT / "fares" / "data"
ATTRACTIONS = json.loads((ROOT / "attractions/data/attractions.json").read_text(encoding="utf-8"))
CARDS = json.loads((ROOT / "attractions/data/city_cards.json").read_text(encoding="utf-8"))

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Miasto -> plik taryfy lokalnej w fares/data. Gelsenkirchen jedzie na taryfie VRR (eezy.nrw).
LOCAL_FARE = {
    "lublin": "ztm_lublin.json",
    "warszawa": "ztm_warszawa.json",
    "krakow": "mpk_krakow.json",
    "poznan": "ztm_poznan.json",
    "wroclaw": "mpk_wroclaw.json",
    "berlin": "bvg_berlin.json",
    "hamburg": "hvv.json",
    "munchen": "mvv.json",
    "koln": "vrs_koln.json",
    "gelsenkirchen": "vrr_eezy.json",
}

# Miasta, dla których jawnie przyjęto, że nie mają karty miejskiej (decyzja projektu, nie wynik
# weryfikacji u źródła; powód w wartości). Karta w city_cards.json zawsze wygrywa z tym wpisem.
NO_CARD_DECLARED = {
    "lublin": "przyjęte w projekcie: brak karty miejskiej w ofercie Lublina; wyszukiwanie 2026-10-11 nie znalazło takiej karty, ale to nie dowód braku",
}

# Znane, zaakceptowane luki: (miasto, kod) -> powód. Nie ukrywamy ich, tylko nazywamy.
FREE_NO_URL = "wstęp bezpłatny (cena 0) z price_verified:true, ale bez official_url"
KNOWN_GAPS = {
    ("wroclaw", "karta: brak wpisu w city_cards.json"): "Wrocław Tourist Card istnieje (visitwroclaw.eu/en/wroclaw-tourist-card-faq, sprawdzone 2026-10-11), ale dostępne strony nie podają ceny ani wariantów (punkty + opcjonalny transport); wpis dopiero po odczycie cennika w przeglądarce",
    ("warszawa", "atrakcja warszawa_hala_koszyki: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("warszawa", "atrakcja warszawa_bazar_rozyckiego: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("munchen", "atrakcja munchen_viktualienmarkt: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("munchen", "atrakcja munchen_englischer_garten: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("munchen", "atrakcja munchen_westpark: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("wroclaw", "atrakcja wroclaw_hala_targowa: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("wroclaw", "atrakcja wroclaw_park_szczytnicki: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("wroclaw", "atrakcja wroclaw_wyspa_slodowa: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
    ("poznan", "atrakcja poznan_park_cytadela: " + FREE_NO_URL): "darmowe miejsce, brak URL w danych",
}


def _fare_gaps(city: str) -> list[str]:
    name = LOCAL_FARE.get(city)
    if not name or not (FARES / name).exists():
        return ["taryfa lokalna: brak pliku w fares/data"]
    data = json.loads((FARES / name).read_text(encoding="utf-8"))
    gaps = []
    src = " ".join(str(v) for k, v in data.items() if k.startswith("_zrodlo") or k == "source")
    if "http" not in src:
        gaps.append(f"taryfa lokalna {name}: brak URL źródła (_zrodlo*)")
    meta = " ".join(str(v) for k, v in data.items() if k.startswith("_") or k == "as_of")
    if not ISO_DATE.search(meta):
        gaps.append(f"taryfa lokalna {name}: brak daty weryfikacji w polach _*")
    return gaps


def _attraction_gaps(city: str) -> list[str]:
    items = [a for a in ATTRACTIONS["atrakcje"] if a["city"] == city]
    if not items:
        return ["atrakcje: brak jakichkolwiek wpisów"]
    gaps = []
    for a in items:
        pv = a.get("price_verified")
        has_url = str(a.get("official_url", "")).startswith("http")
        if pv is None:
            gaps.append(f"atrakcja {a['id']}: price_verified nie jest jawnie ustawione")
        elif pv and not has_url:
            gaps.append(f"atrakcja {a['id']}: " + (FREE_NO_URL if a["normal_price"] == 0 else "price_verified:true bez official_url"))
    # daty: atrakcje mają jedną datę na plik (_data_aktualizacji); grupowe ceny mają własne
    if not ISO_DATE.fullmatch(str(ATTRACTIONS.get("_data_aktualizacji", ""))):
        gaps.append("atrakcje: brak _data_aktualizacji pliku")
    for a in items:
        for g in ("child_price", "student_price", "senior_price", "family_price"):
            gp = a.get(g)
            if gp and gp.get("price_verified"):
                if not str(gp.get("source_url", "")).startswith("http") or not ISO_DATE.fullmatch(str(gp.get("verified_date", ""))):
                    gaps.append(f"atrakcja {a['id']}.{g}: brak source_url/verified_date")
    return gaps


def _card_gaps(city: str) -> list[str]:
    cards = [c for c in CARDS["karty"] if c["city"] == city]
    if not cards:
        return [] if city in NO_CARD_DECLARED else ["karta: brak wpisu w city_cards.json"]
    gaps = []
    for c in cards:
        if not c.get("existence_verified"):
            gaps.append(f"karta {c['id']}: existence_verified nie jest true")
            continue
        if not str(c.get("existence_source_url", "")).startswith("http") or not ISO_DATE.fullmatch(str(c.get("existence_verified_date", ""))):
            gaps.append(f"karta {c['id']}: brak existence_source_url/existence_verified_date")
        for v in c.get("variants", []):
            if v.get("price_verified") is False:
                continue  # jawnie niepotwierdzona cena to dozwolony, widoczny stan
            if v.get("price_verified") is None:
                gaps.append(f"karta {c['id']}/{v['id']}: price_verified nie jest jawnie ustawione")
    return gaps


def _all_cities() -> list[str]:
    cities = {a["city"] for a in ATTRACTIONS["atrakcje"]} | {c["city"] for c in CARDS["karty"]}
    return sorted(cities | set(LOCAL_FARE))


def collect_gaps() -> dict[str, list[str]]:
    return {c: _fare_gaps(c) + _attraction_gaps(c) + _card_gaps(c) for c in _all_cities()}


def test_every_deployed_city_is_mapped_to_local_fare():
    deployed = {a["city"] for a in ATTRACTIONS["atrakcje"]} | {c["city"] for c in CARDS["karty"]}
    assert not deployed - set(LOCAL_FARE), f"miasta bez przypisanej taryfy lokalnej: {sorted(deployed - set(LOCAL_FARE))}"


def test_city_completeness(capsys):
    gaps = collect_gaps()
    unexpected, used = [], set()
    report = []
    for city, items in gaps.items():
        report.append(f"{city}: " + ("kompletne" if not items else f"{len(items)} luk(i)"))
        for g in items:
            if (city, g) in KNOWN_GAPS:
                used.add((city, g))
                report.append(f"  [znana] {g} — {KNOWN_GAPS[(city, g)]}")
            else:
                unexpected.append((city, g))
                report.append(f"  [NOWA]  {g}")
    print("\n" + "\n".join(report))
    stale = sorted(set(KNOWN_GAPS) - used)
    assert not unexpected, "nowe luki w kompletności miast:\n" + "\n".join(f"{c}: {g}" for c, g in unexpected)
    assert not stale, f"wpisy KNOWN_GAPS bez luki (usuń je): {stale}"
