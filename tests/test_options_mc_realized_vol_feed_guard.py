import importlib.util
import json
import sys
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "ak_options_mc", Path(__file__).resolve().parents[1] / "scripts" / "ak_options_mc.py"
)
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)


def _run_main_with_args(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["ak_options_mc.py", *args])
    ak.main()
    out = capsys.readouterr().out
    blob = json.loads(out)
    return json.loads(Path(blob["json"]).read_text())


def test_rv_fallback_populates_contract_from_local_history(tmp_path, monkeypatch, capsys):
    snap = tmp_path / "chain_no_returns.json"
    snap.write_text(json.dumps({
        "spot": 689.0,
        "chain": [
            {"strike": 680, "iv": 0.40, "expiry_days": 7},
            {"strike": 690, "iv": 0.41, "expiry_days": 7},
            {"strike": 700, "iv": 0.42, "expiry_days": 7},
        ],
    }))

    payload = _run_main_with_args(
        monkeypatch,
        capsys,
        [
            "--snapshot-file", str(snap),
            "--n-batches", "1",
            "--paths-per-batch", "100",
            "--model", "jump",
            "--example", "put_diagonal",
        ],
    )

    assert payload["data_quality_status"] == "OK"
    assert payload["calibration"]["rv_source"] == "local_fallback"
    assert payload["calibration"]["rv10"] is not None
    assert payload["calibration"]["rv20"] is not None
    assert payload["edge_attribution"]["iv_rich_vs_rv"] is not None


def test_missing_rv_fails_closed_and_marks_reason(tmp_path, monkeypatch, capsys):
    snap = tmp_path / "chain_short_returns.json"
    snap.write_text(json.dumps({
        "spot": 689.0,
        "returns": [0.01, -0.01, 0.005],
        "chain": [
            {"strike": 680, "iv": 0.40, "expiry_days": 7},
            {"strike": 690, "iv": 0.41, "expiry_days": 7},
            {"strike": 700, "iv": 0.42, "expiry_days": 7},
        ],
    }))

    monkeypatch.setattr(ak, "load_local_returns_fallback", lambda _root: (None, None, None, None))

    payload = _run_main_with_args(
        monkeypatch,
        capsys,
        [
            "--snapshot-file", str(snap),
            "--n-batches", "1",
            "--paths-per-batch", "100",
            "--model", "jump",
            "--example", "put_diagonal",
        ],
    )

    assert payload["data_quality_status"] == "DATA_QUALITY_FAIL: missing_realized_vol"
    assert payload["edge_attribution"]["explainable"] is False
    assert payload["edge_attribution"]["explainable_reason"] == "missing_realized_vol"
    assert payload["gates"]["allow_trade"] is False
    assert payload["telemetry"]["options_mc_rv_missing_events"] == 1
