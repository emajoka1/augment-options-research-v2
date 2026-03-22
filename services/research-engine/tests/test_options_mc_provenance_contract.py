import importlib.util
import json
import sys
from pathlib import Path

spec_ak = importlib.util.spec_from_file_location(
    "ak_options_mc", Path(__file__).resolve().parents[1] / "scripts" / "ak_options_mc.py"
)
ak = importlib.util.module_from_spec(spec_ak)
spec_ak.loader.exec_module(ak)

spec_mc = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec_mc)
spec_mc.loader.exec_module(mc)


class _M:
    def __init__(self):
        self.ev = 0.2
        self.pop = 0.6
        self.cvar95 = -1.0
        self.pot = 0.5
        self.var95 = -0.5
        self.profit_factor = 1.2
        self.avg_loss = -0.8
        self.avg_win = 0.7
        self.min_pl = -1.1



def test_options_mc_payload_contains_mandatory_provenance_keys(monkeypatch):
    captured = {}

    monkeypatch.setattr(ak, "build_paths", lambda _p: type("P", (), {"kb_experiments": Path("/tmp")})())
    monkeypatch.setattr(ak, "ensure_dirs", lambda _p: None)
    monkeypatch.setattr(ak, "simulate_strategy_paths", lambda **kwargs: ([0.1, -0.1, 0.2], 0.3))
    monkeypatch.setattr(ak, "compute_metrics", lambda pnl, pot: _M())
    monkeypatch.setattr(ak, "percentiles", lambda pnl: {"p5": -0.2})
    monkeypatch.setattr(ak, "infer_regime_distribution", lambda *a, **k: {"dominant": "neutral", "neutral": 1.0})

    def fake_write(_out, payload):
        captured["payload"] = payload
        return Path("/tmp/a.json"), Path("/tmp/a.md")

    monkeypatch.setattr(ak, "write_report_json_md", fake_write)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ak_options_mc.py",
            "--n-batches",
            "1",
            "--paths-per-batch",
            "100",
            "--expiry-days",
            "1",
            "--dt-days",
            "1",
        ],
    )
    ak.main()
    p = captured["payload"]

    assert p["generated_at"]
    assert isinstance(p["config_hash"], str) and len(p["config_hash"]) == 64
    assert p["n_batches"] == 1
    assert p["paths_per_batch"] == 100
    assert p["n_total_paths"] == 100
    assert p["assumptions"]["n_paths"] == 100
    assert isinstance(p["base_seed"], int)
    assert p["crn_scope"]



def test_mc_command_fails_closed_on_missing_provenance(monkeypatch):
    brief = {
        "TRADE BRIEF": {
            "Spot": 500.0,
            "Regime": {"riskState": "Neutral", "trend": "flat", "vixDirection": "flat", "ratesDirection": "flat"},
            "Final Decision": "NO TRADE",
            "missingRequiredData": [],
            "Candidates": [{"type": "debit", "decision": "PASS", "score": {"Total": 50}, "gateFailures": []}],
            "Volatility State": {"classifier": {"regime": "NORMAL"}},
        },
        "brief_meta": {"brief_id": "b1"},
    }
    monkeypatch.setattr(mc, "run_live_snapshot", lambda _skip: {"snapshotId": "s1", "symbolsWithData": 1})
    monkeypatch.setattr(mc, "run_brief", lambda: brief)
    monkeypatch.setattr(mc, "get_cboe_spot_mid", lambda _s: 500.0)
    monkeypatch.setattr(mc, "append_log", lambda _e: None)

    # Missing required provenance fields intentionally
    bad_mc = {
        "assumptions": {"model": "jump", "n_paths": 5000, "legs": [{"option_type": "call", "strike": 500}, {"option_type": "call", "strike": 505}]},
        "multi_seed_confidence": {"n_batches": 10, "paths_per_batch": 500, "n_total_paths": 5000, "ev_5th_percentile": 0.5, "cvar_worst": -1.5},
        "edge_attribution": {"explainable": True, "signals_pass": 2},
        "friction_hurdle": {"ev_real": 0.6, "ev_stress": 0.58},
        "distribution_percentiles": {"p5": -1.4},
        "metrics": {"min_pl": -5.0},
        "randomness_policy": {"base_seed": 1, "crn_scope": "global"},
    }
    monkeypatch.setattr(mc, "generate_options_mc_for_run", lambda _spot: (bad_mc, "x.json"))

    monkeypatch.setattr(sys, "argv", ["mc_command.py", "--json", "--max-attempts", "1", "--retry-delay-sec", "0"]) 
    try:
        mc.main()
        assert False, "Expected RuntimeError for invalid provenance"
    except RuntimeError as e:
        assert "Invalid options-mc provenance" in str(e)
