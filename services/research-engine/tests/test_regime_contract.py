import numpy as np

from ak_system.regime import classify_regime_rule_based


def test_short_history_defaults_to_conservative_regime():
    prices = np.array([100, 101, 100.5, 101.2, 100.9], dtype=float)
    vol = np.array([0.01, 0.02, 0.015, 0.018, 0.017], dtype=float)
    lbl = classify_regime_rule_based(prices, vol, lookback=20)
    assert lbl.key == 'trend|vol_expanding'


def test_sufficient_history_still_returns_known_labels():
    prices = np.linspace(100, 110, 40)
    vol = np.linspace(0.01, 0.03, 40)
    lbl = classify_regime_rule_based(prices, vol, lookback=20)
    assert lbl.key in {'trend|vol_expanding', 'trend|vol_contracting', 'mean_revert|vol_expanding', 'mean_revert|vol_contracting'}


def test_nan_autocorrelation_does_not_break_classifier():
    prices = np.ones(30)
    vol = np.linspace(0.01, 0.02, 30)
    lbl = classify_regime_rule_based(prices, vol, lookback=20)
    assert lbl.key in {'trend|vol_expanding', 'trend|vol_contracting', 'mean_revert|vol_expanding', 'mean_revert|vol_contracting'}
