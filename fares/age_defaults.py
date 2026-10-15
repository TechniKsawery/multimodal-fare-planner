"""Domyślne ulgi wyprowadzane z wieku pasażera.

Wspólna funkcja dla UI (app.py) i API (api/main.py), żeby ten sam profil
dawał ten sam wynik (research/audyt-calosci.md §2a, luki 1 i 3).

Zasady:
- Dla dziecka domyślna ulga PKP wynika z wieku według kodów i progów ze źródłem w repo:
  * wiek <= 4: "dzieci_do_4_lat" (100% rabatu, cennik i tabela ulg PKP IC)
  * 4 < wiek < 18: "dzieci_mlodziez_szkolna_do_24_lat" (37% rabatu, tabela ulg PKP IC)
  * wiek >= 18: "brak"
- Studenta i seniora NIE przypisujemy z samego wieku (student wymaga ważnej legitymacji,
  senior w PKP to 2 przejazdy w roku z zaświadczeniem). Użytkownik wybiera je jawnie.
- Ulgi miejskie ulgowe / dziecięce:
  * ZTM Lublin: wiek < 18 (ulgowy), wiek >= 65 lub wiek <= 14 (bezpłatny)
  * ZTM Warszawa: wiek < 18 (ulgowy), wiek >= 70 (bezpłatny)
  * MPK Kraków: wiek < 18 (ulgowy), wiek >= 70 (bezpłatny)
  * ZTM Poznań: wiek < 18 (ulgowy), wiek >= 70 (bezpłatny)
  * MPK Wrocław: wiek < 18 (ulgowy), wiek <= 7 lub wiek <= 21 lub wiek >= 65 (bezpłatny)
  * BVG Berlin: wiek < 18 (ulgowy)
  * VRR, HVV, MVV, VRS: 6 <= wiek <= 14 (Kindertarif / dziecko)
"""

from typing import Any


def default_discounts_for_age(age: int | None) -> dict[str, Any]:
    """Zwraca słownik domyślnych wartości ulg dla podanego wieku."""
    if age is None:
        return {
            "pkp_ulga_kod": "brak",
            "ztm_lublin_ulgowy": False,
            "ztm_lublin_bezplatny": False,
            "ztm_warszawa_ulgowy": False,
            "ztm_warszawa_bezplatny": False,
            "mpk_krakow_ulgowy": False,
            "mpk_krakow_bezplatny": False,
            "ztm_poznan_ulgowy": False,
            "ztm_poznan_bezplatny": False,
            "mpk_wroclaw_ulgowy": False,
            "mpk_wroclaw_bezplatny": False,
            "bvg_berlin_ulgowy": False,
            "vrr_dziecko": False,
            "hvv_dziecko": False,
            "mvv_dziecko": False,
            "vrs_koln_dziecko": False,
        }

    if age <= 4:
        pkp_ulga = "dzieci_do_4_lat"
    elif age < 18:
        pkp_ulga = "dzieci_mlodziez_szkolna_do_24_lat"
    else:
        pkp_ulga = "brak"

    return {
        "pkp_ulga_kod": pkp_ulga,
        "ztm_lublin_ulgowy": age < 18,
        "ztm_lublin_bezplatny": age >= 65 or age <= 14,
        "ztm_warszawa_ulgowy": age < 18,
        "ztm_warszawa_bezplatny": age >= 70,
        "mpk_krakow_ulgowy": age < 18,
        "mpk_krakow_bezplatny": age >= 70,
        "ztm_poznan_ulgowy": age < 18,
        "ztm_poznan_bezplatny": age >= 70,
        "mpk_wroclaw_ulgowy": age < 18,
        "mpk_wroclaw_bezplatny": age <= 7 or age <= 21 or age >= 65,
        "bvg_berlin_ulgowy": age < 18,
        "vrr_dziecko": 6 <= age <= 14,
        "hvv_dziecko": 6 <= age <= 14,
        "mvv_dziecko": 6 <= age <= 14,
        "vrs_koln_dziecko": 6 <= age <= 14,
    }
