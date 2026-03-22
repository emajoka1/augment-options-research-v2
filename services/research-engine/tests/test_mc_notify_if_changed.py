import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "mc_notify_if_changed", Path(__file__).resolve().parents[1] / "scripts" / "mc_notify_if_changed.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_server_error_emits_bounded_fallback_and_logs(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(mod, "STATE_PATH", state)
    monkeypatch.setattr(mod, "TRACE_LOG", trace)
    monkeypatch.setenv("OPENCLAW_REQUEST_ID", "req_test_server_error")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="server_error")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mc_notify_if_changed.py",
            "--command-retries",
            "1",
            "--command-timeout-sec",
            "1",
            "--backoff-sec",
            "0",
        ],
    )
    assert mod.main() == 0
    out = capsys.readouterr().out.strip()
    assert "MC watchdog fallback" in out
    assert "still_running/retrying=true" in out
    assert "server_error" in out

    saved = json.loads(state.read_text())
    assert saved["failure_window_open"] is True
    assert saved["request_id"] == "req_test_server_error"

    lines = [json.loads(x) for x in trace.read_text().strip().splitlines()]
    assert any(x["event"] == "mc_command_error" for x in lines)

    # second failure in same window should dedupe
    monkeypatch.setattr(
        sys,
        "argv",
        ["mc_notify_if_changed.py", "--command-retries", "1", "--command-timeout-sec", "1", "--backoff-sec", "0"],
    )
    assert mod.main() == 0
    out2 = capsys.readouterr().out.strip()
    assert out2 == "NO_CHANGE"


def test_timeout_then_retry_success_returns_partial_retry_path(monkeypatch):
    calls = {"n": 0}

    def fake_run(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))
        payload = {"action_state": "WATCH", "data_status": "OK", "final_decision": "PASS", "spot": 500}
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(mod, "write_trace", lambda *a, **k: None)

    cur, diag = mod.run_mc_json_with_guard(
        max_attempts=1,
        retry_delay_sec=1,
        skip_live=True,
        command_timeout_sec=1,
        command_retries=2,
        backoff_sec=0,
        request_id="req_timeout_then_ok",
    )

    assert cur is not None
    assert cur["data_status"] == "OK"
    assert diag["ok"] is True
    assert diag["attempts"] == 2
    assert diag["errors"]
    assert diag["errors"][0]["kind"] == "timeout"
