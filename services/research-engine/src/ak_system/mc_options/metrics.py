from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np


@dataclass
class MCResults:
    ev: float
    pop: float
    pot: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    var95: float
    cvar95: float
    tail_p1: float
    min_pl: float
    max_pl: float


def compute_metrics(pl: np.ndarray, touch_flags: np.ndarray | None = None) -> MCResults:
    pl = np.asarray(pl, dtype=float)
    wins = pl[pl > 0]
    losses = pl[pl <= 0]

    ev = float(np.mean(pl))
    pop = float(np.mean(pl > 0))
    pot = float(np.mean(touch_flags)) if touch_flags is not None else 0.0

    gross_win = float(np.sum(wins)) if wins.size else 0.0
    gross_loss = float(-np.sum(losses)) if losses.size else 0.0
    profit_factor = gross_win / gross_loss if gross_loss > 1e-12 else float("inf")

    avg_win = float(np.mean(wins)) if wins.size else 0.0
    avg_loss = float(np.mean(losses)) if losses.size else 0.0
    expectancy = pop * avg_win + (1 - pop) * avg_loss

    var95 = float(np.percentile(pl, 5))
    cvar95 = float(np.mean(pl[pl <= var95])) if np.any(pl <= var95) else var95

    return MCResults(
        ev=ev,
        pop=pop,
        pot=pot,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=float(expectancy),
        var95=var95,
        cvar95=cvar95,
        tail_p1=float(np.percentile(pl, 1)),
        min_pl=float(np.min(pl)),
        max_pl=float(np.max(pl)),
    )


def percentiles(pl: np.ndarray, q: Iterable[int] = (1, 5, 10, 25, 50, 75, 90, 95, 99)) -> dict:
    pl = np.asarray(pl, dtype=float)
    return {f"p{k}": float(np.percentile(pl, k)) for k in q}
