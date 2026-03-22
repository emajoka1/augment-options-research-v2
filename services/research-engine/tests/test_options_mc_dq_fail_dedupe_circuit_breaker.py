import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "ak_options_mc", Path(__file__).resolve().parents[1] / "scripts" / "ak_options_mc.py"
)
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)


def _prep_paths(monkeypatch, tmp_path):
    out = tmp_path / "kb" / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ak, "build_paths", lambda _p: type("P", (), {"kb_experiments": out})())
    monkeypatch.setattr(ak, "ensure_dirs", lambda _p: None)
    return out


def _run(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["ak_options_mc.py", *args])
    ak.main()
    return json.loads(capsys.readouterr().out)


def test_dq_fail_dedupes_within_cooldown(tmp_path, monkeypatch, capsys):
    out = _prep_paths(monkeypatch, tmp_path)
    base_args = [
        "--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1",
        "--rv-freshness-sla-seconds", "0", "--force-refresh-minutes", "120", "--dq-fail-dedupe-cooldown-minutes", "30",
    ]

    first = _run(monkeypatch, capsys, base_args)
    assert first["status"] == "FULL_REFRESH"

    second = _run(monkeypatch, capsys, base_args)
    assert second["status"] == "NO_ACTION_DQ_FAIL_DUPLICATE"
    assert second["data_quality_status"].startswith("DATA_QUALITY_FAIL")
    assert "metrics" not in second
    assert second["prior_artifact"]["path"] == first["json"]
    assert len(list(out.glob("options-mc-*.json"))) == 1


def test_dq_fail_republishes_after_cooldown(tmp_path, monkeypatch, capsys):
    _prep_paths(monkeypatch, tmp_path)
    args = [
        "--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1",
        "--rv-freshness-sla-seconds", "0", "--force-refresh-minutes", "120", "--dq-fail-dedupe-cooldown-minutes", "0",
    ]

    _run(monkeypatch, capsys, args)
    second = _run(monkeypatch, capsys, args)
    assert second["status"] == "FULL_REFRESH"
    payload = json.loads(Path(second["json"]).read_text())
    assert payload["telemetry"]["options_mc_runs_dq_fail_republished_after_cooldown"] == 1


def test_dq_reason_transition_bypasses_dedupe(tmp_path, monkeypatch, capsys):
    _prep_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        ak,
        "load_local_returns_fallback",
        lambda _root: (np.array([0.001] * 80, dtype=float), "local_fallback", "2026-03-09T00:00:00+00:00", 1200.0),
    )
    common = ["--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1", "--force-refresh-minutes", "120", "--dq-fail-dedupe-cooldown-minutes", "30"]

    first = _run(monkeypatch, capsys, [*common, "--rv-freshness-sla-seconds", "3600"])
    second = _run(monkeypatch, capsys, [*common, "--rv-freshness-sla-seconds", "0"])

    assert first["status"] == "FULL_REFRESH"
    assert second["status"] == "FULL_REFRESH"


def test_canonical_hash_change_bypasses_dedupe(tmp_path, monkeypatch, capsys):
    _prep_paths(monkeypatch, tmp_path)
    base = [
        "--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1",
        "--rv-freshness-sla-seconds", "0", "--force-refresh-minutes", "120", "--dq-fail-dedupe-cooldown-minutes", "30",
    ]

    _run(monkeypatch, capsys, base)
    second = _run(monkeypatch, capsys, [*base, "--spot", "701.0"])
    assert second["status"] == "FULL_REFRESH"
