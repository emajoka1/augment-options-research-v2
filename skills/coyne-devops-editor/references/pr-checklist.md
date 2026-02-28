# PR Checklist

Use this template in every PR description.

## Summary
- What changed
- Why it changed
- Scope boundaries respected

## Screenshots (UI only)
- Before/after screenshots or short GIF
- Key states covered (desktop/mobile if relevant)

## Test Results
- Commands run (lint/test/typecheck/build)
- Pass/fail status
- Not-run items with reason

## Risk Notes
- Potential regressions
- Data or behavior impact
- Rollback approach

## Guardrail Confirmation
- [ ] Repo is whitelisted
- [ ] Paths are in allowed folders only
- [ ] Branch created (no direct push to main)
- [ ] No billing/infra/secrets changes
- [ ] No new dependencies (or explicit approval linked)
