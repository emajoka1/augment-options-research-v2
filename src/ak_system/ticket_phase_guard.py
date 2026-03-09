from __future__ import annotations

from pathlib import Path

PHASE_ORDER = [
    "stack_phase1_akshare_qlib_adapter",
    "stack_phase2_rd_agent_hypothesis_lane",
    "stack_phase3_longport_optional_upgrade",
]


def _has_result(ticket_id: str, outbox_dir: Path) -> bool:
    return any(outbox_dir.glob(f"*{ticket_id}__RESULT__*.md"))


def phase_gate_status(ticket_id: str, outbox_dir: Path) -> tuple[bool, str]:
    """Return (allowed, reason) for stack phase execution order control."""
    if ticket_id not in PHASE_ORDER:
        return True, "not_a_stack_phase_ticket"

    idx = PHASE_ORDER.index(ticket_id)
    if idx == 0:
        return True, "phase1_allowed"

    required_prev = PHASE_ORDER[idx - 1]
    if _has_result(required_prev, outbox_dir):
        return True, f"{ticket_id}_allowed_prev_phase_complete"

    return False, f"blocked_waiting_for_{required_prev}"
