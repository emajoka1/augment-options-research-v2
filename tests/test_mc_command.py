import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def _brief(final_decision="NO TRADE", missing=None):
    return {
        "TRADE BRIEF": {
            "Spot": 682.92,
            "Regime": {
                "riskState": "Neutral",
                "trend": "down_or_flat",
                "vixDirection": "down",
                "ratesDirection": "up",
            },
            "Final Decision": final_decision,
            "missingRequiredData": missing or [],
            "Candidates": [
                {"type": "debit", "decision": "PASS", "score": {"Total": 61}, "gateFailures": ["missing_fields"]}
            ],
        }
    }


def test_normalize_partial_data_forces_no_trade():
    live = {"symbolsWithData": 0}
    n = mc.normalize(live, _brief(final_decision="TRADE", missing=[]))
    assert n["data_status"] == "PARTIAL_DATA"
    assert n["action_state"] == "NO_TRADE"


def test_normalize_trade_ready_when_clean():
    live = {"symbolsWithData": 12}
    n = mc.normalize(live, _brief(final_decision="TRADE", missing=[]))
    assert n["data_status"] == "OK"
    assert n["action_state"] == "TRADE_READY"


def test_render_markdown_contains_sections():
    live = {"symbolsWithData": 12}
    n = mc.normalize(live, _brief(final_decision="PASS", missing=["ivCurrent"]))
    txt = mc.render_markdown(n, 1, 2)
    assert "Status:" in txt
    assert "Missing for trade-ready" in txt
    assert "`ivCurrent`" in txt


def _patch_deps_for_freshness(monkeypatch, generated_at: str):
    monkeypatch.setattr(mc, "generate_options_mc_for_run", lambda _spot: ({
        "generated_at": generated_at,
        "config_hash": "a" * 64,
        "n_batches": 10,
        "paths_per_batch": 500,
        "n_total_paths": 5000,
        "assumptions": {"model": "jump", "n_paths": 5000, "legs": [{"option_type": "call", "strike": 500}, {"option_type": "call", "strike": 505}]},
        "base_seed": 1,
        "crn_scope": "global",
        "multi_seed_confidence": {"n_batches": 10, "paths_per_batch": 500, "n_total_paths": 5000, "ev_5th_percentile": 0.5, "cvar_worst": -1.5},
        "edge_attribution": {"explainable": True, "signals_pass": 2},
        "friction_hurdle": {"ev_real": 0.6, "ev_stress": 0.58},
        "distribution_percentiles": {"p5": -1.4},
        "metrics": {"min_pl": -5.0},
        "randomness_policy": {"base_seed": 1, "crn_scope": "global"},
    }, "kb/experiments/options-mc-demo.json"))
    monkeypatch.setattr(mc, "latest_options_mc", lambda: (None, None, True))
    monkeypatch.setattr(mc, "run_steady_gate", lambda _p: {"decision": "PASS", "approved": True, "reasons": []})
    monkeypatch.setattr(mc, "get_cboe_spot_mid", lambda _s: 682.92)


def test_fresh_inputs_emit_freshness_metadata(monkeypatch):
    _patch_deps_for_freshness(monkeypatch, "2026-03-09T01:55:00Z")
    n = mc.normalize({"symbolsWithData": 1}, _brief(final_decision="TRADE", missing=[]), freshness_sla_seconds=3600)
    assert "freshness" in n
    assert n["freshness"]["max_age_seconds"] == 3600
    assert "options_mc_generated_at" in n["freshness"]["inputs"]


def test_stale_inputs_fail_closed_with_reason_code(monkeypatch):
    _patch_deps_for_freshness(monkeypatch, "2020-01-01T00:00:00Z")
    n = mc.normalize({"symbolsWithData": 1}, _brief(final_decision="TRADE", missing=[]), freshness_sla_seconds=60)
    assert n["action_state"] == "NO_TRADE"
    failures = n["trade_ready_rule"]["failures"]
    assert "DATA_QUALITY_FAIL: stale_inputs" in failures


def test_partial_data_cannot_bypass_stale_guard(monkeypatch):
    _patch_deps_for_freshness(monkeypatch, "2020-01-01T00:00:00Z")
    n = mc.normalize({"symbolsWithData": 0}, _brief(final_decision="TRADE", missing=[]), freshness_sla_seconds=60)
    assert n["data_status"] == "PARTIAL_DATA"
    assert n["action_state"] == "NO_TRADE"
    assert "DATA_QUALITY_FAIL: stale_inputs" in n["trade_ready_rule"]["failures"]
