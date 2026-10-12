"""Dispatch do kalkulatora właściwego dla przewoźnika w segmencie."""

from . import (
    bvg_berlin,
    db,
    flixbus,
    hvv,
    international,
    kvb,
    mpk_krakow,
    mpk_wroclaw,
    mvv,
    pkp,
    vrr,
    ztm_lublin,
    ztm_poznan,
    ztm_warszawa,
)
from .model import Carrier, PriceEstimate, Segment

_CALCULATORS = {
    Carrier.PKP_INTERCITY: pkp.estimate,
    Carrier.DB: db.estimate,
    Carrier.VRR: vrr.estimate,
    Carrier.FLIXBUS: flixbus.estimate,
    Carrier.ZTM_LUBLIN: ztm_lublin.estimate,
    Carrier.ZTM_WARSZAWA: ztm_warszawa.estimate,
    Carrier.MPK_KRAKOW: mpk_krakow.estimate,
    Carrier.ZTM_POZNAN: ztm_poznan.estimate,
    Carrier.MPK_WROCLAW: mpk_wroclaw.estimate,
    Carrier.BVG_BERLIN: bvg_berlin.estimate,
    Carrier.HVV: hvv.estimate,
    Carrier.MVV: mvv.estimate,
    Carrier.VRS_KOLN: kvb.estimate,
    Carrier.INTERNATIONAL_PL_DE: international.estimate,
}


def estimate_price(segment: Segment) -> PriceEstimate:
    calc = _CALCULATORS.get(segment.carrier)
    if calc is None:
        raise ValueError(f"brak kalkulatora dla przewoźnika: {segment.carrier}")
    return calc(segment)
