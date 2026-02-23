from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .pricer import bs_price


@dataclass
class RepriceRequest:
    strike: float
    option_type: str
    r: float
    q: float
    iv: float
    expiry_years: float


def reprice_option_path(path: np.ndarray, req: RepriceRequest, dt: float) -> np.ndarray:
    n_steps = len(path) - 1
    prices = np.zeros(n_steps + 1, dtype=float)
    for t in range(n_steps + 1):
        T = max(req.expiry_years - t * dt, 1e-6)
        prices[t] = bs_price(
            S=float(path[t]),
            K=req.strike,
            r=req.r,
            q=req.q,
            sigma=req.iv,
            T=T,
            option_type=req.option_type,
        )
    return prices
