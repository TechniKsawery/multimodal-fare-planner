"""Pilnuje, żeby każde pole *_bezplatny / *_ulgowy / *_dziecko / *_schwerbehindert(e) profilu ulg
miało swój checkbox w app.py (przekazany do DiscountProfile(...)) i pole w API (DiscountProfileIn).
Bez tego kalkulator zna ulgę, ale nikt w UI nie może jej zaznaczyć."""

import ast
import dataclasses
from pathlib import Path

from api.schemas import DiscountProfileIn
from fares.model import DiscountProfile

SUFFIXES = ("_bezplatny", "_ulgowy", "_dziecko", "_schwerbehindert")
ROOT = Path(__file__).resolve().parent.parent


def _bool_flag_fields() -> set[str]:
    names = {f.name for f in dataclasses.fields(DiscountProfile)}
    return {n for n in names if n.endswith(SUFFIXES) or n.startswith("schwerbehinderte_")}


def _app_profile_kwargs() -> dict[str, ast.expr]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "DiscountProfile"
        ):
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    raise AssertionError("app.py nie tworzy DiscountProfile(...)")


def test_flag_fields_detected():
    assert len(_bool_flag_fields()) >= 15


def test_every_flag_has_checkbox_in_app():
    kwargs = _app_profile_kwargs()
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    missing = []
    for name in sorted(_bool_flag_fields()):
        value = kwargs.get(name)
        if value is None:
            missing.append(f"{name}: brak w DiscountProfile(...) w app.py")
            continue
        # wartość to zmienna z checkboxa: musi być przypisana z .checkbox(...) w app.py
        var = getattr(value, "id", None)
        if not var or f"{var} = " not in src or ".checkbox(" not in src.split(f"{var} = ", 1)[1].split("\n", 1)[0]:
            missing.append(f"{name}: wartość nie pochodzi bezpośrednio z checkboxa ({var})")
    assert not missing, "Pola profilu ulg bez checkboxa w UI:\n" + "\n".join(missing)


def test_every_flag_in_api_schema():
    api_fields = set(DiscountProfileIn.model_fields)
    assert _bool_flag_fields() <= api_fields, sorted(_bool_flag_fields() - api_fields)


def test_child_with_guardian_in_app_and_api():
    assert "child_with_guardian" in DiscountProfileIn.model_fields
    kwargs = _app_profile_kwargs()
    assert "child_with_guardian" in kwargs
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "child_with_guardian = (" in src
    assert "st.checkbox(" in src.split("child_with_guardian = (", 1)[1].split("if 6 <= wiek <= 14", 1)[0]

