"""Parser tabel cen z PDF "Cennik oferty Super Promo International Polska-Niemcy".

Wejście: tekst z `pdftotext -layout`. Wyjście: słownik pociąg -> relacja ->
poziom (I-V) -> lista (klasa2, klasa1) na strefę. Strefy (listy miejscowości)
są wpisane ręcznie w scripts/build_spi_data.py po lekturze PDF, bo układ
kolumn z listami miast w pdftotext nie jest powtarzalny.
"""
import re
import sys

NUM = r"(?:\d{1,3},\d{2}|-)"
TITLE = re.compile(r"^\s*Pociąg nr (\d+)/\s*(\d+) (.+?) relacji (.+)$")
LEVELS = ["I", "II", "III", "IV", "V"]


def _val(tok):
    return None if tok == "-" else float(tok.replace(",", "."))


def parse_text(text):
    pages = text.split("\f")
    trains = []
    cur = None
    for page in pages:
        for line in page.split("\n"):
            m = TITLE.match(line)
            if m and "..." not in line:
                cur = {"numer": f"{m.group(1)}/{m.group(2)}", "nazwa": m.group(3).strip(),
                       "relacja_trasy": m.group(4).strip(), "_etykiety": [], "_grupy": []}
                trains.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"^\s*(Frankfurt/O|Berlin|Leipzig|Riesa|Elsterwerda|Ruhland|Hoyerswerda)\b", line)
            if m:
                cur["_etykiety"].append(m.group(1))
                line = line[m.end():]
            m = re.match(rf"^\s*(I|II|III|IV|V)\s+((?:{NUM}\s+)*{NUM})\s*$", line)
            if m:
                toks = m.group(2).split()
                if len(toks) % 2:
                    continue
                vals = [_val(t) for t in toks]
                row = [[vals[i], vals[i + 1]] for i in range(0, len(vals), 2)]
                if m.group(1) == "I":
                    cur["_grupy"].append({})
                if cur["_grupy"]:
                    cur["_grupy"][-1][m.group(1)] = row
    for t in trains:
        et, gr = t.pop("_etykiety"), t.pop("_grupy")
        t["tabela"] = dict(zip(et, gr)) if len(et) == len(gr) else {}
        t["blad_parsowania"] = len(et) != len(gr)
    return trains


if __name__ == "__main__":
    for t in parse_text(open(sys.argv[1], encoding="utf-8").read()):
        print(t["numer"], t["nazwa"], {r: len(v) for r, v in t["tabela"].items()}, t['blad_parsowania'],
              {r: len(next(iter(v.values()))) for r, v in t["tabela"].items() if v})
