import importlib.util
import json
import sys
from datetime import datetime, timezone
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
    monkeypatch.setattr(
        ak,
        "load_local_returns_fallback",
        lambda _root: (np.array([0.001] * 80, dtype=float), "local_fallback", datetime.now(timezone.utc).isoformat(), 10.0),
    )
    return out


def _run(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["ak_options_mc.py", *args])
    ak.main()
    return json.loads(capsys.readouterr().out)


def test_identical_inputs_skip_and_reference_prior(tmp_path, monkeypatch, capsys):
    out = _prep_paths(monkeypatch, tmp_path)
    args = ["--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1", "--force-refresh-minutes", "120"]

    first = _run(monkeypatch, capsys, args)
    assert first["status"] == "FULL_REFRESH"
    first_path = Path(first["json"])

    second = _run(monkeypatch, capsys, args)
    assert second["status"] == "NO_NEW_INPUTS"
    assert second["prior_artifact"]["path"] == str(first_path)
    assert sorted(out.glob("options-mc-*.json"))[-1] == first_path


def test_change_in_canonical_input_generates_full_artifact(tmp_path, monkeypatch, capsys):
    _prep_paths(monkeypatch, tmp_path)
    base_args = ["--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1"]
    _run(monkeypatch, capsys, base_args)
    changed = _run(monkeypatch, capsys, [*base_args, "--spot", "701.0"])

    assert changed["status"] == "FULL_REFRESH"
    payload = json.loads(Path(changed["json"]).read_text())
    assert float(payload["assumptions"]["spot"]) == 701.0


def test_force_refresh_cadence_allows_full_refresh_and_telemetry(tmp_path, monkeypatch, capsys):
    _prep_paths(monkeypatch, tmp_path)
    args = ["--n-batches", "1", "--paths-per-batch", "100", "--expiry-days", "1", "--dt-days", "1", "--force-refresh-minutes", "0"]

    _run(monkeypatch, capsys, args)
    second = _run(monkeypatch, capsys, args)
    assert second["status"] == "FULL_REFRESH"

    payload = json.loads(Path(second["json"]).read_text())
    assert payload["telemetry"]["options_mc_runs_forced_refresh"] == 1
