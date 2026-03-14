# HEARTBEAT.md

# Proactive integrity checks (market pipeline)

- Verify latest `python3 scripts/mc_command.py --json` has:
  - `spot_integrity.ok == true`
  - `mc_provenance.source_stale == false`
  - `mc_provenance.counts_consistent == true`
- If any fail, alert immediately with the failing field(s) and pause trade-readiness messaging.
