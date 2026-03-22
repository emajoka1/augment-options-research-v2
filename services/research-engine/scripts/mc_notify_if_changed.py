#!/usr/bin/env python3
"""Run MC and emit notification text only when state changes.

Designed for cron/periodic execution.
Adds bounded-response timeout/retry guard with failure-window dedupe.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "snapshots" / "mc_last_state.json"
TRACE_LOG = ROOT / "logs" / "mc_notify_traces.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_trace(event: str, request_id: str, payload: Dict[str, Any]) -> None:
    TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": _now_iso(),
        "event": event,
        "request_id": request_id,
        **payload,
    }
    with TRACE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_mc_json_with_guard(
    max_attempts: int,
    retry_delay_sec: int,
    skip_live: bool,
    command_timeout_sec: int,
    command_retries: int,
    backoff_sec: int,
    request_id: str,
) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    cmd = [
        "python3",
        "scripts/mc_command.py",
        "--json",
        "--max-attempts",
        str(max_attempts),
        "--retry-delay-sec",
        str(retry_delay_sec),
    ]
    if skip_live:
        cmd.append("--skip-live")

    attempts = max(1, command_retries)
    errors: list[Dict[str, Any]] = []
    for i in range(1, attempts + 1):
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=command_timeout_sec)
            elapsed_ms = int((time.time() - t0) * 1000)
            if p.returncode != 0:
                err = {
                    "attempt": i,
                    "kind": "server_error",
                    "message": (p.stderr.strip() or "mc_command failed"),
                    "elapsed_ms": elapsed_ms,
                }
                errors.append(err)
                write_trace("mc_command_error", request_id, err)
            else:
                try:
                    cur = json.loads(p.stdout)
                    write_trace("mc_command_ok", request_id, {"attempt": i, "elapsed_ms": elapsed_ms})
                    return cur, {
                        "ok": True,
                        "attempts": i,
                        "errors": errors,
                        "elapsed_ms": elapsed_ms,
                    }
                except Exception as e:  # pragma: no cover - defensive
                    err = {
                        "attempt": i,
                        "kind": "json_parse_error",
                        "message": str(e),
                        "elapsed_ms": elapsed_ms,
                    }
                    errors.append(err)
                    write_trace("mc_command_error", request_id, err)
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - t0) * 1000)
            err = {
                "attempt": i,
                "kind": "timeout",
                "message": f"command exceeded {command_timeout_sec}s",
                "elapsed_ms": elapsed_ms,
            }
            errors.append(err)
            write_trace("mc_command_timeout", request_id, err)

        if i < attempts:
            time.sleep(max(0, backoff_sec) * i)

    return None, {
        "ok": False,
        "attempts": attempts,
        "errors": errors,
    }


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def changed(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    keys = ["action_state", "data_status", "final_decision"]
    return any(prev.get(k) != cur.get(k) for k in keys)


def summary(cur: Dict[str, Any]) -> str:
    miss = cur.get("missing_required") or []
    miss_txt = ", ".join(miss) if miss else "none"
    return (
        f"MC update: {cur.get('action_state')} | status={cur.get('data_status')} | "
        f"SPY={cur.get('spot')} | regime={cur.get('regime')} ({cur.get('trend')}) | "
        f"decision={cur.get('final_decision')} | missing={miss_txt}"
    )


def fallback_summary(diag: Dict[str, Any], request_id: str) -> str:
    last = (diag.get("errors") or [{}])[-1]
    reason = last.get("kind") or "unknown_error"
    msg = (last.get("message") or "").replace("\n", " ")[:180]
    return (
        f"MC watchdog fallback: status=RETRYING | still_running/retrying=true | "
        f"reason={reason} | detail={msg or 'n/a'} | attempts={diag.get('attempts')} | request_id={request_id}"
    )


def maybe_notify(text: str, enabled: bool) -> None:
    if not enabled:
        return
    subprocess.run(
        ["openclaw", "system", "event", "--text", text, "--mode", "now"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def maybe_notify_telegram(text: str, enabled: bool, chat_id: str | None) -> None:
    if not enabled:
        return
    token = os.environ.get("TG_BOT_TOKEN")
    cid = chat_id or os.environ.get("TG_CHAT_ID")
    if not token or not cid:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urlencode({"chat_id": cid, "text": text}).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=8) as r:
            _ = r.read()
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Run MC and notify only on state changes")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--retry-delay-sec", type=int, default=180)
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--notify", action="store_true", help="Emit openclaw system event on change")
    ap.add_argument("--telegram", action="store_true", help="Send Telegram message on change (requires TG_BOT_TOKEN + TG_CHAT_ID)")
    ap.add_argument("--tg-chat-id", default=None, help="Override Telegram chat id (else TG_CHAT_ID env)")
    ap.add_argument("--force", action="store_true", help="Emit summary even if state unchanged")
    ap.add_argument("--command-timeout-sec", type=int, default=20)
    ap.add_argument("--command-retries", type=int, default=2)
    ap.add_argument("--backoff-sec", type=int, default=2)
    args = ap.parse_args()

    request_id = os.environ.get("OPENCLAW_REQUEST_ID") or f"req_{uuid.uuid4().hex[:10]}"
    prev = load_state()

    cur, diag = run_mc_json_with_guard(
        args.max_attempts,
        args.retry_delay_sec,
        args.skip_live,
        args.command_timeout_sec,
        args.command_retries,
        args.backoff_sec,
        request_id,
    )

    if cur is None:
        txt = fallback_summary(diag, request_id)
        # dedupe: emit at most once per failure window unless forced
        failure_window_open = bool(prev.get("failure_window_open"))
        should_emit = args.force or not failure_window_open
        if should_emit:
            print(txt)
            maybe_notify(txt, args.notify)
            maybe_notify_telegram(txt, args.telegram, args.tg_chat_id)
        else:
            print("NO_CHANGE")

        save_state(
            {
                "timestamp": _now_iso(),
                "failure_window_open": True,
                "last_failure": (diag.get("errors") or [{}])[-1],
                "request_id": request_id,
                "action_state": prev.get("action_state"),
                "data_status": prev.get("data_status"),
                "final_decision": prev.get("final_decision"),
                "spot": prev.get("spot"),
            }
        )
        return 0

    is_changed = changed(prev, cur)
    should_emit = args.force or is_changed or not prev or bool(prev.get("failure_window_open"))

    if should_emit:
        txt = summary(cur)
        print(txt)
        maybe_notify(txt, args.notify)
        maybe_notify_telegram(txt, args.telegram, args.tg_chat_id)
    else:
        print("NO_CHANGE")

    save_state(
        {
            "timestamp": _now_iso(),
            "failure_window_open": False,
            "request_id": request_id,
            "action_state": cur.get("action_state"),
            "data_status": cur.get("data_status"),
            "final_decision": cur.get("final_decision"),
            "spot": cur.get("spot"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
