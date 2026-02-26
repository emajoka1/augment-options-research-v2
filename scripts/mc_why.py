#!/usr/bin/env python3
"""Explain current MC decision gates in plain terms.

Includes latest EV/CVaR metrics from the options Monte Carlo engine, if available.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MC_DIR = ROOT / "kb" / "experiments"


def run_mc_json() -> dict:
    p = subprocess.run(
        ["python3", "scripts/mc_command.py", "--max-attempts", "1", "--retry-delay-sec", "0", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "mc_command failed")
    return json.loads(p.stdout)


def latest_options_mc() -> dict | None:
    files = sorted(MC_DIR.glob("options-mc-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:
        return None


def main() -> int:
    m = run_mc_json()
    raw = (m.get("raw") or {}).get("TRADE BRIEF", {})
    vol = raw.get("Volatility State") or {}
    top = m.get("top_candidate") or {}
    missing = m.get("missing_required") or []
    omc = latest_options_mc()

    print("MC Why")
    print(f"- Action: {m.get('action_state')}")
    print(f"- Status: {m.get('data_status')} | Source: {m.get('data_source')}")
    print(f"- Decision: {m.get('final_decision')}")
    print(
        f"- Regime: {m.get('regime')} | trend={m.get('trend')} | "
        f"VIX={m.get('vix_direction')} | US10Y={m.get('rates_direction')}"
    )
    print(f"- Vol label: {vol.get('volLabel')} | ivCurrent={vol.get('ivCurrent')}")

    if missing:
        print(f"- Gate block: missing required fields -> {', '.join(missing)}")
    else:
        print("- Gate block: none")

    if top.get("type"):
        print(
            f"- Top candidate: {top.get('type')} score={top.get('score')} "
            f"decision={top.get('decision')}"
        )
        gf = top.get("gate_failures") or []
        print(f"- Candidate gate failures: {', '.join(gf) if gf else 'none'}")
    else:
        print("- Top candidate: none (no structure passed candidate selection)")

    if omc:
        metrics = omc.get("metrics") or {}
        ms = omc.get("multi_seed_confidence") or {}
        gate = omc.get("gates") or {}
        print("- MC risk metrics (latest options MC run):")
        print(
            f"  EV={metrics.get('ev')} | VaR95={metrics.get('var95')} | CVaR95={metrics.get('cvar95')}"
        )
        print(
            f"  seeds(batches)={ms.get('n_batches')} x paths/batch={ms.get('paths_per_batch')} | "
            f"EV_mean={ms.get('ev_mean')} | EV_p5={ms.get('ev_5th_percentile')} | "
            f"CVaR_mean={ms.get('cvar_mean')}"
        )
        print(f"  allow_trade={gate.get('allow_trade')} | regime={gate.get('regime')}")
    else:
        print("- MC risk metrics: unavailable (no options-mc report found yet)")

    print("- Intuition: market is not giving a clear priced edge that passes all gates yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
