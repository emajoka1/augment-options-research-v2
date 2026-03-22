# LEARNINGS

## [LRN-20260306-001] best_practice

**Logged**: 2026-03-06T00:12:00Z
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
Integrity checks must use multi-source spot references with explicit fallback and fail-closed behavior.

### Details
Repeated watchdog failures were caused by `spot_integrity.ok` becoming null when the primary reference source was unavailable. This can create alert loops and reduce operator trust even when other integrity checks pass.

### Suggested Action
Keep spot reference arbitration deterministic: primary CBOE mid, fallback Yahoo regular market, and explicit failure code `spot_integrity_reference_unavailable` when neither source is available.

### Metadata
- Source: conversation
- Related Files: scripts/mc_command.py
- Tags: integrity, spot, fallback, fail-closed

---
