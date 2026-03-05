import importlib.util
import json
from pathlib import Path


spec_cmd = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec_cmd)
spec_cmd.loader.exec_module(mc)

spec_why = importlib.util.spec_from_file_location(
    "mc_why", Path(__file__).resolve().parents[1] / "scripts" / "mc_why.py"
)
mwhy = importlib.util.module_from_spec(spec_why)
spec_why.loader.exec_module(mwhy)


def _brief(no_candidates_reason=None):
    tb = {
        "Spot": 500.0,
        "Regime": {
            "riskState": "Neutral",
            "trend": "flat",
            "vixDirection": "flat",
            "ratesDirection": "flat",
        },
        "Final Decision": "NO TRADE",
        "missingRequiredData": ["ivCurrent"],
        "Candidates": [{"type": "debit", "decision": "PASS", "score": {"Total": 55}, "gateFailures": ["x"]}],
    }
    if no_candidates_reason:
        tb["NoCandidatesReason"] = no_candidates_reason
    return {"TRADE BRIEF": tb, "brief_meta": {"brief_id": "b1"}}


def _monkeypatch_normalize_deps(monkeypatch):
    monkeypatch.setattr(mc, "generate_options_mc_for_run", lambda _spot: ({
        "generated_at": "2026-03-05T00:00:00Z",
        "assumptions": {"model": "jump", "n_paths": 5000, "legs": [{"option_type": "call", "strike": 500}, {"option_type": "call", "strike": 505}]},
        "multi_seed_confidence": {"n_batches": 10, "paths_per_batch": 500, "n_total_paths": 5000, "ev_5th_percentile": 0.5, "cvar_worst": -1.5},
        "edge_attribution": {"explainable": True, "signals_pass": 2},
        "friction_hurdle": {"ev_real": 0.6, "ev_stress": 0.58},
        "distribution_percentiles": {"p5": -1.4},
        "metrics": {"min_pl": -5.0},
        "randomness_policy": {"base_seed": 1, "crn_scope": "global"},
    }, "kb/experiments/options-mc-demo.json"))
    monkeypatch.setattr(mc, "latest_options_mc", lambda: (None, None, True))
    monkeypatch.setattr(mc, "run_steady_gate", lambda _p: {"decision": "PASS", "approved": True, "reasons": []})
    monkeypatch.setattr(mc, "get_cboe_spot_mid", lambda _s: 500.0)


def test_mc_command_schema_contract_required_keys(monkeypatch):
    _monkeypatch_normalize_deps(monkeypatch)
    out = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, _brief())

    required = [
        "timestamp", "trace_ids", "data_status", "data_source", "action_state", "final_decision",
        "spot_integrity", "mc_provenance", "trade_ready_rule", "raw",
    ]
    for k in required:
        assert k in out, f"missing key: {k}"

    for k in ["snapshot_id", "brief_id", "mc_id"]:
        assert k in out["trace_ids"]

    for k in ["ref_source", "ref_spot", "delta", "max_delta", "ok"]:
        assert k in out["spot_integrity"]

    for k in [
        "options_mc_source_mode", "options_mc_source_file", "generated_at", "model", "n_batches", "paths_per_batch",
        "n_total_paths", "computed_n_total_paths", "assumptions_n_paths", "counts_consistent", "source_stale",
        "base_seed", "crn_scope",
    ]:
        assert k in out["mc_provenance"], f"missing mc_provenance key {k}"

    for k in [
        "r_structural", "r_structural_source", "ev_mean_R", "ev_seed_p5_R", "ev_stress_mean_R", "pl_p5_R",
        "cvar_worst_R", "stress_delta_ev_mean_R", "pass", "failures",
    ]:
        assert k in out["trade_ready_rule"], f"missing trade_ready_rule key {k}"


def test_mc_command_backward_compat_aliases(monkeypatch):
    _monkeypatch_normalize_deps(monkeypatch)
    out = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, _brief())
    assert out["traceIds"] == out["trace_ids"]
    assert out["spotIntegrity"] == out["spot_integrity"]
    assert out["mcProvenance"] == out["mc_provenance"]
    assert out["tradeReadyRule"] == out["trade_ready_rule"]


def test_no_candidates_reason_path_preserved(monkeypatch):
    _monkeypatch_normalize_deps(monkeypatch)
    reason = "NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."
    out = mc.normalize({"snapshotId": "s1", "symbolsWithData": 1}, _brief(no_candidates_reason=reason))
    assert out["raw"]["TRADE BRIEF"]["NoCandidatesReason"] == reason


def test_mc_why_includes_stale_source_marker(monkeypatch, capsys):
    monkeypatch.setattr(
        mwhy,
        "run_mc_json",
        lambda: {
            "action_state": "WATCH",
            "data_status": "OK",
            "data_source": "dxlink-live",
            "final_decision": "PASS",
            "regime": "Neutral",
            "trend": "flat",
            "vix_direction": "flat",
            "rates_direction": "flat",
            "top_candidate": {"type": "debit", "score": 60, "decision": "PASS", "gate_failures": []},
            "missing_required": [],
            "raw": {"TRADE BRIEF": {"Volatility State": {"volLabel": "Neutral", "ivCurrent": 0.2}}},
        },
    )
    monkeypatch.setattr(mwhy, "latest_options_mc", lambda: ({"metrics": {}, "multi_seed_confidence": {}, "gates": {}}, "x.json", True))

    assert mwhy.main() == 0
    out = capsys.readouterr().out
    assert "source_stale=True" in out
    assert "Warning: options-MC source is stale" in out
