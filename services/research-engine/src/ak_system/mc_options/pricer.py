from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt

import numpy as np
from scipy.stats import norm


EPS_T = 1e-6
EPS_SIG = 1e-6


@dataclass
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta_daily: float


def _d1_d2(S: float, K: float, r: float, q: float, sigma: float, T: float) -> tuple[float, float]:
    T = max(T, EPS_T)
    sigma = max(sigma, EPS_SIG)
    d1 = (log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return d1, d2


def bs_price(S: float, K: float, r: float, q: float, sigma: float, T: float, option_type: str) -> float:
    T = max(T, EPS_T)
    sigma = max(sigma, EPS_SIG)
    d1, d2 = _d1_d2(S, K, r, q, sigma, T)
    df_r = exp(-r * T)
    df_q = exp(-q * T)

    if option_type.lower() == "call":
        return S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
    if option_type.lower() == "put":
        return K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)
    raise ValueError("option_type must be call or put")


def bs_greeks(S: float, K: float, r: float, q: float, sigma: float, T: float, option_type: str) -> Greeks:
    T = max(T, EPS_T)
    sigma = max(sigma, EPS_SIG)
    d1, d2 = _d1_d2(S, K, r, q, sigma, T)
    df_r = exp(-r * T)
    df_q = exp(-q * T)
    pdf = norm.pdf(d1)

    if option_type.lower() == "call":
        delta = df_q * norm.cdf(d1)
        theta = (
            -S * df_q * pdf * sigma / (2 * sqrt(T))
            - r * K * df_r * norm.cdf(d2)
            + q * S * df_q * norm.cdf(d1)
        )
    elif option_type.lower() == "put":
        delta = df_q * (norm.cdf(d1) - 1)
        theta = (
            -S * df_q * pdf * sigma / (2 * sqrt(T))
            + r * K * df_r * norm.cdf(-d2)
            - q * S * df_q * norm.cdf(-d1)
        )
    else:
        raise ValueError("option_type must be call or put")

    gamma = df_q * pdf / (S * sigma * sqrt(T))
    vega = S * df_q * pdf * sqrt(T)

    return Greeks(delta=float(delta), gamma=float(gamma), vega=float(vega), theta_daily=float(theta / 365.0))


def put_call_parity_gap(S: float, K: float, r: float, q: float, sigma: float, T: float) -> float:
    call = bs_price(S, K, r, q, sigma, T, "call")
    put = bs_price(S, K, r, q, sigma, T, "put")
    lhs = call - put
    rhs = S * exp(-q * max(T, EPS_T)) - K * exp(-r * max(T, EPS_T))
    return lhs - rhs
