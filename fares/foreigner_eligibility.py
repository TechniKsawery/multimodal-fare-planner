"""Ostrzeżenia informacyjne: czy zaznaczona ulga realnie przysługuje cudzoziemcowi.

Nie zmienia ceny — tylko generuje czytelne dla użytkownika ostrzeżenia na podstawie
profilu.obywatelstwo i zaznaczonych ulg, wg reguł zweryfikowanych 2026-10-10 (dwa niezależne
źródła na regułę, zob. pamięć projektu [[zagraniczne-legitymacje-transport-status]] i
[[senior-niepelnosprawnosc-transport-status]]). Gdzie reguła nie została zweryfikowana wprost,
NIE generujemy ostrzeżenia (lepiej żadne niż zgadywane).
"""

from i18n import Msg

from .model import DiscountProfile

_PKP_KODY_STUDENCKIE = {
    "dzieci_mlodziez_szkolna_do_24_lat",
    "student_do_26_lat_doktorant_do_35_lat",
}


def warnings_for(profile: DiscountProfile) -> list[Msg]:
    """Zwraca listę ostrzeżeń dla zaznaczonych ulg, jeśli obywatelstwo wpływa na ich dostępność.
    Elementy to `i18n.Msg` (polski tekst + klucz do renderu w innym języku przez `tm`)."""
    cudzoziemiec = profile.obywatelstwo not in (None, "PL")
    if not cudzoziemiec and not profile.legitymacja_zagraniczna:
        return []

    warnings: list[Msg] = []
    poza_ue = profile.obywatelstwo == "poza_UE"

    if cudzoziemiec and profile.pkp_ulga_kod in _PKP_KODY_STUDENCKIE:
        if poza_ue:
            warnings.append(Msg("foreign.pkp_non_eu"))
        else:
            warnings.append(Msg("foreign.pkp_eu"))

    # Ostrzeżenia o uznawaniu legitymacji dotyczą wyłącznie legitymacji ZAGRANICZNEJ —
    # niezależnie od obywatelstwa (cudzoziemiec z polską legitymacją ich nie dostaje).
    zagraniczna = profile.legitymacja_zagraniczna

    if zagraniczna and profile.ztm_warszawa_ulgowy:
        warnings.append(Msg("foreign.warsaw"))

    if zagraniczna and profile.mpk_krakow_ulgowy:
        warnings.append(Msg("foreign.krakow"))

    if zagraniczna and profile.ztm_poznan_ulgowy:
        warnings.append(Msg("foreign.poznan"))

    if zagraniczna and profile.ztm_lublin_ulgowy:
        warnings.append(Msg("foreign.lublin"))

    if zagraniczna and profile.mpk_wroclaw_ulgowy:
        warnings.append(Msg("foreign.wroclaw"))

    if cudzoziemiec and (profile.bvg_berlin_ulgowy or profile.vrr_dziecko):
        warnings.append(Msg("foreign.germany"))

    return warnings
