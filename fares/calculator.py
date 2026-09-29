"""Dispatch do kalkulatora właściwego dla przewoźnika w segmencie."""
from . import db, flixbus, international, pkp, vrr, ztm_lublin
from .model import Carrier, PriceEstimate, Segment

_CALCULATORS = {
    Carrier.PKP_INTERCITY: pkp.estimate,
    Carrier.DB: db.estimate,
    Carrier.VRR: vrr.estimate,
    Carrier.FLIXBUS: flixbus.estimate,
    Carrier.ZTM_LUBLIN: ztm_lublin.estimate,
    Carrier.INTERNATIONAL_PL_DE: international.estimate,
}


def estimate_price(segment: Segment) -> PriceEstimate:
    calc = _CALCULATORS.get(segment.carrier)
    if calc is None:
        raise ValueError(f"brak kalkulatora dla przewoźnika: {segment.carrier}")
    return calc(segment)
