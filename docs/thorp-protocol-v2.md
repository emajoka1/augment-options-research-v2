# THORP PROTOCOL v2.0.0

Active quantitative risk policy for options-trading-research.

## Core changes vs prior policy

1. **EV seed p5 gate** loosened to `> -0.05R` with conviction bands.
2. **Stress ΔEV gate** loosened to `>= -0.15R` with stress bands.
3. **Survival gates fixed** (non-adaptive):
   - `CVaR95 > -0.90R`
   - `PL p5 > -0.50R`
4. **Regime-proportional stress shock calibration** by VIX tier.
5. **Composite grade sizing** for Kelly-aware implementation.

## Two-tier gate architecture

- **Tier A (Edge, adaptive):** EV seed p5 and Stress ΔEV
- **Tier B (Survival, fixed):** CVaR95 and PL p5

## Banding + sizing

- A/B = 100%
- C = 75%
- D = 60%

## Non-negotiables unchanged

Defined risk only, explainability required, liquidity rails, allocation limits, no auto-execution.

## Config source of truth

See `config/thorp_protocol_v2.json`.
