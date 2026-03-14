- Ticket id: `bot_response_timeout_guard`

## Ticket summary
Added bounded timeout + retry-with-backoff around MC invocation for watchdog flow, guaranteed fallback response on timeout/server errors, structured trace logs, and failure-window dedupe to prevent repeated alert spam.

## Changes made
- Added guarded runner `run_mc_json_with_guard(...)` in `scripts/mc_notify_if_changed.py`:
  - subprocess timeout via `timeout=`
  - retries with linear backoff (`backoff_sec * attempt`)
  - handles server error, timeout, and JSON parse errors
- Added bounded fallback user-facing output when command fails:
  - `MC watchdog fallback: status=RETRYING | still_running/retrying=true ...`
- Added structured trace logging to `logs/mc_notify_traces.jsonl` with request id.
- Added failure-window dedupe:
  - emits only one fallback alert while failure window remains open
  - subsequent failed polls output `NO_CHANGE`
  - closes failure window on recovery
- Added new CLI flags (safe defaults):
  - `--command-timeout-sec` (default `20`)
  - `--command-retries` (default `2`)
  - `--backoff-sec` (default `2`)

## Files changed
- `scripts/mc_notify_if_changed.py`
- `tests/test_mc_notify_if_changed.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_mc_notify_if_changed.py`
- Output: `.. [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `............................ [100%]`

## Manual proof (timeout log + fallback output)
- Fallback output sample:
  - `MC watchdog fallback: status=RETRYING | still_running/retrying=true | reason=timeout | detail=command exceeded 0s | attempts=1 | request_id=req_manual_timeout_demo`
- Structured trace sample (`logs/mc_notify_traces.jsonl`):
  - `{"event":"mc_command_timeout","request_id":"req_manual_timeout_demo","kind":"timeout","message":"command exceeded 0s",...}`

## Risks / follow-ups
- No trading gate thresholds changed.
- No Telegram-facing schema keys were renamed/removed; only watchdog fallback text added in failure path.
- Follow-up ticket `schema_lock_mc_commands` can lock additional contracts for `/mc` variants.

## Commit hash
- `f59c544`
