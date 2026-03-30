import json
from datetime import datetime, timezone

import scripts.spy_free_brief as sfb


NO_CAND_MSG = "NO_CANDIDATES: no structure met liquidity/execution constraints for this setup."


def _row(side: str, strike: float, mark: float, *, delta: float, expiry: str = "2026-03-20", dte: int = 7):
    return {
        "expiry": expiry,
        "dte": dte,
        "strike": strike,
        "side": side,
        "symbol": f"SPY_{expiry}_{side}{int(strike*1000):08d}",
        "bid": mark - 0.0001,
        "ask": mark + 0.0001,
        "mark": mark,
        "delta": delta,
        "iv": 0.22,
        "openInterest": 5000,
        "dayVolume": 1500,
        "liquid": True,
    }


def test_candidate_generation_no_longer_pre_filters_on_risk_cap(monkeypatch):
    monkeypatch.setattr(sfb, "MAX_RISK_DOLLARS", 75.0)

    rows = [
        _row("C", 100.0, 5.00, delta=0.40),
        _row("C", 105.0, 4.00, delta=0.22),
        _row("C", 110.0, 4.30, delta=0.18),
        _row("P", 100.0, 3.00, delta=-0.24),
        _row("P", 95.0, 2.00, delta=-0.10),
        _row("P", 99.0, 2.40, delta=-0.12),
        _row("C", 103.0, 2.40, delta=0.18),
        _row("P", 97.0, 2.40, delta=-0.18),
        _row("C", 110.0, 1.40, delta=0.08),
        _row("P", 90.0, 1.40, delta=-0.08),
    ]

    cands = sfb.build_candidates(rows)

    long_c, short_c = cands["debit"]
    assert long_c is not None and short_c is not None
    assert (float(long_c["mark"]) - float(short_c["mark"])) * 100 > 75.0

    trade = sfb.build_trade("debit", [long_c, short_c], 100.0, {"ivCurrent": 0.2, "volLabel": "Neutral", "classifier": {}}, {"regime": {"riskState": "Neutral"}, "realizedVol": {"rv10": 0.2, "rv20": 0.2}})
    assert trade["maxLossPerContract"] > 75.0


def test_attach_mc_decision_uses_mc_engine_as_decision_source(monkeypatch):
    candidate = {
        "type": "debit",
        "decision": "PASS",
        "gateFailures": [],
        "ticket": {"positionSizeContracts": 1},
        "score": {"Regime": 10, "Vol": 16, "Structure": 20, "Event": 15, "Execution": 18, "AdjustedTotal": 72, "Total": 72},
    }
    legs = [_row("C", 500.0, 5.0, delta=0.4), _row("C", 505.0, 4.2, delta=0.2)]

    class FakeResult:
        allow_trade = True
        data_quality_status = "OK"
        payload = {
            "status": "FULL_REFRESH",
            "metrics": {"ev": 0.8},
            "multi_seed_confidence": {"ev_mean": 0.7},
            "gates": {"allow_trade": True, "ev_gate": True},
            "edge_attribution": {"explainable": True},
            "breakevens": [500.8],
            "assumptions": {"strategy": "call_debit_spread"},
        }

    class FakeEngine:
        def run(self, config):
            assert config.strategy_type == "call_debit_spread"
            assert config.strategy_legs[0]["side"] == "long"
            assert config.strategy_legs[1]["side"] == "short"
            return FakeResult()

    monkeypatch.setattr(sfb, "MCEngine", lambda: FakeEngine())
    monkeypatch.setattr(sfb, "_load_dxlink_candles", lambda: [100, 101, 102, 101, 103, 104, 103, 105, 104, 106, 107])
    out = sfb.attach_mc_decision(candidate, legs, 500.0)
    assert out["decisionSource"] == "mc_engine"
    assert out["decision"] == "TRADE"
    assert out["mc"]["allowTrade"] is True
    assert out["mc"]["strategy"] == "call_debit_spread"
    assert out["gateFailures"] == []


