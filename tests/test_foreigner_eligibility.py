"""Testy ostrzeżeń dla cudzoziemców (fares/foreigner_eligibility.py) - informacyjne, nie zmieniają ceny."""

from fares.foreigner_eligibility import warnings_for
from fares.model import DiscountProfile


def test_brak_obywatelstwa_brak_ostrzezen():
    assert warnings_for(DiscountProfile()) == []


def test_obywatelstwo_pl_brak_ostrzezen():
    profile = DiscountProfile(
        obywatelstwo="PL", pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"
    )
    assert warnings_for(profile) == []


def test_pkp_ulga_studencka_poza_ue_ostrzega_o_wykluczeniu():
    profile = DiscountProfile(
        obywatelstwo="poza_UE", pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"
    )
    warnings = warnings_for(profile)
    assert len(warnings) == 1
    assert "spoza UE" in warnings[0]


def test_pkp_ulga_studencka_ue_ostrzega_o_karcie_pobytu():
    profile = DiscountProfile(
        obywatelstwo="UE", pkp_ulga_kod="student_do_26_lat_doktorant_do_35_lat"
    )
    warnings = warnings_for(profile)
    assert len(warnings) == 1
    assert "karty pobytu" in warnings[0]


def test_krakow_ulgowy_ostrzega_o_isic():
    profile = DiscountProfile(obywatelstwo="UE", mpk_krakow_ulgowy=True)
    warnings = warnings_for(profile)
    assert any("ISIC" in w for w in warnings)


def test_poznan_ulgowy_ostrzega_o_braku_uznania():
    profile = DiscountProfile(obywatelstwo="poza_UE", ztm_poznan_ulgowy=True)
    warnings = warnings_for(profile)
    assert any("NIE są uznawane" in w for w in warnings)


def test_wiele_zaznaczonych_ulg_daje_wiele_ostrzezen():
    profile = DiscountProfile(
        obywatelstwo="UE",
        ztm_warszawa_ulgowy=True,
        mpk_krakow_ulgowy=True,
        ztm_lublin_ulgowy=True,
    )
    assert len(warnings_for(profile)) == 3
