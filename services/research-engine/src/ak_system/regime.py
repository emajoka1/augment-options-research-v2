from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

TrendLabel = Literal["trend", "mean_revert"]
VolLabel = Literal["vol_expanding", "vol_contracting"]


@dataclass(frozen=True)
class RegimeLabel:
    trend: TrendLabel
    vol: VolLabel

    @property
    def key(self) -> str:
        return f"{self.trend}|{self.vol}"


def classify_regime_rule_based(prices: np.ndarray, vol_proxy: np.ndarray, lookback: int = 20) -> RegimeLabel:
    """Classify regime from recent prices and volatility proxy.

    - trend vs mean_revert: slope and lag-1 autocorrelation on returns.
    - vol expanding/contracting: short vol MA vs long vol MA.
    """
    if len(prices) < lookback + 5 or len(vol_proxy) < lookback + 5:
        return RegimeLabel("mean_revert", "vol_contracting")

    returns = np.diff(np.log(prices[-(lookback + 1) :]))
    x = np.arange(len(returns))
    slope = np.polyfit(x, returns, 1)[0]

    r0 = returns[:-1]
    r1 = returns[1:]
    if len(r0) < 2:
        acf1 = 0.0
    else:
        acf1 = float(np.corrcoef(r0, r1)[0, 1])
        if np.isnan(acf1):
            acf1 = 0.0

    trend = "trend" if (slope > 0 and acf1 > 0) or (abs(slope) > 5e-5 and acf1 >= 0) else "mean_revert"

    v_short = float(np.mean(vol_proxy[-10:]))
    v_long = float(np.mean(vol_proxy[-lookback:]))
    vol = "vol_expanding" if v_short > v_long * 1.05 else "vol_contracting"

    return RegimeLabel(trend=trend, vol=vol)
