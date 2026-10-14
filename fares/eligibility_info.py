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
            "dzieci do 30.09 roku ukończenia 7 lat",
            "uczniowie szkół podstawowych (Karta Ucznia; ponadpodstawowe NIE)",
            "osoby 70+ (bez wymogu zamieszkania)",
            "niepełnosprawność znaczna 26+",
        ],
        [
            "dzieci od 1.10 roku ukończenia 7 lat do 16 lat",
            "studenci",
            "emeryci/renciści do 70 lat",
            "niepełnosprawność umiarkowana 26+",
        ],
        "https://www.wtp.waw.pl/ulgi-znizki/",
    ),
    Carrier.MPK_KRAKOW: (
        "Kraków",
        [
            "dzieci do 30.09 roku ukończenia 7 lat",
            "uczniowie szkół podstawowych z Krakowa/Metropolii (ponadpodstawowe NIE)",
            "osoby 70+ (bez wymogu zamieszkania)",
            "niepełnosprawność znaczna",
        ],
        ["dzieci od 1.10 roku ukończenia 7 lat do 16 lat"],
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
        [
            "dzieci do 30.09 roku ukończenia 7 lat",
            "uczniowie szkół podstawowych (gmina Lublin; ponadpodstawowe NIE)",
            "osoby 65+",
        ],
        [
            "uczniowie podstawowych/ponadpodstawowych/policealnych do 24 lat",
            "doktoranci",
            "uczniowie i studenci szkół zagranicznych do 26 lat z kartą ISIC",
            "emeryci",
        ],
        "https://zdtm.lublin.eu/pl/ulgi-w-przejazdach/33.html",
    ),
    Carrier.ZTM_POZNAN: (
        "Poznań",
        [
            "dzieci do 30.09 roku ukończenia 7 lat",
            "osoby 70+ (bez wymogu zamieszkania)",
            "niepełnosprawność znaczna / I grupa",
        ],
        [
            "uczniowie (w Poznaniu NIE jeżdżą bezpłatnie)",
            "dzieci od 1.10 roku ukończenia 7 lat do 18 lat",
        ],
        "https://www.ztm.poznan.pl/wszystko-o-biletach/ulgi-i-zwolnienia/",
    ),
    Carrier.BVG_BERLIN: (
        "Berlin",
        [
            "dzieci do 6 lat",
            "Schwerbehindertenausweis (G/aG/H/Bl) + osobno wykupiona Wertmarke",
        ],
        ["dzieci 6-14 lat (Ermäßigungstarif)"],
        "https://www.vbb.de",
    ),
    Carrier.VRR: (
        "VRR (NRW)",
        ["dzieci do 6 lat"],
        ["dzieci 6-14 lat (Kindertarif)"],
        "https://eezy.nrw/hilfe/so-funktioniert-eezy-nrw",
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
