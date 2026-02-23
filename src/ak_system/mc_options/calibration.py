from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .iv_dynamics import IVDynamicsParams, fit_surface_from_snapshot
from .models import GBMParams, JumpDiffusionParams


@dataclass
class MarketInputs:
    spot: float
    r: float = 0.03
    q: float = 0.0


def defaults_from_market(spot: float, iv_atm: float = 0.25) -> tuple[GBMParams, JumpDiffusionParams, IVDynamicsParams]:
    gbm = GBMParams(mu=0.03, sigma=max(0.05, min(1.0, iv_atm)))
    jd = JumpDiffusionParams(mu=0.03, sigma=gbm.sigma, jump_lambda=0.25, jump_mu=-0.06, jump_sigma=0.20)
    iv = IVDynamicsParams(iv_atm=iv_atm, theta_iv=iv_atm)
    return gbm, jd, iv


def fit_iv_params_from_snapshot(spot: float, strikes: np.ndarray, ivs: np.ndarray) -> IVDynamicsParams:
    fit = fit_surface_from_snapshot(spot=spot, strikes=strikes, ivs=ivs)
    return IVDynamicsParams(iv_atm=fit["iv_atm"], skew=fit["skew"], curv=fit["curv"], theta_iv=fit["iv_atm"])
