import importlib.util
import sys
from pathlib import Path

import numpy as np

from ak_system.mc_options.strategy import compute_breakevens, make_put_diagonal, make_vertical
from ak_system.mc_options.report import write_report_json_md


spec = importlib.util.spec_from_file_location(
    "ak_options_mc", Path(__file__).resolve().parents[1] / "scripts" / "ak_options_mc.py"
)
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)


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


def test_supported_structures_emit_numeric_breakevens():
    put_vertical = make_vertical("put", long_strike=100, short_strike=95, expiry_years=30 / 365)
    call_vertical = make_vertical("call", long_strike=100, short_strike=105, expiry_years=30 / 365)
    diagonal = make_put_diagonal(long_strike=100, short_strike=95, front_expiry_years=7 / 365, back_expiry_years=30 / 365)

    for strat in (put_vertical, call_vertical, diagonal):
        breakevens, reason, _ = compute_breakevens(strat, entry_value=1.8)
        assert reason is None
        assert isinstance(breakevens, list) and len(breakevens) >= 1
        assert all(isinstance(x, float) for x in breakevens)


def test_unsolved_breakevens_emit_typed_failure_and_disable_explainability(monkeypatch):
    captured = {}

    monkeypatch.setattr(ak, "build_paths", lambda _p: type("P", (), {"kb_experiments": Path("/tmp")})())
    monkeypatch.setattr(ak, "ensure_dirs", lambda _p: None)
    monkeypatch.setattr(ak, "simulate_strategy_paths", lambda **kwargs: ([0.1, -0.1, 0.2], 0.3))
    monkeypatch.setattr(ak, "compute_metrics", lambda pnl, pot: _M())
    monkeypatch.setattr(ak, "percentiles", lambda pnl: {"p5": -0.2})
    monkeypatch.setattr(ak, "infer_regime_distribution", lambda *a, **k: {"dominant": "neutral", "neutral": 1.0, "mean_revert|vol_contracting": 0.0})
    monkeypatch.setattr(ak, "load_local_returns_fallback", lambda _root: (np.array([0.01] * 30, dtype=float), "local_fallback", "2026-03-09T07:00:00+00:00", 30.0))
    monkeypatch.setattr(ak, "compute_breakevens", lambda *_a, **_k: (None, "no_breakeven", {"grid_points": 100, "sign_flips": 0}))

    def fake_write(_out, payload):
        captured["payload"] = payload
        return Path("/tmp/a.json"), Path("/tmp/a.md")

    monkeypatch.setattr(ak, "write_report_json_md", fake_write)

    monkeypatch.setattr(sys, "argv", ["ak_options_mc.py", "--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1"])
    ak.main()

    p = captured["payload"]
    assert p["breakevens"] is None
    assert p["breakeven_reason"] == "BREAKEVEN_SOLVER_FAIL:no_breakeven"
    assert p["edge_attribution"]["structure_expected_move_match"] is None
    assert p["edge_attribution"]["explainable"] is False
    assert p["edge_attribution"]["explainable_reason"] == "BREAKEVEN_SOLVER_FAIL:no_breakeven"


def test_markdown_never_prints_breakevens_none(tmp_path):
    payload = {
        "assumptions": {"strategy": "put_diagonal", "model": "jump", "spot": 100, "r": 0.01, "q": 0.0, "expiry_years": 0.1, "n_paths": 100, "legs": []},
        "metrics": {"ev": 0.1, "pop": 0.5, "pot": 0.5, "var95": -0.4, "cvar95": -0.7, "profit_factor": 1.1},
        "stress": {},
        "edge_attribution": {"structure_expected_move_match": None, "explainable": False},
        "gates": {},
        "friction_hurdle": {},
        "multi_seed_confidence": {},
        "breakevens": None,
        "breakeven_reason": "BREAKEVEN_SOLVER_FAIL:no_breakeven",
    }
    _, md = write_report_json_md(tmp_path, payload)
    text = md.read_text()
    assert "Breakevens: None" not in text
    assert "Breakevens: BREAKEVEN_SOLVER_FAIL:no_breakeven" in text
