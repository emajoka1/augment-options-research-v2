import numpy as np

from ak_system.mc_options.calibration import fit_iv_params_from_snapshot
from ak_system.mc_options.iv_dynamics import fit_surface_from_snapshot


def test_fit_surface_prefers_nearest_expiry_slice():
    spot = 100.0
    strikes = np.array([95, 100, 105, 95, 100, 105], dtype=float)
    ivs = np.array([0.30, 0.28, 0.29, 0.20, 0.19, 0.20], dtype=float)
    expiries = np.array([5, 5, 5, 30, 30, 30], dtype=float)

    fit = fit_surface_from_snapshot(spot=spot, strikes=strikes, ivs=ivs, expiries_days=expiries, target_expiry_days=5)
    assert fit['iv_atm'] > 0.25


def test_fit_surface_returns_slice_metadata_when_expiries_present():
    spot = 100.0
    strikes = np.array([95, 100, 105, 95, 100, 105], dtype=float)
    ivs = np.array([0.30, 0.28, 0.29, 0.20, 0.19, 0.20], dtype=float)
    expiries = np.array([5, 5, 5, 30, 30, 30], dtype=float)

    fit = fit_surface_from_snapshot(spot=spot, strikes=strikes, ivs=ivs, expiries_days=expiries, target_expiry_days=30)
    assert fit['slice_expiry_days'] == 30.0
    assert fit['slice_points'] == 3


def test_fit_iv_params_uses_term_and_nearest_slice():
    spot = 100.0
    strikes = np.array([95, 100, 105, 95, 100, 105], dtype=float)
    ivs = np.array([0.30, 0.28, 0.29, 0.20, 0.19, 0.20], dtype=float)
    expiries = np.array([5, 5, 5, 30, 30, 30], dtype=float)

    iv = fit_iv_params_from_snapshot(spot=spot, strikes=strikes, ivs=ivs, expiries_days=expiries, target_expiry_days=5)
    assert iv.iv_atm > 0.25
    assert np.isfinite(iv.skew)
    assert np.isfinite(iv.curv)
