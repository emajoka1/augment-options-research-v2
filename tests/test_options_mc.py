import math

from ak_system.mc_options.pricer import bs_greeks, bs_price, put_call_parity_gap


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
