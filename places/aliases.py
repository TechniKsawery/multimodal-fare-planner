"""Nazwy miast w językach interfejsu (PL, EN, DE, ES, FR, NL) z pliku places/aliases.json.

Do czego służą:
- szukanie: wpisanie dowolnej nazwy miasta ("Krakau", "Cologne", "Monachium", "Koeln") daje to samo
  miejsce; geokoder MOTIS dostaje nazwę lokalną (`local_query`), bo sam nie zwraca nazw
  alternatywnych (odpowiedź /api/v1/geocode ma jedno pole `name`; parametr `language` zmienia tylko
  język tej jednej nazwy i nie da się go sprawdzić bez działającego MOTIS);
- wyświetlanie: miasto (albo dworzec zaczynający się od jego nazwy, "Köln Hbf") pokazujemy w języku
  interfejsu, a nazwę lokalną obok (`localize_name`).

Nic tu nie zgadujemy: pusta nazwa w danym języku = brak odrębnej nazwy (używamy lokalnej).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).with_name("aliases.json")
LANGUAGES = ("pl", "en", "de", "es", "fr", "nl")

# Promień wokół współrzędnych miasta z pliku: wynik geokodera dalej niż tyle nie jest tym miastem (inna wieś o tej
# samej nazwie). Tyle samo przyjmuje skrypt weryfikujący aliasy.
CITY_RADIUS_KM = 25.0

_TOKEN = re.compile(r"[^\W_]+")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
# Słowa, po których nazwa miasta jest początkiem dłuższej nazwy innego miejsca ("Frankfurt Oder"):
# takiego początku nie zamieniamy na nazwę miasta.
_CONTINUATION = {"oder", "an", "am", "im", "bei", "ob", "in", "nad"}
# najdłuższy alias ma 5 słów ("Landsberg an der Warthe"); dalsze słowa nie są częścią nazwy miasta
_MAX_ALIAS_WORDS = 5


def fold(text: str) -> str:
    """Tekst do porównań: małe litery, bez polskich/niemieckich znaków diakrytycznych i interpunkcji."""
    text = text.casefold().replace("ł", "l").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass(frozen=True)
class City:
    key: str
    local: str  # nazwa w kraju miasta, taka jak zwraca geokoder ("Köln", "Kraków", "Praha")
    country: str
    display: dict  # język -> nazwa wyświetlana wg Wikidata ("" = brak odrębnej nazwy)
    aliases: (
        tuple  # dodatkowe zapisy tylko do wyszukiwania, nigdy pokazywane ("Kattowitz", "Cracow")
    )
    verified: bool
    lat: float | None = None  # przybliżony środek; tylko do rozstrzygania trafień w Wikidata
    lon: float | None = None

    def name(self, lang: str | None) -> str:
        """Nazwa w danym języku; brak odrębnej nazwy (albo nieznany język) = nazwa lokalna."""
        return self.display.get(lang or "") or self.local

    def search_names(self) -> list[str]:
        out = [self.local, *self.display.values(), *self.aliases]
        return list(dict.fromkeys(n for n in out if n))


@lru_cache(maxsize=1)
def load_cities() -> tuple[City, ...]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(
        City(
            key=key,
            local=entry["local"],
            country=entry["kraj"],
            display=dict(entry["wyswietlana"]),
            aliases=tuple(entry["aliasy_wyszukiwania"]),
            verified=bool(entry.get("zweryfikowano")),
            lat=entry.get("lat"),
            lon=entry.get("lon"),
        )
        for key, entry in data["miasta"].items()
    )


@lru_cache(maxsize=1)
def _index() -> dict[str, City]:
    """Zapis po złożeniu (fold) -> miasto. "Köln" ma też wariant "koeln" (umlaut jako ae/oe/ue)."""
    index: dict[str, City] = {}
    for city in load_cities():
        for name in city.search_names():
            for variant in {fold(name), fold(name.translate(_UMLAUTS))}:
                index.setdefault(variant, city)
    return index


@lru_cache(maxsize=1)
def _local_index() -> dict[str, City]:
    """Tylko nazwy lokalne: tak nazywa miejsca geokoder, więc tylko je podmieniamy przy wyświetlaniu
    (polskie "Praga" to też dzielnica Warszawy, której nie wolno pokazać jako Prague)."""
    out = {}
    for city in load_cities():
        for variant in {fold(city.local), fold(city.local.translate(_UMLAUTS))}:
            out.setdefault(variant, city)
    return out


def find_city(text: str) -> City | None:
    """Miasto o tej nazwie w dowolnym z języków (bez wielkości liter i ogonków), inaczej None."""
    return _index().get(fold(text))


def alias_names() -> dict[str, str]:
    """Złożona nazwa (każdy język) -> nazwa lokalna miasta; do poprawiania literówek."""
    return {name: city.local for name, city in _index().items()}


def _match_prefix(part: str, index: dict[str, City]) -> tuple[City, int] | None:
    """Miasto, którego nazwa to początek tekstu (całość albo pierwsze słowa), i pozycja końca nazwy."""
    tokens = list(_TOKEN.finditer(part))
    folded = [fold(m.group()) for m in tokens]
    for k in range(min(len(tokens), _MAX_ALIAS_WORDS), 0, -1):
        city = index.get(" ".join(f for f in folded[:k] if f))
        if city is not None:
            if k < len(tokens) and folded[k] in _CONTINUATION:
                continue
            return city, tokens[k - 1].end()
    return None


def _replace_prefix(part: str, index: dict[str, City], lang: str | None) -> str:
    """Zamienia nazwę miasta na początku członu na jego nazwę w `lang` (None = lokalną); reszta zostaje
    bez zmian ("Krakau Hbf" -> "Kraków Hbf"). Człony z cyframi (adresy) nie są ruszane."""
    if any(c.isdigit() for c in part):
        return part
    found = _match_prefix(part, index)
    if found is None:
        return part
    city, end = found
    lead = part[: len(part) - len(part.lstrip())]
    return lead + city.name(lang) + part[end:]


def local_query(text: str) -> str:
    """Wpisany tekst z nazwami miast w dowolnym języku zamienionymi na lokalne ("Cologne" -> "Köln",
    "Krakau, Hbf" -> "Kraków, Hbf"). Bez nazwy miasta: ten sam tekst."""
    parts = text.split(",")
    return ",".join(_replace_prefix(p, _index(), None) for p in parts)


def localize_name(name: str, lang: str | None) -> tuple[str, str | None]:
    """(nazwa do pokazania, nazwa lokalna albo None) dla nazwy z geokodera. Miasto albo dworzec
    zaczynający się od lokalnej nazwy miasta ("Köln Hbf") dostaje nazwę z języka interfejsu
    ("Cologne Hbf"), a oryginał wraca jako druga wartość. Gdy nic się nie zmienia: (name, None)."""
    index = _local_index()
    parts = [p.strip() for p in name.split(", ")]
    shown = [
        _replace_prefix(p, index, lang) if i == 0 else _whole(p, index, lang)
        for i, p in enumerate(parts)
    ]
    display = ", ".join(shown)
    return (display, None) if display == name else (display, name)


def _whole(part: str, index: dict[str, City], lang: str | None) -> str:
    """Człon, który w całości jest nazwą miasta (ewentualnie z interpunkcją po niej), w nazwie z `lang`."""
    found = _match_prefix(part, index)
    if found is None or _TOKEN.search(part[found[1] :]):
        return part
    city, end = found
    lead = part[: len(part) - len(part.lstrip())]
    return lead + city.name(lang) + part[end:]


def place_text(name: str, lang: str | None, template: str = "{shown} ({local})") -> str:
    """Nazwa do wstawienia w zdanie: "Cologne (Köln)" albo samo "Berlin", gdy obie nazwy są takie same."""
    shown, local = localize_name(name, lang)
    return shown if local is None else template.format(shown=shown, local=local)
