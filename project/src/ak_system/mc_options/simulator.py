from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .iv_dynamics import IVDynamicsParams, evolve_iv_state, surface_iv
from .models import GBMParams, HestonParams, JumpDiffusionParams, simulate_gbm_paths, simulate_heston_paths, simulate_jump_diffusion_paths
from .pricer import bs_price
from .strategy import ExitRules, Leg, StrategyDef, should_exit, strategy_mid_value


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


def reprice_option_path_with_surface(
    path: np.ndarray,
    req: RepriceRequest,
    dt: float,
    iv_state: dict,
    iv_params: IVDynamicsParams,
) -> np.ndarray:
    n_steps = len(path) - 1
    prices = np.zeros(n_steps + 1, dtype=float)
    for t in range(n_steps + 1):
        T = max(req.expiry_years - t * dt, 1e-6)
        iv = surface_iv(S_t=float(path[t]), K=req.strike, tau=T, iv_state=iv_state, t_idx=t, params=iv_params)
        prices[t] = bs_price(
            S=float(path[t]),
            K=req.strike,
            r=req.r,
            q=req.q,
            sigma=iv,
            T=T,
            option_type=req.option_type,
        )
    return prices


@dataclass
class FrictionConfig:
    spread_bps: float = 30.0
    slippage_bps: float = 8.0
    partial_fill_prob: float = 0.1
    min_tick: float = 0.01


def _exec_price(mid: float, side: str, friction: FrictionConfig, rng: np.random.Generator) -> float:
    spread = max(friction.min_tick, mid * friction.spread_bps / 10000)
    slip = friction.slippage_bps / 10000 * max(mid, friction.min_tick)
    if rng.random() < friction.partial_fill_prob:
        slip *= 1.8
    if side == "buy":
        return mid + 0.5 * spread + slip
    return max(friction.min_tick, mid - 0.5 * spread - slip)


def simulate_strategy_paths(
    strategy: StrategyDef,
    S0: float,
    r: float,
    q: float,
    n_paths: int,
    n_steps: int,
    dt: float,
    iv_params: IVDynamicsParams,
    exit_rules: ExitRules,
    friction: FrictionConfig,
    model: str = "jump",
    seed: int = 42,
    event_risk_high: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    heston_var = None
    if model == "gbm":
        paths = simulate_gbm_paths(S0, n_paths, n_steps, dt, GBMParams(mu=r - q, sigma=iv_params.iv_atm), seed=seed)
    elif model == "heston":
        paths, heston_var = simulate_heston_paths(
            S0,
            n_paths,
            n_steps,
            dt,
            HestonParams(mu=r - q, v0=max(1e-8, iv_params.iv_atm**2), theta=max(1e-8, iv_params.iv_atm**2)),
            seed=seed,
        )
    else:
        paths = simulate_jump_diffusion_paths(
            S0,
            n_paths,
            n_steps,
            dt,
            JumpDiffusionParams(mu=r - q, sigma=iv_params.iv_atm, jump_lambda=0.35, jump_mu=-0.05, jump_sigma=0.18),
            seed=seed,
        )

    pnl = np.zeros(n_paths)
    pot_flags = np.zeros(n_paths)

    for i in range(n_paths):
        path = paths[i]
        rets = np.diff(np.log(np.maximum(path, 1e-12)))
        iv_state = evolve_iv_state(iv_params, n_steps=n_steps, dt=dt, returns=rets, seed=seed + i)

        # Tie ATM IV to simulated Heston variance when model == heston:
        # sigma_t = sqrt(v_t), then keep skew/curv/term from fitted surface dynamics.
        if model == "heston" and heston_var is not None:
            iv_state["iv_atm"] = np.clip(np.sqrt(np.maximum(heston_var[i], 1e-12)), iv_params.iv_floor, iv_params.iv_cap)

        tau0 = strategy.expiry_years
        tau_by_leg0 = {idx: max((leg.expiry_years if leg.expiry_years is not None else strategy.expiry_years), 1e-6) for idx, leg in enumerate(strategy.legs)}
        iv_map0 = {leg.strike: surface_iv(path[0], leg.strike, tau_by_leg0[idx], iv_state, 0, iv_params) for idx, leg in enumerate(strategy.legs)}
        entry_mid = strategy_mid_value(strategy, path[0], r, q, tau0, iv_map0, tau_by_leg=tau_by_leg0)

        # Convert strategy value to executed entry cost with leg-level friction.
        entry_cost = 0.0
        for leg in strategy.legs:
            mid = bs_price(path[0], leg.strike, r, q, iv_map0[leg.strike], tau0, leg.option_type)
            if leg.side == "long":
                px = _exec_price(mid, "buy", friction, rng)
                entry_cost += px * leg.qty
            else:
                px = _exec_price(mid, "sell", friction, rng)
                entry_cost -= px * leg.qty

        final_val = entry_mid
        iv_shift = 0.0
        entry_abs = max(abs(entry_cost), 1e-6)
        tp_target = exit_rules.take_profit_pct * entry_abs if exit_rules.take_profit_pct is not None else None
        sl_limit = -exit_rules.stop_loss_pct * entry_abs if exit_rules.stop_loss_pct is not None else None

        for t in range(1, n_steps + 1):
            tau = max(strategy.expiry_years - t * dt, 1e-6)
            tau_by_leg = {
                idx: max((leg.expiry_years if leg.expiry_years is not None else strategy.expiry_years) - t * dt, 1e-6)
                for idx, leg in enumerate(strategy.legs)
            }
            iv_map = {leg.strike: surface_iv(path[t], leg.strike, tau_by_leg[idx], iv_state, t, iv_params) for idx, leg in enumerate(strategy.legs)}
            val = strategy_mid_value(strategy, path[t], r, q, tau, iv_map, tau_by_leg=tau_by_leg)
            path_pnl = val - entry_cost
            iv_shift = iv_state["iv_atm"][t] - iv_state["iv_atm"][0]
            dte_days = tau * 365

            if tp_target is not None and path_pnl >= tp_target and pot_flags[i] == 0:
                pot_flags[i] = 1

            if should_exit(
                path_pnl,
                entry_abs,
                dte_days,
                iv_shift,
                exit_rules,
                is_short_premium=(entry_cost < 0),
                event_risk_high=event_risk_high,
            ):
                final_val = val
                break
            final_val = val

        # exit execution at final value with friction
        exit_val = 0.0
        tau_end = max(strategy.expiry_years - n_steps * dt, 1e-6)
        t_used = min(n_steps, t if 't' in locals() else n_steps)
        iv_map_end = {leg.strike: surface_iv(path[t_used], leg.strike, tau_end, iv_state, t_used, iv_params) for leg in strategy.legs}
        for leg in strategy.legs:
            mid = bs_price(path[t_used], leg.strike, r, q, iv_map_end[leg.strike], tau_end, leg.option_type)
            # closing side opposite of opening side
            if leg.side == "long":
                px = _exec_price(mid, "sell", friction, rng)
                exit_val += px * leg.qty
            else:
                px = _exec_price(mid, "buy", friction, rng)
                exit_val -= px * leg.qty

        pnl[i] = exit_val - entry_cost

    return pnl, pot_flags
