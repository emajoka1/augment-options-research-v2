import importlib.util
from pathlib import Path

from ak_system.research.hypothesis_lane import build_hypothesis, validate_hypothesis_payload


spec_mc = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec_mc)
spec_mc.loader.exec_module(mc)


def _stub_normalize_inputs():
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
    return brief_payload, mc_payload


def test_hypothesis_lane_required_fields_and_guardrail():
    payload = build_hypothesis("SPY")
    ok, errors = validate_hypothesis_payload(payload)
    assert ok, errors
    assert payload["guardrails"]["can_set_trade_ready"] is False


def test_hypothesis_lane_does_not_change_mc_decision_path(monkeypatch):
    brief_payload, mc_payload = _stub_normalize_inputs()
    monkeypatch.setattr(mc, "generate_options_mc_for_run", lambda _spot: (mc_payload, "x.json"))
    monkeypatch.setattr(mc, "run_steady_gate", lambda _p: {"decision": "PASS", "approved": True, "reasons": []})
    monkeypatch.setattr(mc, "get_cboe_spot_mid", lambda _s: 500.0)

    out_before = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, brief_payload)

    # Build hypothesis artifact payload (research-only lane), then ensure normalize output unchanged.
    _ = build_hypothesis("SPY")
    out_after = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, brief_payload)

    assert out_before["final_decision"] == out_after["final_decision"]
    assert out_before["action_state"] == out_after["action_state"]
    assert out_before["trade_ready_rule"] == out_after["trade_ready_rule"]
