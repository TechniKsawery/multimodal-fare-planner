"""Generuje fares/data/pkp_spi_pl_de.json z tekstu cennika PKP IC "Super Promo International
Polska-Niemcy" (verification/zrodla-pdf/cennik_spi.txt, z `pdftotext -layout`).

Ceny parsuje scripts/parse_spi_pdf.py. Listy miejscowości w strefach są wpisane ręcznie poniżej
(układ kolumn w tekście z PDF nie jest powtarzalny), ale skrypt sprawdza, że KAŻDA wpisana
miejscowość faktycznie występuje w tekście cennika, a liczba stref zgadza się z tabelą cen.

Uruchomienie z korzenia repo:  python3 scripts/build_spi_data.py
Pominięte (nie modelowane): Saxonia, Via Regia (relacje do Lipska), Chopin i Carpatia
(Monachium, miejsca sypialne/do leżenia) — inna struktura tabel, nieobjęte wyceną Berlina.
"""
import json
import pathlib
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from parse_spi_pdf import parse_text  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TXT = ROOT / "verification/zrodla-pdf/cennik_spi.txt"
OUT = ROOT / "fares/data/pkp_spi_pl_de.json"

BWE = [
    ["Rzepin"],
    ["Świebodzin", "Zbąszynek"],
    ["Poznań"],
    ["Kutno", "Konin"],
    ["Warszawa"],
]
ODRA = [
    ["Rzepin"],
    ["Zielona Góra"],
    ["Legnica", "Lubin", "Głogów"],
    ["Opole", "Wrocław"],
    ["Kraków", "Katowice", "Zabrze", "Gliwice", "Kędzierzyn-Koźle"],
]
WAWEL = ODRA[:4] + [
    ["Bochnia", "Kraków", "Katowice", "Zabrze", "Gliwice", "Kędzierzyn-Koźle"],
    ["Przemyśl", "Jarosław", "Przeworsk", "Łańcut", "Rzeszów", "Dębica", "Tarnów"],
]
GEDANIA = [
    ["Rzepin"],
    ["Zbąszynek", "Świebodzin"],
    ["Gniezno", "Poznań"],
    ["Bydgoszcz", "Toruń", "Inowrocław"],
    ["Gdynia", "Sopot", "Gdańsk", "Tczew"],
]
URSA_430 = [
    ["Rzepin"],
    ["Świebodzin", "Zbąszynek", "Zbąszyń", "Nowy Tomyśl"],
    ["Opalenica", "Poznań", "Kościan", "Leszno"],
    ["Rawicz", "Żmigród", "Oborniki Śląskie", "Wrocław", "Brzeg", "Opole"],
    ["Kędzierzyn Koźle", "Gliwice", "Zabrze", "Katowice", "Jaworzno Szczakowa", "Trzebinia",
     "Krzeszowice", "Kraków", "Bochnia", "Brzesko Okocim"],
    ["Tarnów", "Dębica", "Rzeszów", "Łańcut", "Przeworsk", "Jarosław", "Przemyśl"],
]
URSA_440 = [
    ["Rzepin"],
    ["Świebodzin", "Zbąszynek", "Zbąszyń", "Nowy Tomyśl"],
    ["Opalenica", "Poznań", "Środa Wielkopolska", "Jarocin"],
    ["Pleszew", "Kalisz", "Sieradz", "Zduńska Wola", "Łask", "Pabianice"],
    ["Łódź", "Koluszki", "Skierniewice", "Żyrardów", "Warszawa", "Otwock"],
    ["Pilawa", "Dęblin", "Puławy", "Nałęczów", "Lublin", "Świdnik", "Rejowiec", "Chełm"],
]
STREFY = {
    "40/41": BWE, "42/43": BWE, "44/45": BWE, "46/47": BWE, "48/49": BWE,
    "246/247": BWE, "248/249": BWE,
    "54/55": ODRA, "56/57": WAWEL, "58/59": WAWEL, "230/231": GEDANIA,
    "430/431": URSA_430, "440/441": URSA_440,
}
POZIOMY = ["I", "II", "III", "IV", "V"]
RZYMSKIE = ["I", "II", "III", "IV", "V", "VI"]


def norm(s):
    s = unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ")


def main():
    text = TXT.read_text(encoding="utf-8")
    ntext = " ".join(norm(text).split())
    trains = {t["numer"]: t for t in parse_text(text) if t["numer"] in STREFY}
    assert set(trains) == set(STREFY), set(STREFY) - set(trains)
    pociagi = []
    for numer, strefy in STREFY.items():
        t = trains[numer]
        assert not t["blad_parsowania"], numer
        for rel, tab in t["tabela"].items():
            assert list(tab) == POZIOMY, (numer, rel)
            for row in tab.values():
                assert len(row) == len(strefy), (numer, rel, len(row), len(strefy))
        for miasta in strefy:
            for m in miasta:
                assert norm(m) in ntext, f"{m} nie występuje w cenniku"
        ceny = {
            rel: {
                p: {RZYMSKIE[i]: {"klasa_2": c2, "klasa_1": c1} for i, (c2, c1) in enumerate(row)}
                for p, row in tab.items()
            }
            for rel, tab in t["tabela"].items()
        }
        pociagi.append({
            "numer": numer, "nazwa": t["nazwa"], "trasa": t["relacja_trasy"],
            "strefy": {RZYMSKIE[i]: m for i, m in enumerate(strefy)},
            "ceny_eur": ceny,
        })
    out = {
        "_zrodlo": "PKP Intercity, 'Cennik oferty Super Promo International w komunikacji Polska – Niemcy', ważny od 19 sierpnia 2026 (33 strony).",
        "_zrodlo_url": "https://www.intercity.pl/pl/dokumenty/Przepisy i taryfy/Cennik_SPI_Polska-Niemcy_od_19.08.2026.pdf",
        "_kopia_zrodla": "PDF PKP IC (sha256 38d58ffc1b9640ba99e146330f653ddd1846b5d1d96b9ee4ed62f08775cf6088; oryginał pod _zrodlo_url, kopii PDF nie ma w repo) i verification/zrodla-pdf/cennik_spi.txt",
        "_data_odczytu": "2026-10-11",
        "_uwaga": "Ceny dla pasażera DOROSŁEGO (PDF nie podaje ulg), w euro, za miejsce do siedzenia, kolumny klasa 2 i klasa 1. Poziom cenowy I-V zależy od dostępności puli (PKP: pule aktualizowane dynamicznie i ograniczone) - reguła przydziału poziomu dla konkretnego dnia NIE jest w cenniku i nie jest modelowana; pokazujemy przedział poziom I - poziom V. Ceny obowiązują, gdy rozkład przewiduje kursowanie pociągu i zatrzymanie na stacji. Przeliczenie na PLN po kursie z dnia zakupu. Pominięte: Saxonia 132/133 i Via Regia 134/135 (Lipsk), Chopin i Carpatia (Monachium, miejsca sypialne) - inna struktura tabel.",
        "waluta": "EUR",
        "pociagi": pociagi,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("zapisano", OUT, len(pociagi), "pociągów")


if __name__ == "__main__":
    main()
