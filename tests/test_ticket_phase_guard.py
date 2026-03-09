from pathlib import Path

from ak_system.ticket_phase_guard import phase_gate_status


def test_phase1_always_allowed(tmp_path: Path) -> None:
    allowed, reason = phase_gate_status("stack_phase1_akshare_qlib_adapter", tmp_path)
    assert allowed is True
    assert reason == "phase1_allowed"


def test_phase2_blocked_without_phase1_result(tmp_path: Path) -> None:
    allowed, reason = phase_gate_status("stack_phase2_rd_agent_hypothesis_lane", tmp_path)
    assert allowed is False
    assert reason == "blocked_waiting_for_stack_phase1_akshare_qlib_adapter"


def test_phase2_allowed_with_phase1_result(tmp_path: Path) -> None:
    (tmp_path / "stack_phase1_akshare_qlib_adapter__RESULT__20260305T203503Z.md").write_text("ok", encoding="utf-8")
    allowed, reason = phase_gate_status("stack_phase2_rd_agent_hypothesis_lane", tmp_path)
    assert allowed is True
    assert reason == "stack_phase2_rd_agent_hypothesis_lane_allowed_prev_phase_complete"


def test_phase3_blocked_without_phase2_result_even_if_phase1_exists(tmp_path: Path) -> None:
    (tmp_path / "stack_phase1_akshare_qlib_adapter__RESULT__20260305T203503Z.md").write_text("ok", encoding="utf-8")
    allowed, reason = phase_gate_status("stack_phase3_longport_optional_upgrade", tmp_path)
    assert allowed is False
    assert reason == "blocked_waiting_for_stack_phase2_rd_agent_hypothesis_lane"
