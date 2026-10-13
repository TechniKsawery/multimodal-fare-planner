"""Bagaż PODRĘCZNY wg przewoźnika: trzy jawne stany, bez zgadywania i bez przeliczania walut.

Dane: flights/data/cabin_baggage.json. Stan wynika wyłącznie z pól pliku:
- WLICZONY  — duży bagaż podręczny jest w cenie bazowego biletu,
- PLATNY    — w cenie bazowej tylko mały bagaż pod fotel; dopłata podana w ORYGINALNEJ walucie
              przewoźnika (kwota albo widełki) — NIE przeliczamy jej po placeholderowym kursie,
- NIEZNANY  — brak przewoźnika w tabeli, wpis bez price_verified albo zasada zależna od taryfy,
              której nie znamy z samej ceny biletu (nie zgadujemy taryfy).

Dopłata za bagaż podręczny NIE jest doliczana do ceny biletu ani do ceny łącznej (widełki,
dynamiczne ceny, nieznana taryfa) — pokazujemy ją osobno, jawnie.
"""

from dataclasses import dataclass, field
from enum import Enum

from ._data_loading import load

_DATA = load("cabin_baggage.json")


class CabinBaggageState(str, Enum):
    INCLUDED = "wliczony"
    PAID = "platny"
    UNKNOWN = "nieznany"


@dataclass
class CabinFee:
    """Jedna pozycja cennika dopłaty, w oryginalnej walucie (bez przeliczania)."""

    label: str  # np. "online przy rezerwacji", "przy bramce"
    min_amount: float
    max_amount: float | None  # None = cena "od" (bez górnej granicy) albo kwota stała
    currency: str
    is_from: bool = False  # True = "od X" (brak górnej granicy w źródle)

    def format(self) -> str:
        if self.is_from:
            amount = f"od {self.min_amount:.2f}"
        elif self.max_amount is None or self.max_amount == self.min_amount:
            amount = f"{self.min_amount:.2f}"
        else:
            amount = f"{self.min_amount:.2f}–{self.max_amount:.2f}"
        return f"{amount} {self.currency} ({self.label})"


@dataclass
class ExtraFee:
    """Pozycja z taryfikatora przewoźnika poza dopłatą za bagaż podręczny (rejestrowany, nadwaga...),
    w oryginalnej walucie. typ: stala | od (dolna granica) | do (górna granica) | zmienna (brak kwoty)."""

    label: str
    amount: float | None
    currency: str
    kind: str
    confirmed: bool
    note: str = ""

    def format(self) -> str:
        if self.amount is None:
            amount = "cena zmienna"
        else:
            prefix = {"od": "od ", "do": "do "}.get(self.kind, "")
            amount = f"{prefix}{self.amount:.2f} {self.currency}"
        flag = "" if self.confirmed else ", cena niepotwierdzona / zależna od trasy"
        return f"{self.label}: {amount}{flag}"


@dataclass
class CabinBaggageInfo:
    airline_code: str | None
    state: CabinBaggageState
    airline_name: str | None = None
    description: str = ""
    fees: list[CabinFee] = field(default_factory=list)
    source: str | None = None
    verified_on: str | None = None
    price_verified: bool = False  # dotyczy wymiarów/wagi i zasady wliczenia
    fees_verified: bool = False  # dopłaty (widełki, dynamiczne) potwierdzone osobno
    extra_fees: list[ExtraFee] = field(default_factory=list)
    fees_source: str | None = None
    fees_verified_on: str | None = None

    def to_dict(self) -> dict:
        """Postać do PriceEstimate.breakdown (serializowalna; kwoty w oryginalnych walutach)."""
        return {
            "stan": self.state.value,
            "przewoznik": self.airline_name,
            "kod_linii": self.airline_code,
            "opis": self.description,
            "oplaty": [
                {
                    "etykieta": f.label,
                    "od": f.min_amount,
                    "do": f.max_amount,
                    "waluta": f.currency,
                    "tylko_od": f.is_from,
                    "tekst": f.format(),
                }
                for f in self.fees
            ],
            "zrodlo": self.source,
            "data_weryfikacji": self.verified_on,
            "price_verified": self.price_verified,
            "oplaty_potwierdzone": self.fees_verified,
            "oplaty_dodatkowe": [
                {
                    "etykieta": e.label,
                    "kwota": e.amount,
                    "waluta": e.currency,
                    "typ": e.kind,
                    "potwierdzona": e.confirmed,
                    "uwaga": e.note,
                    "tekst": e.format(),
                }
                for e in self.extra_fees
            ],
            "zrodlo_oplat": self.fees_source,
            "data_weryfikacji_oplat": self.fees_verified_on,
        }


