from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class IVDynamicsParams:
    iv_atm: float = 0.25
    theta_iv: float = 0.25
    a_iv: float = 4.0
    nu_iv: float = 0.25

    skew: float = -0.25
    theta_skew: float = -0.20
    a_skew: float = 3.0
    nu_skew: float = 0.20
    b_skew_ret: float = -2.0

    term: float = 0.00
    theta_term: float = 0.00
    a_term: float = 2.0
    nu_term: float = 0.10

    curv: float = 0.10
    iv_floor: float = 0.03
    iv_cap: float = 2.00


def fit_surface_from_snapshot(spot: float, strikes: np.ndarray, ivs: np.ndarray) -> dict:
    m = np.log(np.maximum(strikes, 1e-12) / max(spot, 1e-12))
    X = np.vstack([np.ones_like(m), m, m**2]).T
    beta, *_ = np.linalg.lstsq(X, ivs, rcond=None)
    return {
        "iv_atm": float(beta[0]),
        "skew": float(beta[1]),
        "curv": float(beta[2]),
    }


def evolve_iv_state(
    params: IVDynamicsParams,
    n_steps: int,
    dt: float,
    returns: np.ndarray,
    seed: int = 123,
) -> dict:
    rng = np.random.default_rng(seed)
    iv_atm = np.zeros(n_steps + 1)
    skew = np.zeros(n_steps + 1)
    term = np.zeros(n_steps + 1)

    iv_atm[0] = params.iv_atm
    skew[0] = params.skew
    term[0] = params.term

    for t in range(1, n_steps + 1):
        z1, z2, z3 = rng.normal(size=3)
        rt = returns[t - 1] if t - 1 < len(returns) else 0.0

        iv_atm[t] = iv_atm[t - 1] + params.a_iv * (params.theta_iv - iv_atm[t - 1]) * dt + params.nu_iv * np.sqrt(dt) * z1
        skew[t] = (
            skew[t - 1]
            + params.a_skew * (params.theta_skew - skew[t - 1]) * dt
            + params.nu_skew * np.sqrt(dt) * z2
            + params.b_skew_ret * rt
        )
        term[t] = term[t - 1] + params.a_term * (params.theta_term - term[t - 1]) * dt + params.nu_term * np.sqrt(dt) * z3

    return {"iv_atm": iv_atm, "skew": skew, "term": term}


def surface_iv(S_t: float, K: float, tau: float, iv_state: dict, t_idx: int, params: IVDynamicsParams) -> float:
    m = np.log(max(K, 1e-12) / max(S_t, 1e-12))
    term_factor = iv_state["term"][t_idx] * np.sqrt(max(tau, 1e-6))
    iv = iv_state["iv_atm"][t_idx] + iv_state["skew"][t_idx] * m + params.curv * (m**2) + term_factor
    return float(np.clip(iv, params.iv_floor, params.iv_cap))
