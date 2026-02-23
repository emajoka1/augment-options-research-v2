from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_report_json_md(out_base: Path, payload: dict) -> tuple[Path, Path]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    j = out_base / f"options-mc-{ts}.json"
    m = out_base / f"options-mc-{ts}.md"
    out_base.mkdir(parents=True, exist_ok=True)

    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    metrics = payload.get("metrics", {})
    assumptions = payload.get("assumptions", {})
    stress = payload.get("stress", {})
    breakevens = payload.get("breakevens", [])
    md = f"""# Trade Brief — Options Monte Carlo

## Assumptions
- Model: {assumptions.get('model')}
- Spot: {assumptions.get('spot')}
- r/q: {assumptions.get('r')} / {assumptions.get('q')}
- Expiry (years): {assumptions.get('expiry_years')}
- Paths: {assumptions.get('n_paths')}

## Expected Move vs Breakevens
- Breakevens: {breakevens}

## Core Metrics (after costs)
- EV: {metrics.get('ev'):.4f}
- POP: {metrics.get('pop'):.3f}
- PoT: {metrics.get('pot'):.3f}
- VaR95: {metrics.get('var95'):.4f}
- CVaR95: {metrics.get('cvar95'):.4f}
- Profit factor: {metrics.get('profit_factor'):.3f}

## Execution Drag
- baseline spread bps: {stress.get('spread_bps')}
- baseline slippage bps: {stress.get('slippage_bps')}
- partial fill prob: {stress.get('partial_fill_prob')}

## Decision
- Rule: TRADE only if EV>0 and CVaR within limits.
"""
    m.write_text(md, encoding="utf-8")
    return j, m
