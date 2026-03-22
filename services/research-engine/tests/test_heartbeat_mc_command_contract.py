import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "heartbeat_integrity_check", Path(__file__).resolve().parents[1] / "scripts" / "heartbeat_integrity_check.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_path_without_mc_command_uses_canonical_explicit_script(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        payload = {
            "spot_integrity": {"ok": True},
            "mc_provenance": {"source_stale": False, "counts_consistent": True},
        }
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    code, out = mod.run_check()

    assert code == 0
    assert out["status"] == "HEARTBEAT_OK"
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1].endswith("scripts/mc_command.py")
    assert captured["cmd"][2:] == ["--json"]


def test_missing_canonical_target_emits_structured_unavailable_and_increments_counter(tmp_path, monkeypatch):
    metrics = tmp_path / "heartbeat_metrics.json"
    monkeypatch.setattr(mod, "METRICS_PATH", metrics)

    missing = tmp_path / "missing_mc_command.py"
    code, out = mod.run_check(command_script=missing)

    assert code == 0
    assert out["status"] == "HEARTBEAT_CHECK_FAILED"
    assert out["reason"] == "mc_command_unavailable"
    assert "canonical_target_missing" in out["detail"]

    saved = json.loads(metrics.read_text())
    assert saved["heartbeat_mc_command_unavailable_total"] == 1
    assert saved["heartbeat_mc_command_unavailable_last_failure_ts"]


def test_integration_fields_evaluated_in_clean_path(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        payload = {
            "spot_integrity": {"ok": True},
            "mc_provenance": {"source_stale": False, "counts_consistent": True},
        }
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    _code, out = mod.run_check()
    assert out["checks"]["spot_integrity.ok"] is True
    assert out["checks"]["mc_provenance.source_stale"] is False
    assert out["checks"]["mc_provenance.counts_consistent"] is True


def test_no_raw_command_not_found_leaks_in_normalized_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="zsh: command not found: mc_command")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    _code, out = mod.run_check()
    assert out["status"] == "HEARTBEAT_CHECK_FAILED"
    assert out["reason"] == "mc_command_unavailable"
    assert "command not found" not in json.dumps(out)
