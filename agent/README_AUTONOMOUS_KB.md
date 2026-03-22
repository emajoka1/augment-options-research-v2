# Autonomous Research + Knowledge System (Options Assistant)

See `docs/AUTONOMOUS_KB_SYSTEM.md` for full runbook.

## Quickstart

```bash
PYTHONPATH=src python3 scripts/ak_scheduler.py --mode once
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Promotion / rollback

```bash
PYTHONPATH=src python3 scripts/ak_admin.py approve proposals/<proposal>.json --approver "YourName"
PYTHONPATH=src python3 scripts/ak_admin.py rollback
```
