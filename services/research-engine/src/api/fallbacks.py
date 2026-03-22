from __future__ import annotations

import numpy as np

from ak_system.mc_options.calibration import ChainSnapshot


def demo_chain_snapshot(symbol: str = 'SPY') -> ChainSnapshot:
    spot = 600.0
    strikes = np.array([585, 590, 595, 600, 605, 610, 615], dtype=float)
    ivs = np.array([0.23, 0.235, 0.242, 0.25, 0.255, 0.261, 0.268], dtype=float)
    expiries_days = np.array([7, 7, 7, 7, 7, 7, 7], dtype=float)
    returns = np.array([0.001] * 30, dtype=float)
    return ChainSnapshot(spot=spot, strikes=strikes, ivs=ivs, expiries_days=expiries_days, returns=returns)
