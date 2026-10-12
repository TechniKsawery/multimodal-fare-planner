"""Ostrzeżenia informacyjne: czy zaznaczona ulga realnie przysługuje cudzoziemcowi.

Nie zmienia ceny — tylko generuje czytelne dla użytkownika ostrzeżenia na podstawie
profilu.obywatelstwo i zaznaczonych ulg, wg reguł zweryfikowanych 2026-10-10 (dwa niezależne
źródła na regułę, zob. pamięć projektu [[zagraniczne-legitymacje-transport-status]] i
[[senior-niepelnosprawnosc-transport-status]]). Gdzie reguła nie została zweryfikowana wprost,
NIE generujemy ostrzeżenia (lepiej żadne niż zgadywane).
"""

from .model import DiscountProfile

_PKP_KODY_STUDENCKIE = {
    "dzieci_mlodziez_szkolna_do_24_lat",
    "student_do_26_lat_doktorant_do_35_lat",
}


def warnings_for(profile: DiscountProfile) -> list[str]:
    """Zwraca listę ostrzeżeń dla zaznaczonych ulg, jeśli obywatelstwo wpływa na ich dostępność."""
    cudzoziemiec = profile.obywatelstwo not in (None, "PL")
    if not cudzoziemiec and not profile.legitymacja_zagraniczna:
        return []

    warnings: list[str] = []
    poza_ue = profile.obywatelstwo == "poza_UE"

    if cudzoziemiec and profile.pkp_ulga_kod in _PKP_KODY_STUDENCKIE:
        if poza_ue:
            warnings.append(
                "PKP Intercity: ulga ustawowa dla uczniów/studentów NIE obejmuje obywateli"
                " spoza UE (rozporządzenie MI z 20.04.2017) — ta zniżka najpewniej nie zostanie"
                " przyznana przy kontroli biletów."
            )
        else:
            warnings.append(
                "PKP Intercity: ulga ustawowa dla uczniów/studentów wymaga od obywateli UE"
                " (innych niż PL) ważnej karty pobytu w Polsce (rozporządzenie MI z 20.04.2017)."
            )

    # Ostrzeżenia o uznawaniu legitymacji dotyczą wyłącznie legitymacji ZAGRANICZNEJ —
    # niezależnie od obywatelstwa (cudzoziemiec z polską legitymacją ich nie dostaje).
    zagraniczna = profile.legitymacja_zagraniczna

    if zagraniczna and profile.ztm_warszawa_ulgowy:
        warnings.append(
            "Warszawa (WTP): zagraniczna legitymacja szkolna/studencka jest uznawana do 26 lat,"
            " ale TYLKO do ulgi 50% — nigdy do przejazdu bezpłatnego."
        )

    if zagraniczna and profile.mpk_krakow_ulgowy:
        warnings.append(
            "Kraków (ZTP): zagraniczna legitymacja jest uznawana do ulgi 50%, ale wymagana jest"
            " konkretnie karta ISIC — inna zagraniczna legitymacja szkolna może nie wystarczyć."
        )

    if zagraniczna and profile.ztm_poznan_ulgowy:
        warnings.append(
            "Poznań (ZTM): zagraniczne legitymacje szkolne/studenckie NIE są uznawane — szkoła"
            " musi być fizycznie w Poznaniu."
        )

    if zagraniczna and profile.ztm_lublin_ulgowy:
        warnings.append(
            "Lublin (ZDiTM): ulga studencka wymaga legitymacji wydanej przez POLSKĄ szkołę"
            " wyższą — zagraniczna legitymacja studencka nie uprawnia do tej zniżki."
        )

    if zagraniczna and profile.mpk_wroclaw_ulgowy:
        warnings.append(
            "Wrocław (MPK): zagraniczna legitymacja szkolna jest uznawana, ale wymaga"
            " tłumaczenia przez tłumacza przysięgłego — chyba że masz ISIC/Euro26 (wtedy bez"
            " tłumaczenia)."
        )

    if cudzoziemiec and (profile.bvg_berlin_ulgowy or profile.vrr_dziecko):
        warnings.append(
            "Niemcy (BVG/VBB, VRR): brak ulgi studenckiej na pojedynczy przejazd niezależnie od"
            " obywatelstwa — zniżka działa tylko przez Semesterticket przy faktycznym zapisie na"
            " niemiecką uczelnię, nie przez samą legitymację z innego kraju."
        )

    return warnings
