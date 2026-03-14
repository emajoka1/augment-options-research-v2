#!/usr/bin/env python3
"""Heartbeat integrity checker with canonical MC command invocation.

Uses explicit script path (no PATH-dependent `mc_command` alias), emits
structured failures, and tracks telemetry for command unavailability.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "snapshots" / "heartbeat_metrics.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_metrics() -> Dict[str, Any]:
    if not METRICS_PATH.exists():
        return {
            "heartbeat_mc_command_unavailable_total": 0,
            "heartbeat_mc_command_unavailable_last_failure_ts": None,
        }
    try:
        data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        data.setdefault("heartbeat_mc_command_unavailable_total", 0)
        data.setdefault("heartbeat_mc_command_unavailable_last_failure_ts", None)
        return data
    except Exception:
        return {
            "heartbeat_mc_command_unavailable_total": 0,
            "heartbeat_mc_command_unavailable_last_failure_ts": None,
        }


def save_metrics(metrics: Dict[str, Any]) -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _failure(reason: str, detail: str, remediation: str) -> Dict[str, Any]:
    metrics = load_metrics()
    if reason == "mc_command_unavailable":
        metrics["heartbeat_mc_command_unavailable_total"] = int(
            metrics.get("heartbeat_mc_command_unavailable_total", 0)
        ) + 1
        metrics["heartbeat_mc_command_unavailable_last_failure_ts"] = _now_iso()
    save_metrics(metrics)
    return {
        "status": "HEARTBEAT_CHECK_FAILED",
        "reason": reason,
        "detail": detail,
        "remediation": remediation,
        "telemetry": {
            "heartbeat_mc_command_unavailable_total": metrics.get("heartbeat_mc_command_unavailable_total", 0),
            "heartbeat_mc_command_unavailable_last_failure_ts": metrics.get(
                "heartbeat_mc_command_unavailable_last_failure_ts"
            ),
        },
    }


def run_check(command_script: Path | None = None) -> Tuple[int, Dict[str, Any]]:
    script_path = command_script or (ROOT / "scripts" / "mc_command.py")
    if not script_path.exists():
        return 0, _failure(
            "mc_command_unavailable",
            f"canonical_target_missing:{script_path}",
            "Restore scripts/mc_command.py or update canonical command target.",
        )

    cmd = [sys.executable, str(script_path), "--json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return 0, _failure(
            "mc_command_unavailable",
            "python_runtime_unavailable",
            "Ensure python runtime is available for canonical mc_command invocation.",
        )

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().lower()
        if "command not found" in stderr:
            return 0, _failure(
                "mc_command_unavailable",
                "canonical_command_invocation_failed",
                "Use explicit python scripts/mc_command.py --json invocation and verify script availability.",
            )
        return 0, {
            "status": "HEARTBEAT_CHECK_FAILED",
            "reason": "mc_command_failed",
            "detail": (proc.stderr.strip() or "mc_command returned non-zero")[:240],
            "remediation": "Inspect scripts/mc_command.py output and upstream market data inputs.",
        }

    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return 0, {
            "status": "HEARTBEAT_CHECK_FAILED",
            "reason": "mc_command_invalid_json",
            "detail": str(exc)[:240],
            "remediation": "Fix JSON output contract in scripts/mc_command.py.",
        }

    checks = {
        "spot_integrity.ok": bool((payload.get("spot_integrity") or {}).get("ok")),
        "mc_provenance.source_stale": bool((payload.get("mc_provenance") or {}).get("source_stale")),
        "mc_provenance.counts_consistent": bool((payload.get("mc_provenance") or {}).get("counts_consistent")),
    }
    ok = checks["spot_integrity.ok"] and (not checks["mc_provenance.source_stale"]) and checks[
        "mc_provenance.counts_consistent"
    ]

    return 0, {
        "status": "HEARTBEAT_OK" if ok else "HEARTBEAT_CHECK_FAILED",
        "reason": None if ok else "integrity_field_failed",
        "checks": checks,
        "ok": ok,
        "canonical_command": " ".join(cmd),
    }


def main() -> int:
    override = os.environ.get("HEARTBEAT_MC_COMMAND_PATH")
    command_script = Path(override) if override else None
    code, out = run_check(command_script=command_script)
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