_FEE_LABELS = {
    "rezerwacja_online_pl": "online przy rezerwacji, wg strony PL",
    "rezerwacja_online": "online przy rezerwacji, wg strony EN",
    "po_rezerwacji_lotnisko": "po rezerwacji / na lotnisku, wg strony EN; PL podaje 20–60",
    "online": "online",
    "lotnisko": "na lotnisku",
    "bramka": "przy bramce",
    "priority_online": "WIZZ Priority online / telecentrum",
    "priority_lotnisko": "zakup WIZZ Priority na lotnisku",
    "kara_bagaz_do_luku": "kara za bagaż podręczny wysłany do luku",
}


_STATE_TEXT = {
    "maly_tylko": "tylko mały bagaż w cenie",
    "podreczny_platny": "duży podręczny płatny",
    "podreczny_w_cenie": "duży podręczny wliczony",
}


def _label(prefix: str) -> str:
    return _FEE_LABELS.get(prefix, prefix.replace("_", " "))


def _parse_fees(doplata: dict | None) -> list[CabinFee]:
    """Normalizuje różne układy pól dopłaty w pliku (X_min/X_max, X_od_<waluta>, X_<waluta>)."""
    if not doplata:
        return []
    default_currency = doplata.get("waluta")
    fees: list[CabinFee] = []
    for key, value in doplata.items():
        if key == "waluta" or value is None:
            continue
        if key.endswith("_min"):
            prefix = key[: -len("_min")]
            fees.append(
                CabinFee(
                    _label(prefix),
                    float(value),
                    float(doplata[f"{prefix}_max"]) if doplata.get(f"{prefix}_max") is not None else None,
                    default_currency,
                )
            )
        elif key.endswith("_max"):
            continue  # obsłużone razem z _min
        elif "_od_" in key:
            prefix, currency = key.rsplit("_od_", 1)
            fees.append(CabinFee(_label(prefix), float(value), None, currency.upper(), is_from=True))
        else:
            prefix, _, currency = key.rpartition("_")
            fees.append(CabinFee(_label(prefix), float(value), None, currency.upper()))
    return fees


def _unknown(code: str | None, reason: str, entry: dict | None = None) -> CabinBaggageInfo:
    return CabinBaggageInfo(
        airline_code=code,
        state=CabinBaggageState.UNKNOWN,
        airline_name=entry["nazwa"] if entry else None,
        description=reason,
        source=(entry or {}).get("zrodlo") or (entry or {}).get("zrodlo_oficjalne_do_sprawdzenia"),
    )


