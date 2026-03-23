from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, HTTPException
from ak_system import __version__
from ak_system.adapters.data_provider import PolygonProvider, SnapshotFileProvider
from src.api.fallbacks import demo_chain_snapshot
from ak_system.mc_options.calibration import ChainSnapshot, parse_chain_snapshot
from ak_system.mc_options.engine import MCEngine, MCEngineConfig
from ak_system.mc_options.iv_dynamics import fit_surface_from_snapshot
from ak_system.mc_options.pricer import bs_greeks, bs_price
from dataclasses import asdict
from ak_system.mc_options.strategy import Leg, StrategyDef, compute_breakevens, default_exit_rules_for_strategy, max_profit_max_loss, strategy_mid_value
from ak_system.brief.generator import BriefGenerator
from ak_system.risk.estimator import estimate_structure_risk
from src.api.job_models import JobAcceptedResponse, JobStatusResponse
from src.api.jobs import get_job, submit_mc_job
from src.api.models import (
    BriefResponse,
    ChainResponse,
    GreeksResponse,
    HealthResponse,
    MCRunResponse,
    RiskEstimateResponse,
    StrategyAnalyzeRequest,
    StrategyAnalyzeResponse,
    VolSurfaceResponse,
)

app = FastAPI(title='Research Engine API', version=__version__)
ALLOW_DEMO_FALLBACK = os.environ.get('ALLOW_DEMO_FALLBACK', '0').lower() in {'1', 'true', 'yes'}



@app.get('/v1/health', response_model=HealthResponse)
def health():
    return {'status': 'ok', 'version': __version__, 'timestamp': datetime.now(timezone.utc).isoformat()}


@app.get('/v1/chain/{symbol}', response_model=ChainResponse)
async def get_chain(symbol: str, snapshot_path: str | None = Query(default=None, description='Local snapshot path')):
    provider = None
    if os.environ.get('POLYGON_API_KEY'):
        provider = PolygonProvider(os.environ['POLYGON_API_KEY'])
    elif snapshot_path:
        provider = SnapshotFileProvider(snapshot_path)

    snap = await provider.get_chain(symbol) if provider else demo_chain_snapshot(symbol)
    return {
        'symbol': symbol,
        'spot': snap.spot,
        'strikes': snap.strikes.tolist(),
        'ivs': snap.ivs.tolist(),
        'expiry_days': snap.expiries_days.tolist() if snap.expiries_days is not None else None,
        'returns': snap.returns.tolist() if snap.returns is not None else None,
        'source': 'polygon' if os.environ.get('POLYGON_API_KEY') else ('snapshot_file' if snapshot_path else 'builtin_demo'),
        'todo': 'Replace with Polygon.io live fetch in Task 0.5.' if not os.environ.get('POLYGON_API_KEY') else None,
    }


@app.get('/v1/greeks', response_model=GreeksResponse)
def greeks(S: float, K: float, r: float, q: float, sigma: float, T: float, option_type: Literal['call', 'put']):
    price = bs_price(S, K, r, q, sigma, T, option_type)
    greeks_payload = asdict(bs_greeks(S, K, r, q, sigma, T, option_type))
    return {'price': price, **greeks_payload}


@app.post('/v1/mc/run', response_model=MCRunResponse)
def run_mc(config: MCEngineConfig):
    result = MCEngine().run(config)
    return result.payload




@app.post('/v1/mc/run-async', response_model=JobAcceptedResponse, status_code=202)
def run_mc_async(config: MCEngineConfig):
    job_id, backend = submit_mc_job(config)
    return {'job_id': job_id, 'status': 'pending', 'backend': backend}


@app.get('/v1/mc/jobs/{job_id}', response_model=JobStatusResponse)
def get_mc_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='job not found')
    return {'status': job.status, 'result': job.result, 'error': job.error, 'backend': job.backend}

@app.post('/v1/strategy/analyze', response_model=StrategyAnalyzeResponse)
def analyze_strategy(req: StrategyAnalyzeRequest):
    expiry_years = max((leg.expiry_years or 0.0137) for leg in req.legs)
    strategy = StrategyDef(name='custom', legs=[Leg(**leg.model_dump()) for leg in req.legs], expiry_years=expiry_years)
    iv_by_strike = {leg.strike: 0.25 for leg in strategy.legs}
    tau_by_leg = {i: (leg.expiry_years or expiry_years) for i, leg in enumerate(strategy.legs)}
    entry_value = strategy_mid_value(strategy, req.spot, req.r, req.q, expiry_years, iv_by_strike, tau_by_leg=tau_by_leg)
    breakevens, _, _ = compute_breakevens(strategy, abs(entry_value) or 1e-6)
    grid = __import__('numpy').linspace(req.spot * 0.8, req.spot * 1.2, 101)
    max_profit, max_loss = max_profit_max_loss(strategy, grid, req.r, req.q, iv_by_strike, entry_value)
    strategy_name = 'custom' if len(req.legs) > 4 else ('long_straddle' if len(req.legs) == 2 and all(leg.side == 'long' for leg in req.legs) else 'iron_fly')
    exit_rules = default_exit_rules_for_strategy(strategy_name, expiry_days=expiry_years * 365)
    return {
        'entry_value': entry_value,
        'breakevens': breakevens,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'greeks_aggregate': {'delta': 0.0, 'gamma': 0.0, 'vega': 0.0, 'theta_daily': 0.0},
        'exit_rules': {
            'take_profit_pct': exit_rules.take_profit_pct,
            'stop_loss_pct': exit_rules.stop_loss_pct,
            'dte_stop_days': exit_rules.dte_stop_days,
            'gamma_risk_dte_days': exit_rules.gamma_risk_dte_days,
        },
    }


@app.get('/v1/vol-surface/{symbol}', response_model=VolSurfaceResponse)
def vol_surface(symbol: str, snapshot_path: str | None = Query(default=None, description='Local snapshot path')):
    snap = parse_chain_snapshot(snapshot_path) if snapshot_path else demo_chain_snapshot(symbol)
    fit = fit_surface_from_snapshot(spot=snap.spot, strikes=snap.strikes, ivs=snap.ivs, expiries_days=snap.expiries_days)
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


@app.get('/v1/risk/estimate', response_model=RiskEstimateResponse)
def risk_estimate(structure_type: str, risk_cap: float, debit: float = 0.0, credit: float = 0.0, width: float = 0.0, wing: float = 0.0):
    return estimate_structure_risk(structure_type=structure_type, risk_cap=risk_cap, debit=debit, credit=credit, width=width, wing=wing)


@app.post('/v1/brief/{symbol}', response_model=BriefResponse)
def generate_brief(symbol: str):
    result = BriefGenerator().generate(symbol)
    return result.payload
brief(symbol: str):
    result = BriefGenerator().generate(symbol)
    return result.payload
