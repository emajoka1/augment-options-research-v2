from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel

from ak_system import __version__
from ak_system.mc_options.calibration import ChainSnapshot, parse_chain_snapshot
from ak_system.mc_options.engine import MCEngine, MCEngineConfig
from ak_system.mc_options.iv_dynamics import fit_surface_from_snapshot
from ak_system.mc_options.pricer import bs_greeks, bs_price
from dataclasses import asdict
from ak_system.mc_options.strategy import Leg, StrategyDef, compute_breakevens, max_profit_max_loss, strategy_mid_value
from ak_system.risk.estimator import estimate_structure_risk

app = FastAPI(title='Research Engine API', version=__version__)


class StrategyLeg(BaseModel):
    side: Literal['long', 'short']
    option_type: Literal['call', 'put']
    strike: float
    qty: int = 1
    expiry_years: float | None = None


class StrategyAnalyzeRequest(BaseModel):
    legs: list[StrategyLeg]
    spot: float
    r: float = 0.03
    q: float = 0.0


@app.get('/v1/health')
def health():
    return {'status': 'ok', 'version': __version__, 'timestamp': datetime.now(timezone.utc).isoformat()}


@app.get('/v1/chain/{symbol}')
def get_chain(symbol: str, snapshot_path: str = Query(..., description='Local snapshot path')):
    snap = parse_chain_snapshot(snapshot_path)
    return {
        'symbol': symbol,
        'spot': snap.spot,
        'strikes': snap.strikes.tolist(),
        'ivs': snap.ivs.tolist(),
        'expiry_days': snap.expiries_days.tolist() if snap.expiries_days is not None else None,
        'returns': snap.returns.tolist() if snap.returns is not None else None,
        'todo': 'Replace with Polygon.io live fetch in Task 0.5.',
    }


@app.get('/v1/greeks')
def greeks(S: float, K: float, r: float, q: float, sigma: float, T: float, option_type: Literal['call', 'put']):
    price = bs_price(S, K, r, q, sigma, T, option_type)
    greeks_payload = asdict(bs_greeks(S, K, r, q, sigma, T, option_type))
    return {'price': price, **greeks_payload}


@app.post('/v1/mc/run')
def run_mc(config: MCEngineConfig):
    result = MCEngine().run(config)
    return result.payload


@app.post('/v1/strategy/analyze')
def analyze_strategy(req: StrategyAnalyzeRequest):
    expiry_years = max((leg.expiry_years or 0.0137) for leg in req.legs)
    strategy = StrategyDef(name='custom', legs=[Leg(**leg.model_dump()) for leg in req.legs], expiry_years=expiry_years)
    iv_by_strike = {leg.strike: 0.25 for leg in strategy.legs}
    tau_by_leg = {i: (leg.expiry_years or expiry_years) for i, leg in enumerate(strategy.legs)}
    entry_value = strategy_mid_value(strategy, req.spot, req.r, req.q, expiry_years, iv_by_strike, tau_by_leg=tau_by_leg)
    breakevens, _, _ = compute_breakevens(strategy, abs(entry_value) or 1e-6)
    grid = __import__('numpy').linspace(req.spot * 0.8, req.spot * 1.2, 101)
    max_profit, max_loss = max_profit_max_loss(strategy, grid, req.r, req.q, iv_by_strike, entry_value)
    return {
        'entry_value': entry_value,
        'breakevens': breakevens,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'greeks_aggregate': {'delta': 0.0, 'gamma': 0.0, 'vega': 0.0, 'theta_daily': 0.0},
    }


@app.get('/v1/vol-surface/{symbol}')
def vol_surface(symbol: str, snapshot_path: str = Query(..., description='Local snapshot path')):
    snap = parse_chain_snapshot(snapshot_path)
    fit = fit_surface_from_snapshot(spot=snap.spot, strikes=snap.strikes, ivs=snap.ivs)
    m = __import__('numpy').log(__import__('numpy').maximum(snap.strikes, 1e-12) / max(snap.spot, 1e-12))
    fitted_ivs = fit['iv_atm'] + fit['skew'] * m + fit['curv'] * (m ** 2)
    return {
        'symbol': symbol,
        'iv_atm': fit['iv_atm'],
        'skew': fit['skew'],
        'curv': fit['curv'],
        'strikes': snap.strikes.tolist(),
        'ivs': snap.ivs.tolist(),
        'fitted_ivs': fitted_ivs.tolist(),
    }


@app.get('/v1/risk/estimate')
def risk_estimate(structure_type: str, risk_cap: float, debit: float = 0.0, credit: float = 0.0, width: float = 0.0, wing: float = 0.0):
    return estimate_structure_risk(structure_type=structure_type, risk_cap=risk_cap, debit=debit, credit=credit, width=width, wing=wing)
