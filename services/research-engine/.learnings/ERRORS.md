# ERRORS

## [ERR-20260306-001] integrity_watchdog_spot_integrity_null

**Logged**: 2026-03-06T00:12:00Z
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
Watchdog repeatedly emitted alerts because `spot_integrity.ok` was null.

### Error
```
ALERT: integrity watchdog check failed.
spot_integrity.ok=null (expected true)
```

### Context
- Operation: periodic `integrity-watchdog` cron
- Pipeline: `scripts/mc_command.py --json`
- Impact: trade-readiness messaging paused repeatedly

### Suggested Fix
Compute spot integrity against fallback source when primary quote endpoint unavailable; emit explicit unavailable failure state instead of null.

### Metadata
- Reproducible: yes
- Related Files: scripts/mc_command.py

---

## [ERR-20260308-002] mc_command_binary_missing

**Logged**: 2026-03-08T16:13:21Z
**Priority**: high
**Status**: pending
**Area**: config

### Summary
Heartbeat integrity check could not run because `mc_command` is not available in PATH.

### Error
```
zsh:1: command not found: mc_command
```

### Context
- Operation: heartbeat task from `HEARTBEAT.md`
- Command attempted: `mc_command --json`
- Working dir: `/Users/forge/.openclaw/workspace`
- Result: unable to verify required fields (`spot_integrity.ok`, `mc_provenance.source_stale`, `mc_provenance.counts_consistent`)

### Suggested Fix
Use the documented local command/script for MC JSON generation (likely `scripts/mc_command.py --json`), or add `mc_command` wrapper to PATH.

### Metadata
- Reproducible: yes
- Related Files: HEARTBEAT.md, scripts/mc_command.py
- See Also: ERR-20260306-001

---