def test_no_candidates_message_exact_and_diagnostics_present(monkeypatch, capsys):
    rows = [
        _row("C", 100.0, 5.00, delta=0.40),
        _row("C", 110.0, 4.30, delta=0.18),
        _row("P", 100.0, 3.00, delta=-0.24),
        _row("P", 99.0, 2.40, delta=-0.12),
    ]

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    monkeypatch.setattr(sfb, "load_live", lambda _p: {"underlying": {"mark": 500.0}, "finishedAt": now})
    monkeypatch.setattr(sfb, "load_chain", lambda _p: {})
    monkeypatch.setattr(sfb, "live_is_fresh", lambda _live: True)
    monkeypatch.setattr(sfb, "get_spot_from_dx", lambda _p: None)
    monkeypatch.setattr(sfb, "watchlist_from_live", lambda _l: rows)
    monkeypatch.setattr(
        sfb,
        "regime_snapshot",
        lambda _spot: {
            "timeUserTz": "test-time",
            "regime": {"riskState": "Neutral"},
            "realizedVol": {"rv10": 0.2, "rv20": 0.2},
        },
    )
    monkeypatch.setattr(sfb, "vol_state", lambda _rows, _rv10, _rv20: {"ivCurrent": 0.2, "volLabel": "Neutral", "classifier": {}})

    class FakeResult:
        allow_trade = False
        data_quality_status = "OK"
        payload = {
            "status": "FULL_REFRESH",
            "metrics": {"ev": -1.0},
            "multi_seed_confidence": {"ev_mean": -1.0},
            "gates": {"allow_trade": False, "ev_gate": False},
            "edge_attribution": {},
            "breakevens": [100.5],
            "assumptions": {"strategy": "call_debit_spread"},
        }

    class FakeEngine:
        def run(self, config):
            return FakeResult()

    monkeypatch.setattr(sfb, "MCEngine", lambda: FakeEngine())

    sfb.main()
    payload = json.loads(capsys.readouterr().out)
    tb = payload["TRADE BRIEF"]

    assert tb["NoCandidatesReason"] is None
    assert len(tb["Candidates"]) == 2


def test_attach_mc_decision_does_not_upgrade_blocked_candidate_to_trade(monkeypatch):
    candidate = {
        'type': 'debit',
        'expectedMove': {'ivUsed': 0.25},
        'ticket': {'positionSizeContracts': 0},
        'score': {'Regime': 10, 'Vol': 16, 'Structure': 20, 'Event': 15, 'Execution': 18, 'AdjustedTotal': 50, 'Total': 50},
        'gateFailures': ['score_below_70', 'directional_mismatch'],
        'decision': 'PASS',
    }
    legs = [
        {'side': 'C', 'strike': 645.0, 'dte': 18, 'iv': 0.25},
        {'side': 'C', 'strike': 655.0, 'dte': 18, 'iv': 0.24},
    ]

    monkeypatch.setattr(sfb, 'load_live', lambda _p: {})
    monkeypatch.setattr(sfb, 'watchlist_from_live', lambda _live: [])
    monkeypatch.setattr(sfb, '_load_dxlink_candles', lambda: [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0])
    monkeypatch.setattr(sfb, 'ann_realized_vol', lambda _closes, _window: 0.2)
    monkeypatch.setattr(sfb, 'validate_mc_inputs', lambda *args, **kwargs: {'valid': True, 'warnings': []})
    monkeypatch.setattr(sfb, '_strategy_legs_for_candidate', lambda *_args, **_kwargs: [])

    class FakeResult:
        allow_trade = True
        data_quality_status = 'OK'
        payload = {
            'status': 'FULL_REFRESH',
            'metrics': {'pop': 0.55, 'pot': 0.4},
            'multi_seed_confidence': {},
            'gates': {'allow_trade': True},
            'edge_attribution': {},
            'breakevens': [650.0],
            'assumptions': {'strategy': 'call_debit_spread'},
        }

    class FakeEngine:
        def run(self, _config):
            return FakeResult()

    monkeypatch.setattr(sfb, 'MCEngine', lambda: FakeEngine())

    out = sfb.attach_mc_decision(candidate, legs, 635.0)
    assert out['decision'] == 'PASS'
    assert 'position_size_zero' in out['hardPassReasons']
    assert 'score_below_trade_threshold' in out['hardPassReasons']
    assert 'directional_mismatch_blocks_trade' in out['hardPassReasons']
