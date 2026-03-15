#!/usr/bin/env python3
"""Deterministic approval gate for Steady Compounder mode.

Input JSON (stdin or --input):
{
  "structure": {"quality":0.72,"structural_r_clean":true,"invalidation_1r":true},
  "mc": {"ev_seed_p5_r":0.04,"pl_p5_r":-0.2,"cvar95_r":-0.6,"stress_delta_ev_r":-0.01,"explainable":true},
  "regime": {"bucket":"hostile","extreme_vol":false,"short_premium":false},
  "allocation": {"trades_today":1,"trades_week":3,"day_pnl_r":-0.5,"correlated_exposure_pct":40}
}
"""

from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "steady_compounder_mode.json"

STRUCTURAL_QUALITY_BY_TIER = {
    1: 0.70,  # VIX <= 15
    2: 0.65,  # VIX 15.01 - 19.99
    3: 0.52,  # VIX 20.00 - 27.99
    4: 0.45,  # VIX 28.00 - 35.99
    5: 0.40,  # VIX >= 36
}
HARD_FLOOR = 0.40


def fail(reasons, code="PASS"):
    return {"decision": code, "approved": False, "reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="Path to candidate JSON (default stdin)")
    args = ap.parse_args()

    cfg = json.loads(CFG.read_text())
    payload = json.loads(Path(args.input).read_text()) if args.input else json.loads(sys.stdin.read())

    reasons = []
    s = payload.get("structure", {})
    m = payload.get("mc", {})
    r = payload.get("regime", {})
    a = payload.get("allocation", {})
    ov = payload.get("overrides", {}) or {}

    sg = cfg["structural_gate"]
    # Dynamic runtime structural threshold by active regime tier; config min_quality_score remains fallback.
    tier = r.get("tier")
    tier_dynamic = STRUCTURAL_QUALITY_BY_TIER.get(int(tier)) if isinstance(tier, int) or (isinstance(tier, str) and str(tier).isdigit()) else None
    if tier_dynamic is None and isinstance(r.get("vix"), (int, float)):
        v = float(r.get("vix"))
        if v <= 15:
            tier_dynamic = 0.70
        elif v < 20:
            tier_dynamic = 0.65
        elif v < 28:
            tier_dynamic = 0.52
        elif v < 36:
            tier_dynamic = 0.45
        else:
            tier_dynamic = 0.40

    structural_quality_min = float(
        ov.get("structural_quality_min")
        if ov.get("structural_quality_min") is not None
        else (tier_dynamic if tier_dynamic is not None else sg.get("min_quality_score", 0.65))
    )
    structural_quality_min = max(structural_quality_min, HARD_FLOOR)

    if float(s.get("quality", -1)) < structural_quality_min:
        reasons.append("structural_quality_below_threshold")
    if sg["require_clean_structural_r"] and not bool(s.get("structural_r_clean")):
        reasons.append("structural_r_not_clean")
    if sg["require_1r_invalidation"] and not bool(s.get("invalidation_1r")):
        reasons.append("invalidation_not_1r_definable")

    mg = cfg["mc_gate"]
    mg_ov = ov.get("mc_gate", {}) or {}
    ev_seed_p5_min_r = float(mg_ov.get("ev_seed_p5_min_r", mg["ev_seed_p5_min_r"]))
    pl_p5_min_r = float(mg_ov.get("pl_p5_min_r", mg["pl_p5_min_r"]))
    cvar95_min_r = float(mg_ov.get("cvar95_min_r", mg["cvar95_min_r"]))
    stress_delta_ev_min_r = float(mg_ov.get("stress_delta_ev_min_r", mg["stress_delta_ev_min_r"]))

    if float(m.get("ev_seed_p5_r", -999)) <= ev_seed_p5_min_r:
        reasons.append("ev_seed_p5_below_threshold")
    if float(m.get("pl_p5_r", -999)) <= pl_p5_min_r:
        reasons.append("pl_p5_below_threshold")
    if float(m.get("cvar95_r", -999)) <= cvar95_min_r:
        reasons.append("cvar95_below_threshold")
    if float(m.get("stress_delta_ev_r", -999)) < stress_delta_ev_min_r:
        reasons.append("stress_delta_ev_below_threshold")
    if mg["require_explainable"] and not bool(m.get("explainable")):
        reasons.append("edge_not_explainable")

    ag = cfg["allocation"]
    if int(a.get("trades_today", 0)) >= int(ag["max_trades_per_day"]):
        reasons.append("max_trades_per_day_reached")
    if int(a.get("trades_week", 0)) >= int(ag["max_trades_per_week"]):
        reasons.append("max_trades_per_week_reached")
    if float(a.get("day_pnl_r", 0.0)) <= float(ag["daily_loss_cap_r"]):
        reasons.append("daily_loss_cap_reached")
    if float(a.get("correlated_exposure_pct", 0.0)) > float(ag["max_correlated_exposure_pct"]):
        reasons.append("correlated_exposure_too_high")

    if bool(r.get("extreme_vol")) and bool(r.get("short_premium")) and bool(cfg["regime_overrides"]["disable_short_premium_in_extreme_vol"]):
        reasons.append("short_premium_disabled_in_extreme_vol")

    if reasons:
        print(json.dumps(fail(reasons), indent=2))
        return 0

    mult = cfg["regime_risk_multiplier"].get(r.get("bucket", "neutral"), 1.0)
    print(json.dumps({"decision": "TRADE_READY", "approved": True, "risk_multiplier": mult, "reasons": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
