#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ak_system.ticket_phase_guard import phase_gate_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Stack phase execution order gate")
    parser.add_argument("ticket_id", help="ticket id (e.g. stack_phase2_rd_agent_hypothesis_lane)")
    parser.add_argument("--outbox", default="kb/outbox", help="outbox directory")
    args = parser.parse_args()

    allowed, reason = phase_gate_status(args.ticket_id, Path(args.outbox))
    print(reason)
    return 0 if allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
