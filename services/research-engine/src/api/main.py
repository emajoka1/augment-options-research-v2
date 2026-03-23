from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Literal

from fastapi import FastAPI, Query, HTTPException
import numpy as np
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
LOCAL_SPY_LIVE_SNAPSHOT = Path(os.environ.get('SPY_LIVE_OUT', str(Path.home() / 'lab/data/tastytrade/spy_live_snapshot.json')))
LOCAL_SPY_LIVE_SCRIPT = Path(os.environ.get('SPY_LIVE_SCRIPT', str(Path(__file__).resolve().parents[2] / 'scripts' / 'spy_live_snapshot.cjs')))
LOCAL_SPY_LIVE_MAX_AGE_SECONDS = int(os.environ.get('SPY_LIVE_MAX_AGE_SECONDS', '300'))
TRIGGER_LOCAL_SPY_LIVE = os.environ.get('SPY_TRIGGER_LIVE_FROM_API', '1').lower() in {'1', 'true', 'yes'}
MIN_LIVE_CHAIN_POINTS = int(os.environ.get('SPY_MIN_LIVE_CHAIN_POINTS', '8'))


def _snapshot_is_fresh(path: Path, max_age_seconds: int) -> bool:
    if not path.exists():
        return False
    try:
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        return age <= max_age_seconds
    except OSError:
        return False



def _trigger_spy_live_snapshot() -> None:
    if not TRIGGER_LOCAL_SPY_LIVE:
        return
    if not LOCAL_SPY_LIVE_SCRIPT.exists():
        raise FileNotFoundError(f'live snapshot script not found: {LOCAL_SPY_LIVE_SCRIPT}')
    subprocess.run(
        ['node', str(LOCAL_SPY_LIVE_SCRIPT)],
        check=True,
        cwd=str(LOCAL_SPY_LIVE_SCRIPT.parent.parent),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )



def _load_local_spy_live_snapshot() -> ChainSnapshot | None:
    if not _snapshot_is_fresh(LOCAL_SPY_LIVE_SNAPSHOT, LOCAL_SPY_LIVE_MAX_AGE_SECONDS):
        _trigger_spy_live_snapshot()
    if not LOCAL_SPY_LIVE_SNAPSHOT.exists():
        return None

    payload = json.loads(LOCAL_SPY_LIVE_SNAPSHOT.read_text(encoding='utf-8'))
    contracts = payload.get('contracts') or []
    data = payload.get('data') or {}
    underlying = payload.get('underlying') or {}

    spot_candidates = [underlying.get('mark'), underlying.get('bid'), underlying.get('ask'), underlying.get('last')]
    spot = next((float(v) for v in spot_candidates if isinstance(v, (int, float)) and np.isfinite(v) and v > 0), None)
    if spot is None:
        return None

    strikes: list[float] = []
    ivs: list[float] = []
    expiries_days: list[float] = []
    returns = payload.get('returns')

    for contract in contracts:
        symbol = contract.get('symbol')
        row = data.get(symbol or '')
        if not row:
            continue
        strike = contract.get('strike')
        dte = contract.get('dte')
        iv = row.get('iv')
        if not isinstance(strike, (int, float)) or not isinstance(dte, (int, float)) or not isinstance(iv, (int, float)):
            continue
        if not np.isfinite(strike) or not np.isfinite(dte) or not np.isfinite(iv) or iv <= 0:
            continue
        strikes.append(float(strike))
        ivs.append(float(iv))
        expiries_days.append(float(dte))

    if len(strikes) < MIN_LIVE_CHAIN_POINTS:
        return None

    returns_arr = np.array(returns, dtype=float) if isinstance(returns, list) else None
    return ChainSnapshot(
        spot=float(spot),
        strikes=np.array(strikes, dtype=float),
        ivs=np.array(ivs, dtype=float),
        expiries_days=np.array(expiries_days, dtype=float),
        returns=returns_arr,
    )



async def _resolve_chain_snapshot(symbol: str, snapshot_path: str | None) -> tuple[ChainSnapshot, str]:
    if os.environ.get('POLYGON_API_KEY'):
        provider = PolygonProvider(os.environ['POLYGON_API_KEY'])
        return await provider.get_chain(symbol), 'polygon'

    if snapshot_path:
        return parse_chain_snapshot(snapshot_path), 'snapshot_file'

    if symbol.upper() == 'SPY':
        live_snapshot = _load_local_spy_live_snapshot()
        if live_snapshot is not None:
            return live_snapshot, 'dxlink_live_snapshot'

    if ALLOW_DEMO_FALLBACK:
        return demo_chain_snapshot(symbol), 'builtin_demo'

    raise HTTPException(status_code=503, detail='live provider or snapshot required')


@app.get('/v1/health', response_model=HealthResponse)
def health():
    return {'status': 'ok', 'version': __version__, 'timestamp': datetime.now(timezone.utc).isoformat()}


@app.get('/v1/chain/{symbol}', response_model=ChainResponse)
async def get_chain(symbol: str, snapshot_path: str | None = Query(default=None, description='Local snapshot path')):
    snap, source = await _resolve_chain_snapshot(symbol, snapshot_path)
    return {
        'symbol': symbol,
        'spot': snap.spot,
        'strikes': snap.strikes.tolist(),
        'ivs': snap.ivs.tolist(),
        'expiry_days': snap.expiries_days.tolist() if snap.expiries_days is not None else None,
        'returns': snap.returns.tolist() if snap.returns is not None else None,
        'source': source,
        'todo': 'Replace with Polygon.io live fetch in Task 0.5.' if source == 'builtin_demo' else None,
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
    greeks = {'delta': 0.0, 'gamma': 0.0, 'vega': 0.0, 'theta_daily': 0.0}
    for leg in strategy.legs:
        tau_leg = leg.expiry_years or expiry_years
        sigma_leg = iv_by_strike.get(leg.strike, 0.25)
        g = asdict(bs_greeks(req.spot, leg.strike, req.r, req.q, sigma_leg, tau_leg, leg.option_type))
        sign = 1.0 if leg.side == 'long' else -1.0
        qty = float(leg.qty)
        greeks['delta'] += sign * qty * g['delta']
        greeks['gamma'] += sign * qty * g['gamma']
        greeks['vega'] += sign * qty * g['vega']
        greeks['theta_daily'] += sign * qty * g['theta_daily']

    return {
        'entry_value': entry_value,
        'breakevens': breakevens,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'greeks_aggregate': greeks,
        'exit_rules': {
            'take_profit_pct': exit_rules.take_profit_pct,
            'stop_loss_pct': exit_rules.stop_loss_pct,
            'dte_stop_days': exit_rules.dte_stop_days,
            'gamma_risk_dte_days': exit_rules.gamma_risk_dte_days,
        },
    }


@app.get('/v1/vol-surface/{symbol}', response_model=VolSurfaceResponse)
async def vol_surface(symbol: str, snapshot_path: str | None = Query(default=None, description='Local snapshot path')):
    snap, _ = await _resolve_chain_snapshot(symbol, snapshot_path)
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
    try:
        result = BriefGenerator().generate(symbol)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return result.payload
