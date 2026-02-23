import math

import numpy as np

from ak_system.mc_options.iv_dynamics import IVDynamicsParams, evolve_iv_state, fit_surface_from_snapshot, surface_iv
from ak_system.mc_options.models import GBMParams, simulate_gbm_paths
from ak_system.mc_options.pricer import bs_greeks, bs_price, put_call_parity_gap
from ak_system.mc_options.strategy import make_iron_fly, max_profit_max_loss, strategy_mid_value
from ak_system.mc_options.simulator import RepriceRequest, reprice_option_path


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
