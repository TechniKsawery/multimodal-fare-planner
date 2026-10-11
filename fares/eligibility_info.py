"""Zweryfikowane tytuły do przejazdów bezpłatnych/ulgowych w komunikacji miejskiej, per przewoźnik.

Treść pochodzi WYŁĄCZNIE z tego, co już jest potwierdzone w fares/data/*.json (pola `_zrodlo_*`)
i w opisach checkboxów app.py. Niczego tu nie zgadujemy — nowy tytuł dodawaj dopiero po
weryfikacji źródła.
"""

from .model import Carrier

_WERTMARKE = "Ciężka niepełnosprawność (Merkzeichen G/aG/H/Bl/Gl) z ważną Wertmarke — § 228 SGB IX"

# carrier -> (nazwa miasta, [tytuły bezpłatne], [tytuły ulgowe 50%], źródło)
ELIGIBILITY: dict[Carrier, tuple[str, list[str], list[str], str]] = {
    Carrier.ZTM_WARSZAWA: (
        "Warszawa",
        [
            "uczniowie szkół podstawowych (Karta Ucznia; ponadpodstawowe NIE)",
            "osoby 70+ (bez wymogu zamieszkania)",
            "niepełnosprawność znaczna 26+",
        ],
        ["studenci", "emeryci/renciści do 70 lat", "niepełnosprawność umiarkowana 26+"],
        "https://www.wtp.waw.pl/ulgi-znizki/",
    ),
    Carrier.MPK_KRAKOW: (
        "Kraków",
        [
            "uczniowie szkół podstawowych z Krakowa/Metropolii (ponadpodstawowe NIE)",
            "osoby 70+ (bez wymogu zamieszkania)",
            "niepełnosprawność znaczna",
        ],
        [],
        "https://ztp.krakow.pl/kmk/przewodnik-po-biletach-kmk",
    ),
    Carrier.MPK_WROCLAW: (
        "Wrocław",
        [
            "uczniowie szkół podstawowych i ponadpodstawowych do 21 lat",
            "dzieci do 7 lat",
            "seniorzy 65+ (bez wymogu zamieszkania)",
        ],
        ["studenci i doktoranci", "uczniowie szkół policealnych"],
        "https://www.wroclaw.pl/komunikacja/uprawnienia-do-ulg",
    ),
    Carrier.ZTM_LUBLIN: (
        "Lublin",
        ["uczniowie szkół podstawowych (gmina Lublin; ponadpodstawowe NIE)"],
        [],
        "https://zdtm.lublin.eu/pl/ulgi-w-przejazdach/33.html",
    ),
    Carrier.ZTM_POZNAN: (
        "Poznań",
        ["osoby 70+ (bez wymogu zamieszkania)", "niepełnosprawność znaczna / I grupa"],
        ["uczniowie (w Poznaniu NIE jeżdżą bezpłatnie)"],
        "https://www.ztm.poznan.pl/wszystko-o-biletach/ulgi-i-zwolnienia/",
    ),
    Carrier.BVG_BERLIN: (
        "Berlin",
        ["Schwerbehindertenausweis (G/aG/H/Bl) + osobno wykupiona Wertmarke"],
        ["dzieci 6-14 lat (Ermäßigungstarif)"],
        "https://www.vbb.de",
    ),
    Carrier.HVV: ("Hamburg", [_WERTMARKE, "dzieci do 6 lat"], ["dzieci 6-14 lat"], "https://www.hvv.de"),
    Carrier.MVV: (
        "Monachium",
        [_WERTMARKE, "dzieci do 6 lat"],
        ["dzieci 6-14 lat"],
        "https://www.mvv-muenchen.de/tickets-abos-preise/einzelfahrkarte",
    ),
    Carrier.VRS_KOLN: (
        "Kolonia",
        [_WERTMARKE, "dzieci do 6 lat"],
        [],
        "https://www.vrs.de/tickets/ticketsortiment/einzelticket",
    ),
}


def eligibility_for(carrier: Carrier):
    """(miasto, bezpłatne, ulgowe, źródło) albo None, gdy przewoźnik nie ma wpisu."""
    return ELIGIBILITY.get(carrier)


def explain_ticket(breakdown: dict) -> str | None:
    """Dlaczego cena wyszła 0/ulgowa — z `typ_biletu` kalkulatora; None dla zwykłej ceny."""
    typ = str(breakdown.get("typ_biletu", ""))
    if typ.startswith("bezpłatny"):
        return f"Przejazd bezpłatny — {typ}. Wynika z zaznaczonego tytułu w formularzu."
    if typ.startswith("ulgowy") or "dziecko" in typ:
        return f"Bilet ulgowy — {typ}. Wynika z zaznaczonego tytułu w formularzu."
    return None
