import math

import numpy as np

from ak_system.mc_options.calibration import parse_chain_snapshot
from ak_system.mc_options.iv_dynamics import IVDynamicsParams, evolve_iv_state, fit_surface_from_snapshot, surface_iv
from ak_system.mc_options.metrics import compute_metrics
from ak_system.mc_options.models import GBMParams, HestonParams, simulate_gbm_paths, simulate_heston_paths
from ak_system.mc_options.pricer import bs_greeks, bs_price, put_call_parity_gap
from ak_system.mc_options.strategy import ExitRules, make_iron_fly, make_long_straddle, max_profit_max_loss, strategy_mid_value
from ak_system.mc_options.simulator import FrictionConfig, RepriceRequest, reprice_option_path, simulate_strategy_paths


def test_put_call_parity_holds():
    gap = put_call_parity_gap(S=100, K=100, r=0.03, q=0.0, sigma=0.2, T=30 / 365)
    assert abs(gap) < 1e-6


def test_intrinsic_limit_near_expiry():
    call = bs_price(S=105, K=100, r=0.02, q=0.0, sigma=0.25, T=1e-8, option_type="call")
    put = bs_price(S=95, K=100, r=0.02, q=0.0, sigma=0.25, T=1e-8, option_type="put")
    assert abs(call - 5.0) < 1e-3
    assert abs(put - 5.0) < 1e-3


def test_greeks_signs():
    g_call = bs_greeks(S=100, K=100, r=0.02, q=0.0, sigma=0.2, T=30 / 365, option_type="call")
    g_put = bs_greeks(S=100, K=100, r=0.02, q=0.0, sigma=0.2, T=30 / 365, option_type="put")
    assert g_call.delta > 0
    assert g_put.delta < 0
    assert g_call.gamma > 0 and g_put.gamma > 0
    assert g_call.vega > 0 and g_put.vega > 0


def test_gbm_deterministic_seed_shape():
    paths = simulate_gbm_paths(100, n_paths=5, n_steps=10, dt=1 / 252, params=GBMParams(), seed=1)
    assert paths.shape == (5, 11)
    paths2 = simulate_gbm_paths(100, n_paths=5, n_steps=10, dt=1 / 252, params=GBMParams(), seed=1)
    assert np.allclose(paths, paths2)


def test_repricing_path_non_negative():
    path = np.linspace(100, 102, 11)
    req = RepriceRequest(strike=100, option_type="call", r=0.02, q=0.0, iv=0.2, expiry_years=20 / 252)
    px = reprice_option_path(path, req, dt=1 / 252)
    assert np.all(px >= 0)


def test_surface_fit_and_iv_bounds():
    spot = 100
    strikes = np.array([90, 95, 100, 105, 110], dtype=float)
    ivs = np.array([0.28, 0.26, 0.24, 0.25, 0.27], dtype=float)
    fit = fit_surface_from_snapshot(spot, strikes, ivs)
    params = IVDynamicsParams(iv_atm=fit["iv_atm"], skew=fit["skew"], curv=fit["curv"])
    rets = np.zeros(10)
    state = evolve_iv_state(params, n_steps=10, dt=1 / 252, returns=rets, seed=1)
    iv = surface_iv(100, 100, 20 / 252, state, 5, params)
    assert params.iv_floor <= iv <= params.iv_cap


def test_iron_fly_defined_risk_shape():
    strat = make_iron_fly(center=100, wing=5, expiry_years=30 / 365, qty=1)
    iv_map = {95: 0.25, 100: 0.25, 105: 0.25}
    entry = strategy_mid_value(strat, S=100, r=0.02, q=0.0, tau=30 / 365, iv_by_strike=iv_map)
    mx, mn = max_profit_max_loss(strat, np.linspace(70, 130, 121), r=0.02, q=0.0, iv_by_strike=iv_map, entry_value=entry)
    assert mx > 0
    assert mn < 0
    assert abs(mn) < 10  # bounded by wing width in this simple setup


def test_strategy_mc_reproducible_and_metrics():
    strat = make_long_straddle(K=100, expiry_years=5 / 365)
    pnl1, touch1 = simulate_strategy_paths(
        strategy=strat,
        S0=100,
        r=0.02,
        q=0.0,
        n_paths=120,
        n_steps=20,
        dt=(5 / 365) / 20,
        iv_params=IVDynamicsParams(iv_atm=0.25),
        exit_rules=ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25),
        friction=FrictionConfig(spread_bps=20, slippage_bps=5, partial_fill_prob=0.1),
        model="jump",
        seed=11,
    )
    pnl2, touch2 = simulate_strategy_paths(
        strategy=strat,
        S0=100,
        r=0.02,
        q=0.0,
        n_paths=120,
        n_steps=20,
        dt=(5 / 365) / 20,
        iv_params=IVDynamicsParams(iv_atm=0.25),
        exit_rules=ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25),
        friction=FrictionConfig(spread_bps=20, slippage_bps=5, partial_fill_prob=0.1),
        model="jump",
        seed=11,
    )
    assert np.allclose(pnl1, pnl2)
    m = compute_metrics(pnl1, touch1)
    assert 0 <= m.pop <= 1


def test_wider_spread_reduces_ev():
    strat = make_long_straddle(K=100, expiry_years=5 / 365)
    common = dict(
        strategy=strat,
        S0=100,
        r=0.02,
        q=0.0,
        n_paths=160,
        n_steps=20,
        dt=(5 / 365) / 20,
        iv_params=IVDynamicsParams(iv_atm=0.25),
        exit_rules=ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25),
        model="jump",
        seed=44,
    )
    pnl_tight, _ = simulate_strategy_paths(**common, friction=FrictionConfig(spread_bps=15, slippage_bps=4, partial_fill_prob=0.05))
    pnl_wide, _ = simulate_strategy_paths(**common, friction=FrictionConfig(spread_bps=80, slippage_bps=20, partial_fill_prob=0.30))
    m_tight = compute_metrics(pnl_tight)
    m_wide = compute_metrics(pnl_wide)
    assert m_wide.ev <= m_tight.ev


def test_heston_paths_deterministic_and_positive():
    p1, v1 = simulate_heston_paths(100, n_paths=4, n_steps=8, dt=1 / 252, params=HestonParams(), seed=9)
    p2, v2 = simulate_heston_paths(100, n_paths=4, n_steps=8, dt=1 / 252, params=HestonParams(), seed=9)
    assert np.allclose(p1, p2)
    assert np.allclose(v1, v2)
    assert np.all(p1 > 0)
    assert np.all(v1 > 0)


def test_parse_chain_snapshot_json(tmp_path):
    f = tmp_path / "chain.json"
    f.write_text('{"spot": 101.5, "chain": [{"strike": 100, "iv": 0.24, "expiry_days": 5}, {"strike": 102, "iv": 0.25, "expiry_days": 10}], "returns": [0.01, -0.02]}')
    s = parse_chain_snapshot(f)
    assert s.spot == 101.5
    assert len(s.strikes) == 2 and len(s.ivs) == 2
    assert s.expiries_days is not None
    assert s.returns is not None and len(s.returns) == 2


def test_parse_chain_snapshot_csv(tmp_path):
    f = tmp_path / "chain.csv"
    f.write_text("# spot=100.0\n# returns=0.01;-0.02;0.005\nstrike,iv,expiry_days\n99,0.24,5\n101,0.25,10\n")
    s = parse_chain_snapshot(f)
    assert s.spot == 100.0
    assert len(s.strikes) == 2
    assert s.expiries_days is not None
    assert s.returns is not None and len(s.returns) == 3
