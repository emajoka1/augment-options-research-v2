import numpy as np

from ak_system.mc_options.simulator import FrictionConfig, _exec_price


def test_low_premium_option_gets_multi_tick_spread_floor():
    rng = np.random.default_rng(1)
    px = _exec_price(0.30, 'buy', FrictionConfig(spread_bps=30, slippage_bps=0, partial_fill_prob=0.0, min_tick=0.01), rng)
    assert px >= 0.30 + 0.015  # half of 3-tick spread


def test_mid_premium_option_gets_two_tick_floor():
    rng = np.random.default_rng(1)
    px = _exec_price(0.80, 'buy', FrictionConfig(spread_bps=30, slippage_bps=0, partial_fill_prob=0.0, min_tick=0.01), rng)
    assert px >= 0.80 + 0.01  # half of 2-tick spread


def test_higher_premium_option_still_uses_at_least_one_tick():
    rng = np.random.default_rng(1)
    px = _exec_price(3.00, 'sell', FrictionConfig(spread_bps=1, slippage_bps=0, partial_fill_prob=0.0, min_tick=0.01), rng)
    assert px <= 3.00 - 0.005


def test_wider_friction_still_hurts_execution_more():
    rng1 = np.random.default_rng(1)
    rng2 = np.random.default_rng(1)
    tight = _exec_price(0.40, 'buy', FrictionConfig(spread_bps=15, slippage_bps=2, partial_fill_prob=0.0, min_tick=0.01), rng1)
    wide = _exec_price(0.40, 'buy', FrictionConfig(spread_bps=80, slippage_bps=20, partial_fill_prob=0.0, min_tick=0.01), rng2)
    assert wide >= tight
