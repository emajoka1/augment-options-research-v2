from __future__ import annotations

from typing import Any, Dict

ESTIMATOR_VERSION = "v1"


def risk_cap_dollars(account_size: float, risk_pct: float, max_risk_dollars: float) -> float:
    return float(max_risk_dollars) if float(max_risk_dollars) > 0 else (float(account_size) * float(risk_pct))


def max_loss_debit(debit: float) -> float:
    return max(0.0, float(debit)) * 100.0


def max_loss_credit(width: float, credit: float) -> float:
    return max(0.0, float(width) - float(credit)) * 100.0


def max_loss_condor(wing: float, credit: float) -> float:
    return max_loss_credit(wing, credit)


def feasible_under_cap(max_loss: float, risk_cap: float) -> bool:
    return float(max_loss) <= float(risk_cap)


def estimate_structure_risk(structure_type: str, *, risk_cap: float, debit: float | None = None, credit: float | None = None, width: float | None = None, wing: float | None = None, max_loss: float | None = None) -> Dict[str, Any]:
    st = (structure_type or "").lower()
    if max_loss is None:
        if st in {"debit", "diagonal", "calendar"}:
            max_loss = max_loss_debit(debit or 0.0)
        elif st in {"credit", "put_credit", "call_credit"}:
            max_loss = max_loss_credit(width or 0.0, credit or 0.0)
        elif st in {"condor", "iron_condor", "iron_fly"}:
            max_loss = max_loss_condor(wing or width or 0.0, credit or 0.0)
        else:
            max_loss = float(max_loss or 0.0)
    return {
        "version": ESTIMATOR_VERSION,
        "structure_type": structure_type,
        "max_loss": float(max_loss),
        "risk_cap": float(risk_cap),
        "feasible_under_cap": feasible_under_cap(float(max_loss), float(risk_cap)),
    }
