from __future__ import annotations

from pathlib import Path

PHASE_ORDER = [
    "stack_phase1_akshare_qlib_adapter",
    "stack_phase2_rd_agent_hypothesis_lane",
    "stack_phase3_longport_optional_upgrade",
]

_REQUIRED_RESULT_MARKERS = (
    "PYTHONPATH=src ./.venv/bin/python -m pytest -q",
    "acceptance",
)


def _result_files(ticket_id: str, outbox_dir: Path) -> list[Path]:
    return sorted(outbox_dir.glob(f"*{ticket_id}__RESULT__*.md"))


def _has_required_proof(result_path: Path) -> bool:
    text = result_path.read_text(encoding="utf-8", errors="ignore").lower()
    if not all(marker.lower() in text for marker in _REQUIRED_RESULT_MARKERS):
        return False

    has_acceptance_pass_signal = (
        "acceptance tests passing" in text
        or "acceptance tests: pass" in text
        or "acceptance tests passed" in text
    )
    return has_acceptance_pass_signal


def _has_verified_result(ticket_id: str, outbox_dir: Path) -> bool:
    result_files = _result_files(ticket_id, outbox_dir)
    if not result_files:
        return False
    # Require at least one result artifact with full proof markers.
    return any(_has_required_proof(path) for path in reversed(result_files))


def phase_gate_status(ticket_id: str, outbox_dir: Path) -> tuple[bool, str]:
    """Return (allowed, reason) for stack phase execution order control."""
    if ticket_id not in PHASE_ORDER:
        return True, "not_a_stack_phase_ticket"

    idx = PHASE_ORDER.index(ticket_id)
    if idx == 0:
        return True, "phase1_allowed"

    required_prev = PHASE_ORDER[idx - 1]
    if _has_verified_result(required_prev, outbox_dir):
        return True, f"{ticket_id}_allowed_prev_phase_complete"

    if _result_files(required_prev, outbox_dir):
        return False, f"blocked_waiting_for_{required_prev}_verified_result"

    return False, f"blocked_waiting_for_{required_prev}"
