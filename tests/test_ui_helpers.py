
from streamlit.testing.v1 import AppTest



def _app():
    from datetime import datetime
    from types import SimpleNamespace

    from fares.model import Carrier
    from ui_helpers import render_bezplatne_info

    def pl(carrier, bd, a, b):
        leg = SimpleNamespace(origin_name=a, destination_name=b)
        return SimpleNamespace(leg=leg, carrier=carrier, breakdown=bd)

    it = SimpleNamespace(
        legs=[
            pl(Carrier.ZTM_POZNAN, {"typ_biletu": "bezpłatny (100%)"}, "Półwiejska", "Dworzec"),
            pl(Carrier.ZTM_WARSZAWA, {"typ_biletu": "ulgowy (50%)"}, "Centralny", "Wola"),
            pl(Carrier.FLIXBUS, {}, "Poznań", "Warszawa"),
            pl(None, {}, "x", "y"),
        ]
    )
    render_bezplatne_info(it)


def test_render_bezplatne_info_komunikaty_i_expander():
    at = AppTest.from_function(_app).run()
    assert not at.exception
    assert len(at.success) == 2
    assert "bezpłatny" in at.success[0].value and "Półwiejska" in at.success[0].value
    assert len(at.expander) == 1
    md = " ".join(m.value for m in at.expander[0].markdown)
    assert "Poznań" in md and "Warszawa" in md
