from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import numpy as np

from .pricer import bs_price

OptionType = Literal["call", "put"]
Side = Literal["long", "short"]


@dataclass
class Leg:
    side: Side
    option_type: OptionType
    strike: float
    qty: int = 1


@dataclass
class StrategyDef:
    name: str
    legs: List[Leg]
    expiry_years: float


@dataclass
class ExitRules:
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None
    dte_stop_days: float | None = None
    iv_shift_stop: float | None = None


def make_long_straddle(K: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        name="long_straddle",
        expiry_years=expiry_years,
        legs=[
            Leg("long", "call", K, qty),
            Leg("long", "put", K, qty),
        ],
    )


def make_vertical(option_type: OptionType, long_strike: float, short_strike: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        name=f"{option_type}_vertical",
        expiry_years=expiry_years,
        legs=[Leg("long", option_type, long_strike, qty), Leg("short", option_type, short_strike, qty)],
    )


def make_iron_fly(center: float, wing: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        name="iron_fly",
        expiry_years=expiry_years,
        legs=[
            Leg("short", "call", center, qty),
            Leg("short", "put", center, qty),
            Leg("long", "call", center + wing, qty),
            Leg("long", "put", center - wing, qty),
        ],
    )


def make_iron_condor(short_put: float, long_put: float, short_call: float, long_call: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        name="iron_condor",
        expiry_years=expiry_years,
        legs=[
            Leg("short", "put", short_put, qty),
            Leg("long", "put", long_put, qty),
            Leg("short", "call", short_call, qty),
            Leg("long", "call", long_call, qty),
        ],
    )


def strategy_mid_value(strategy: StrategyDef, S: float, r: float, q: float, tau: float, iv_by_strike: dict[float, float]) -> float:
    total = 0.0
    for leg in strategy.legs:
        iv = float(iv_by_strike[leg.strike])
        p = bs_price(S, leg.strike, r, q, iv, max(tau, 1e-6), leg.option_type)
        sign = 1.0 if leg.side == "long" else -1.0
        total += sign * leg.qty * p
    return total


def max_profit_max_loss(strategy: StrategyDef, S_grid: np.ndarray, r: float, q: float, iv_by_strike: dict[float, float], entry_value: float) -> tuple[float, float]:
    payoffs = []
    for s in S_grid:
        payoff = strategy_mid_value(strategy, s, r, q, tau=1e-6, iv_by_strike=iv_by_strike) - entry_value
        payoffs.append(payoff)
    payoffs = np.array(payoffs)
    return float(np.max(payoffs)), float(np.min(payoffs))


def should_exit(current_pnl: float, entry_debit_or_credit: float, dte_days: float, iv_shift: float, rules: ExitRules, is_short_premium: bool) -> bool:
    # For short premium, take profit is % of credit captured (positive pnl).
    if rules.take_profit_pct is not None and entry_debit_or_credit > 0:
        tp_target = rules.take_profit_pct * abs(entry_debit_or_credit)
        if current_pnl >= tp_target:
            return True

    if rules.stop_loss_pct is not None and entry_debit_or_credit > 0:
        sl_limit = -rules.stop_loss_pct * abs(entry_debit_or_credit)
        if current_pnl <= sl_limit:
            return True

    if rules.dte_stop_days is not None and dte_days <= rules.dte_stop_days:
        return True

    if rules.iv_shift_stop is not None and abs(iv_shift) >= rules.iv_shift_stop:
        return True

    return False
