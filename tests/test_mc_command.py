import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "mc_command", Path(__file__).resolve().parents[1] / "scripts" / "mc_command.py"
)
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def _brief(final_decision="NO TRADE", missing=None):
    return {
        "TRADE BRIEF": {
            "Spot": 682.92,
            "Regime": {
                "riskState": "Neutral",
                "trend": "down_or_flat",
                "vixDirection": "down",
                "ratesDirection": "up",
            },
            "Final Decision": final_decision,
            "missingRequiredData": missing or [],
            "Candidates": [
                {"type": "debit", "decision": "PASS", "score": {"Total": 61}, "gateFailures": ["missing_fields"]}
            ],
        }
    }


def test_normalize_partial_data_forces_no_trade():
    live = {"symbolsWithData": 0}
    n = mc.normalize(live, _brief(final_decision="TRADE", missing=[]))
    assert n["data_status"] == "PARTIAL_DATA"
    assert n["action_state"] == "NO_TRADE"


def test_normalize_trade_ready_when_clean():
    live = {"symbolsWithData": 12}
    n = mc.normalize(live, _brief(final_decision="TRADE", missing=[]))
    assert n["data_status"] == "OK"
    assert n["action_state"] == "TRADE_READY"


def test_render_markdown_contains_sections():
    live = {"symbolsWithData": 12}
    n = mc.normalize(live, _brief(final_decision="PASS", missing=["ivCurrent"]))
    txt = mc.render_markdown(n, 1, 2)
    assert "Status:" in txt
    assert "Missing for trade-ready" in txt
    assert "`ivCurrent`" in txt