def get_cabin_baggage(airline_code: str | None) -> CabinBaggageInfo:
    """Zasady bagażu podręcznego dla przewoźnika (kod IATA z Travelpayouts); zawsze zwraca
    wynik — brak danych to jawny stan NIEZNANY, nigdy zgadywanie."""
    if not airline_code:
        return _unknown(None, "Nie znamy przewoźnika tego lotu — zasad bagażu podręcznego nie podajemy.")
    code = airline_code.upper()
    entry = _DATA["przewoznicy"].get(code)
    if entry is None:
        return _unknown(code, f"Brak przewoźnika {code} w tabeli zasad bagażu podręcznego — sprawdź u przewoźnika.")
    if not entry.get("price_verified"):
        return _unknown(code, f"{entry['nazwa']}: zasady bagażu podręcznego niezweryfikowane.", entry)

    base = entry["stan_w_cenie_bazowej"]
    common = dict(
        airline_code=code,
        airline_name=entry["nazwa"],
        source=entry["zrodlo"],
        verified_on=entry["data_weryfikacji"],
        price_verified=True,
        fees_verified=bool(entry.get("doplata_potwierdzona", False)),
        extra_fees=[
            ExtraFee(e["etykieta"], e.get("kwota"), e["waluta"], e["typ"], bool(e["potwierdzona"]), e.get("uwaga", ""))
            for e in entry.get("oplaty_dodatkowe", [])
        ],
        fees_source=entry.get("zrodlo_oplaty"),
        fees_verified_on=entry.get("data_weryfikacji_oplat"),
    )

    if base == "zalezy_od_taryfy":
        parts = [f"{name}: {t.get('uwaga') or _STATE_TEXT.get(t['stan'], t['stan'])}" for name, t in entry["taryfy"].items()]
        return CabinBaggageInfo(
            state=CabinBaggageState.UNKNOWN,
            description=(
                f"{entry['nazwa']}: zasada zależy od taryfy, a tej nie znamy z ceny biletu. "
                + " | ".join(parts)
                + (f". {entry['uwaga']}" if entry.get("uwaga") else "")
            ),
            **common,
        )

    big = entry.get("podreczny") or {}
    if base == "podreczny_w_cenie":
        dims = "×".join(str(d) for d in big.get("wymiary_cm", []))
        weight = f", do {big['waga_kg']} kg" if big.get("waga_kg") else ""
        return CabinBaggageInfo(
            state=CabinBaggageState.INCLUDED,
            description=f"{entry['nazwa']}: bagaż podręczny ({dims} cm{weight}) wliczony w cenę.",
            **common,
        )
    if base == "podreczny_platny":
        fees = _parse_fees(big.get("doplata"))
        small = entry.get("maly") or {}
        small_txt = f" Mały bagaż pod fotel ({'×'.join(str(d) for d in small['wymiary_cm'])} cm) w cenie." if small.get("wymiary_cm") else ""
        higher = " ".join(
            f"{name}: {t['uwaga']}" for name, t in entry.get("taryfy", {}).items() if t.get("stan") == "podreczny_w_cenie"
        )
        return CabinBaggageInfo(
            state=CabinBaggageState.PAID,
            description=(
                f"{entry['nazwa']}: w taryfie podstawowej duży bagaż podręczny jest płatny.{small_txt}"
                + (f" {higher}" if higher else "")
                + (f" {entry['doplata_opis']}" if entry.get("doplata_opis") else "")
            ),
            fees=fees,
            **common,
        )
    return _unknown(code, f"{entry['nazwa']}: nierozpoznany stan bagażu ({base}).", entry)


_STATE_ICON = {
    CabinBaggageState.INCLUDED.value: "wliczony",
    CabinBaggageState.PAID.value: "PŁATNY",
    CabinBaggageState.UNKNOWN.value: "NIEZNANY",
}


def format_breakdown(info: dict) -> str:
    """Czytelny opis stanu bagażu podręcznego z breakdown["bagaz_podreczny"] (UI / demo)."""
    parts = [f"Bagaż podręczny: {_STATE_ICON.get(info['stan'], info['stan'])}."]
    if info["stan"] == CabinBaggageState.PAID.value and info["oplaty"]:
        tag = (" (oficjalny PRZEDZIAŁ, konkretna cena zależy od trasy i daty)" if info.get("oplaty_potwierdzone")
               else " ORIENTACYJNA, NIEPOTWIERDZONA (cena dynamiczna)")
        parts.append(f"Dopłata{tag} (waluta przewoźnika, bez przeliczenia, NIE wliczona w cenę łączną): "
                     + "; ".join(f["tekst"] for f in info["oplaty"]) + ".")
    if info.get("oplaty_dodatkowe"):
        parts.append("Inne opłaty bagażowe (waluta przewoźnika, bez przeliczenia): "
                     + "; ".join(e["tekst"] for e in info["oplaty_dodatkowe"]) + ".")
        if info.get("zrodlo_oplat") and info.get("data_weryfikacji_oplat"):
            parts.append(f"Źródło opłat: {info['zrodlo_oplat']} (stan na {info['data_weryfikacji_oplat']}).")
    if info["opis"]:
        parts.append(info["opis"])
    if info.get("zrodlo") and info.get("data_weryfikacji"):
        parts.append(f"Źródło: {info['zrodlo']} (stan na {info['data_weryfikacji']}).")
    return " ".join(parts)
