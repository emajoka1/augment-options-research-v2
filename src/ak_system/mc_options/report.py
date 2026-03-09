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
    breakeven_reason = payload.get("breakeven_reason")
    edge = payload.get("edge_attribution", {})
    fh = payload.get("friction_hurdle", {})
    ms = payload.get("multi_seed_confidence", {})

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
- Breakevens: {breakevens if breakevens is not None else breakeven_reason}

## Core Metrics (after costs)
- EV: {metrics.get('ev'):.4f}
- POP: {metrics.get('pop'):.3f}
- PoT: {metrics.get('pot'):.3f} *(pathwise: P(P/L reaches profit target before stop/expiry))*
- VaR95: {metrics.get('var95'):.4f}
- CVaR95: {metrics.get('cvar95'):.4f}
- Profit factor: {metrics.get('profit_factor'):.3f}

## Multi-seed Confidence (fairness)
- batches × paths: {ms.get('n_batches')} × {ms.get('paths_per_batch')}
- EV_mean: {ms.get('ev_mean')}
- EV_std: {ms.get('ev_std')}
- EV_5th_percentile: {ms.get('ev_5th_percentile')}
- POP_mean: {ms.get('pop_mean')}
- CVaR_mean: {ms.get('cvar_mean')}
- CVaR_worst: {ms.get('cvar_worst')}

## Execution Drag
- baseline spread bps: {stress.get('spread_bps')}
- baseline slippage bps: {stress.get('slippage_bps')}
- partial fill prob: {stress.get('partial_fill_prob')}

## Friction Hurdle Rate
- EV_mid: {fh.get('ev_mid')}
- EV_real: {fh.get('ev_real')}
- EV_stress: {fh.get('ev_stress')}
- ΔEV_real (real-mid): {fh.get('delta_ev_real')}
- ΔEV_stress (stress-mid): {fh.get('delta_ev_stress')}

## Edge Attribution (required)
- IV rich vs RV: {edge.get('iv_rich_vs_rv')}
- Mean-revert regime probability: {edge.get('mean_reversion_regime_probability')}
- Structure/expected-move match: {edge.get('structure_expected_move_match')}
- Explainable edge: {edge.get('explainable')}

## Survival-first Gates (Regime-conditioned)
- Dominant regime: **{gates.get('regime')}**
- EV threshold (R): {gates.get('ev_threshold_R')} | pass={gates.get('ev_gate')}
- EV_5th percentile gate (> +0.02R): {gates.get('ev_ci_gate')}
- CVaR threshold (R): {gates.get('cvar_threshold_R')} | pass={gates.get('cvar_gate')}
- CVaR worst-case gate: {gates.get('cvar_worst_gate')}
- POP/PoT gate: {gates.get('pop_or_pot')}
- Slippage sensitivity gate: {gates.get('slippage_sensitivity_ok')}
- Stress EV not catastrophic: {gates.get('stress_ev_not_catastrophic')}
- ALLOW TRADE: **{gates.get('allow_trade')}**
"""
    m.write_text(md, encoding="utf-8")
    return j, m
