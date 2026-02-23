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
    expiry_years: float | None = None  # for calendars/diagonals


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
    gamma_risk_dte_days: float | None = None
    event_risk_exit: bool = False


def make_long_straddle(K: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef("long_straddle", [Leg("long", "call", K, qty), Leg("long", "put", K, qty)], expiry_years)


def make_vertical(option_type: OptionType, long_strike: float, short_strike: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(f"{option_type}_vertical", [Leg("long", option_type, long_strike, qty), Leg("short", option_type, short_strike, qty)], expiry_years)


def make_put_debit_spread(long_strike: float, short_strike: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef("put_debit_spread", [Leg("long", "put", long_strike, qty), Leg("short", "put", short_strike, qty)], expiry_years)


def make_iron_fly(center: float, wing: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        "iron_fly",
        [
            Leg("short", "call", center, qty),
            Leg("short", "put", center, qty),
            Leg("long", "call", center + wing, qty),
            Leg("long", "put", center - wing, qty),
        ],
        expiry_years,
    )


def make_iron_condor(short_put: float, long_put: float, short_call: float, long_call: float, expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        "iron_condor",
        [
            Leg("short", "put", short_put, qty),
            Leg("long", "put", long_put, qty),
            Leg("short", "call", short_call, qty),
            Leg("long", "call", long_call, qty),
        ],
        expiry_years,
    )


def make_put_calendar(strike: float, front_expiry_years: float, back_expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        "put_calendar",
        [Leg("short", "put", strike, qty, expiry_years=front_expiry_years), Leg("long", "put", strike, qty, expiry_years=back_expiry_years)],
        back_expiry_years,
    )


def make_put_diagonal(long_strike: float, short_strike: float, front_expiry_years: float, back_expiry_years: float, qty: int = 1) -> StrategyDef:
    return StrategyDef(
        "put_diagonal",
        [Leg("short", "put", short_strike, qty, expiry_years=front_expiry_years), Leg("long", "put", long_strike, qty, expiry_years=back_expiry_years)],
        back_expiry_years,
    )


def default_exit_rules_for_strategy(strategy_name: str) -> ExitRules:
    if strategy_name in {"iron_fly", "iron_condor"}:
        return ExitRules(take_profit_pct=0.50, stop_loss_pct=1.00, dte_stop_days=0.25, gamma_risk_dte_days=0.20, event_risk_exit=True)
    if strategy_name in {"put_debit_spread", "long_straddle"}:
        return ExitRules(take_profit_pct=0.70, stop_loss_pct=0.50, dte_stop_days=0.10, gamma_risk_dte_days=0.10, event_risk_exit=False)
    if strategy_name in {"put_calendar", "put_diagonal"}:
        return ExitRules(take_profit_pct=0.40, stop_loss_pct=0.60, dte_stop_days=1.0, gamma_risk_dte_days=0.50, event_risk_exit=True)
    return ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25)


def strategy_mid_value(strategy: StrategyDef, S: float, r: float, q: float, tau: float, iv_by_strike: dict[float, float], tau_by_leg: dict[int, float] | None = None) -> float:
    total = 0.0
    for idx, leg in enumerate(strategy.legs):
        iv = float(iv_by_strike[leg.strike])
        leg_tau = tau_by_leg[idx] if tau_by_leg and idx in tau_by_leg else tau
        p = bs_price(S, leg.strike, r, q, iv, max(leg_tau, 1e-6), leg.option_type)
        total += (1.0 if leg.side == "long" else -1.0) * leg.qty * p
    return total


def max_profit_max_loss(strategy: StrategyDef, S_grid: np.ndarray, r: float, q: float, iv_by_strike: dict[float, float], entry_value: float) -> tuple[float, float]:
    payoffs = [strategy_mid_value(strategy, s, r, q, tau=1e-6, iv_by_strike=iv_by_strike) - entry_value for s in S_grid]
    arr = np.array(payoffs)
    return float(np.max(arr)), float(np.min(arr))


def compute_breakevens(strategy: StrategyDef, entry_value: float) -> list[float]:
    name = strategy.name
    v = abs(entry_value)
    if name == "long_straddle":
        k = strategy.legs[0].strike
        return [float(k - v), float(k + v)]
    if name == "iron_fly":
        center = [l.strike for l in strategy.legs if l.side == "short"]
        if center:
            k = float(center[0])
            return [float(k - v), float(k + v)]
    if name in {"put_debit_spread", "call_vertical", "put_vertical"} or name.endswith("_vertical"):
        longs = [l for l in strategy.legs if l.side == "long"]
        if longs:
            l0 = longs[0]
            return [float(l0.strike + v)] if l0.option_type == "call" else [float(l0.strike - v)]
    return []


def should_exit(
    current_pnl: float,
    entry_debit_or_credit: float,
    dte_days: float,
    iv_shift: float,
    rules: ExitRules,
    is_short_premium: bool,
    event_risk_high: bool = False,
) -> bool:
    if rules.take_profit_pct is not None and entry_debit_or_credit > 0 and current_pnl >= rules.take_profit_pct * abs(entry_debit_or_credit):
        return True
    if rules.stop_loss_pct is not None and entry_debit_or_credit > 0 and current_pnl <= -rules.stop_loss_pct * abs(entry_debit_or_credit):
        return True
    if rules.dte_stop_days is not None and dte_days <= rules.dte_stop_days:
        return True
    if rules.iv_shift_stop is not None and abs(iv_shift) >= rules.iv_shift_stop:
        return True
    # gamma-risk tighten near expiry for short premium
    if is_short_premium and rules.gamma_risk_dte_days is not None and dte_days <= rules.gamma_risk_dte_days:
        return True
    # event-risk rule
    if event_risk_high and rules.event_risk_exit:
        return True
    return False
