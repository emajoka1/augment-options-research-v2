import importlib.util
from pathlib import Path

spec_brief = importlib.util.spec_from_file_location(
    "spy_free_brief", Path(__file__).resolve().parents[1] / "scripts" / "spy_free_brief.py"
)
brief = importlib.util.module_from_spec(spec_brief)
spec_brief.loader.exec_module(brief)

spec_mc = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec_mc)
spec_mc.loader.exec_module(mc)

from ak_system.risk.estimator import estimate_structure_risk


def _leg(side, strike, mark, option_side='C'):
    return {
        "symbol": f"SPY_{option_side}_{strike}",
        "side": option_side,
        "strike": float(strike),
        "mark": float(mark),
        "bid": float(mark) - 0.01,
        "ask": float(mark) + 0.01,
        "dte": 7,
        "expiry": "2026-03-20",
        "openInterest": 1000,
        "dayVolume": 500,
        "delta": 0.2,
        "iv": 0.2,
    }


def test_brief_max_loss_matches_shared_estimator_representative_structures():
    spot = 500.0
    vol = {"ivCurrent": 0.2, "volLabel": "Neutral"}
    context = {"realizedVol": {"rv10": 0.18, "rv20": 0.17}, "regime": {"riskState": "Neutral", "trend": "flat", "vixDirection": "flat", "ratesDirection": "flat"}}
    risk_cap = brief.risk_cap_dollars()

    d = brief.build_trade("debit", (_leg("buy", 500, 5.0), _leg("sell", 505, 4.1)), spot, vol, context)
    est_d = estimate_structure_risk("debit", risk_cap=risk_cap, debit=0.9)
    assert abs(d["maxLossPerContract"] - est_d["max_loss"]) < 1e-6

    c = brief.build_trade("credit", (_leg("sell", 500, 3.0, 'P'), _leg("buy", 495, 2.3, 'P')), spot, vol, context)
    est_c = estimate_structure_risk("credit", risk_cap=risk_cap, width=5.0, credit=0.7)
    assert abs(c["maxLossPerContract"] - est_c["max_loss"]) < 1e-6

    cond = brief.build_trade(
        "condor",
        (
            _leg("sell", 495, 2.4, 'P'),
            _leg("buy", 490, 1.8, 'P'),
            _leg("sell", 505, 2.4, 'C'),
            _leg("buy", 510, 1.8, 'C'),
        ),
        spot,
        vol,
        context,
    )
    est_i = estimate_structure_risk("condor", risk_cap=risk_cap, wing=5.0, credit=1.2)
    assert abs(cond["maxLossPerContract"] - est_i["max_loss"]) < 1e-6


def test_mc_command_exposes_estimator_keys_and_consistency(monkeypatch):
    brief_payload = {
        "TRADE BRIEF": {
            "Spot": 500.0,
            "Regime": {"riskState": "Neutral", "trend": "flat", "vixDirection": "flat", "ratesDirection": "flat"},
            "Final Decision": "NO TRADE",
            "missingRequiredData": [],
            "Volatility State": {"classifier": {"regime": "NORMAL"}},
            "riskFramework": {"maxRiskDollars": 250.0},
            "Candidates": [{"type": "debit", "maxLossPerContract": 90.0, "decision": "PASS", "score": {"Total": 55}, "gateFailures": []}],
        },
        "brief_meta": {"brief_id": "b1"},
    }

    mc_payload = {
        "generated_at": "2026-03-05T00:00:00Z",
        "config_hash": "a" * 64,
        "n_batches": 10,
        "paths_per_batch": 500,
        "n_total_paths": 5000,
        "base_seed": 1,
        "crn_scope": "same_model_same_structure_friction_only",
        "assumptions": {"model": "jump", "n_paths": 5000, "legs": [{"option_type": "call", "strike": 500}, {"option_type": "call", "strike": 505}]},
        "multi_seed_confidence": {"n_batches": 10, "paths_per_batch": 500, "n_total_paths": 5000, "ev_5th_percentile": 0.5, "cvar_worst": -1.5},
        "edge_attribution": {"explainable": True, "signals_pass": 2},
        "friction_hurdle": {"ev_real": 0.6, "ev_stress": 0.58},
        "distribution_percentiles": {"p5": -1.4},
        "metrics": {"min_pl": -5.0},
        "randomness_policy": {"base_seed": 1, "crn_scope": "same_model_same_structure_friction_only"},
    }

    monkeypatch.setattr(mc, "generate_options_mc_for_run", lambda _spot: (mc_payload, "x.json"))
    monkeypatch.setattr(mc, "run_steady_gate", lambda _p: {"decision": "PASS", "approved": True, "reasons": []})
    monkeypatch.setattr(mc, "get_cboe_spot_mid", lambda _s: 500.0)

    out = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, brief_payload)
    re = out["risk_estimator"]
    assert re["version"]
    assert re["max_loss"] == 90.0
    assert re["risk_cap"] == 250.0
    assert re["feasible_under_cap"] is True
