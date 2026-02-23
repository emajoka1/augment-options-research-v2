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
    gates = payload.get("gates", {})
    breakevens = payload.get("breakevens", [])

    legs_lines = []
    for leg in assumptions.get("legs", []):
        legs_lines.append(f"- {leg.get('side')} {leg.get('qty')} {leg.get('option_type').upper()} {leg.get('strike')}")
    legs_txt = "\n".join(legs_lines) if legs_lines else "- N/A"

    md = f"""# Trade Brief — Options Monte Carlo

## Strategy
- Name: **{assumptions.get('strategy')}**
- Legs:
{legs_txt}

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
- PoT: {metrics.get('pot'):.3f} *(pathwise: P(P/L reaches profit target before stop/expiry))*
- VaR95: {metrics.get('var95'):.4f}
- CVaR95: {metrics.get('cvar95'):.4f}
- Profit factor: {metrics.get('profit_factor'):.3f}

## Execution Drag
- baseline spread bps: {stress.get('spread_bps')}
- baseline slippage bps: {stress.get('slippage_bps')}
- partial fill prob: {stress.get('partial_fill_prob')}

## Survival-first Gates
- EV > +0.05R: {gates.get('ev_gt_0.05R')}
- CVaR95 > -1.0R: {gates.get('cvar95_gt_-1R')}
- POP/PoT gate: {gates.get('pop_or_pot')}
- Slippage sensitivity gate: {gates.get('slippage_sensitivity_ok')}
- ALLOW TRADE: **{gates.get('allow_trade')}**
"""
    m.write_text(md, encoding="utf-8")
    return j, m
