from __future__ import annotations

from typing import Any

import numpy as np


def compute_edge_attribution(ivp, rv10, rv20, regime_probs: dict[str, float], breakevens, spot: float, expiry_years: float) -> dict[str, Any]:
    iv_rv_gap = float(ivp.iv_atm - rv20) if rv20 is not None else None
    expected_move = float(spot * ivp.iv_atm * (expiry_years**0.5))
    if breakevens is not None:
        be_dist = min(abs(b - spot) for b in breakevens)
        structure_match = float(max(0.0, 1.0 - abs(be_dist - expected_move) / max(expected_move, 1e-6)))
    else:
        structure_match = None

    mean_revert_prob = float(regime_probs.get("mean_revert|vol_contracting", 0.0))
    iv_rv_present = iv_rv_gap is not None
    regime_present = np.isfinite(mean_revert_prob)
    structure_present = isinstance(structure_match, (int, float)) and np.isfinite(structure_match)

    iv_rv_pass = iv_rv_present
    regime_pass = regime_present and (mean_revert_prob >= 0.20)
    structure_pass = structure_present and (float(structure_match) >= 0.05)

    explainability_signals_present = int(iv_rv_present) + int(regime_present) + int(structure_present)
    explainability_signals_pass = int(iv_rv_pass) + int(regime_pass) + int(structure_pass)

    return {
        "iv_rich_vs_rv": iv_rv_gap,
        "mean_reversion_regime_probability": mean_revert_prob,
        "structure_expected_move_match": structure_match,
        "signals_present": explainability_signals_present,
        "signals_pass": explainability_signals_pass,
        "thresholds": {
            "regime_prob_min": 0.20,
            "structure_match_min": 0.05,
            "min_signals_pass": 2,
        },
    }


def evaluate_survival_gates(metrics, multi_seed: dict[str, float], regime: str, attribution: dict[str, Any], config) -> tuple[dict[str, Any], dict[str, float]]:
    R_unit = max(abs(metrics.min_pl), 1e-6)
    is_short_premium = config.strategy_name in {"iron_fly", "iron_condor"}

    if regime == "trend|vol_expanding":
        ev_req, cvar_req = 0.10, -0.70
    elif regime == "mean_revert|vol_contracting":
        ev_req, cvar_req = 0.05, -1.00
    else:
        ev_req, cvar_req = 0.07, -0.85

    ev_mid_mean = float(multi_seed["ev_mid"])
    ev_real_mean = float(multi_seed["ev_real"])
    ev_stress_mean = float(multi_seed["ev_stress"])

    ev_mid_r = ev_mid_mean / R_unit
    ev_real_r = ev_real_mean / R_unit
    ev_stress_r = ev_stress_mean / R_unit
    ev_p5_r = float(multi_seed["ev_5th_percentile"]) / R_unit
    cvar_r = float(multi_seed["cvar_mean"]) / R_unit
    cvar_worst_r = float(multi_seed["cvar_worst"]) / R_unit

    strategy_type = getattr(config, 'strategy_name', None) or getattr(config, 'strategy_type', None)
    max_loss = abs(float(metrics.min_pl)) if metrics.min_pl is not None else None
    cvar_abs = abs(float(metrics.cvar95)) if metrics.cvar95 is not None else None
    cvar_ratio = (cvar_abs / max_loss) if (max_loss is not None and max_loss > 0 and cvar_abs is not None) else None
    defined_risk = strategy_type in {"iron_condor", "put_credit_spread", "call_debit_spread", "put_debit_spread", "iron_fly"}

    if defined_risk and cvar_ratio is not None:
        cvar_gate = cvar_ratio <= 1.05
        cvar_worst_gate = cvar_ratio <= 1.05
        cvar_gate_status = 'PASS' if cvar_ratio <= 0.90 else ('WARN' if cvar_ratio <= 1.05 else 'FAIL')
    else:
        cvar_gate = cvar_r > cvar_req
        cvar_worst_gate = cvar_worst_r > cvar_req
        cvar_gate_status = None

    friction_hurdle = {
        "ev_mid": ev_mid_mean,
        "ev_real": ev_real_mean,
        "ev_stress": ev_stress_mean,
        "delta_ev_real": ev_real_mean - ev_mid_mean,
        "delta_ev_stress": ev_stress_mean - ev_mid_mean,
        "ev_mid_R": ev_mid_r,
        "ev_real_R": ev_real_r,
        "ev_stress_R": ev_stress_r,
    }

    gate = {
        "regime": regime,
        "ev_threshold_R": ev_req,
        "cvar_threshold_R": cvar_req,
        "ev_gate": ev_real_r > ev_req,
        "ev_ci_gate": ev_p5_r > 0.02,
        "cvar_gate": cvar_gate,
        "cvar_worst_gate": cvar_worst_gate,
        "cvar_ratio": cvar_ratio,
        "cvar_gate_status": cvar_gate_status,
        "pop_or_pot": (float(multi_seed["pop_mean"]) > 0.55) if is_short_premium else (float(metrics.pot) > 0.45),
        "slippage_sensitivity_ok": abs(ev_stress_mean - ev_real_mean) / R_unit < 0.35,
        "stress_ev_not_catastrophic": ev_stress_r > -0.50,
    }
    return gate, friction_hurdle
