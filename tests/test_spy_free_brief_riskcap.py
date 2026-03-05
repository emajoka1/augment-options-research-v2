import json
from datetime import datetime, timezone

import scripts.spy_free_brief as sfb


NO_CAND_MSG = "NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."


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


def test_riskcap_first_generation_enforces_cap_pre_selection(monkeypatch):
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
    assert (float(long_c["mark"]) - float(short_c["mark"])) * 100 <= 75.0

    short_p, long_p = cands["credit"]
    assert short_p is not None and long_p is not None
    credit = float(short_p["mark"]) - float(long_p["mark"])
    width = abs(float(short_p["strike"]) - float(long_p["strike"]))
    assert (width - credit) * 100 <= 75.0

    sp, lp, sc, lc = cands["condor"]
    if all(x is not None for x in (sp, lp, sc, lc)):
        credit_ic = float(sp["mark"]) + float(sc["mark"]) - float(lp["mark"]) - float(lc["mark"])
        wing = min(abs(float(sp["strike"]) - float(lp["strike"])), abs(float(lc["strike"]) - float(sc["strike"])))
        assert (wing - credit_ic) * 100 <= 75.0


def test_no_candidates_message_exact_and_diagnostics_present(monkeypatch, capsys):
    monkeypatch.setattr(sfb, "MAX_RISK_DOLLARS", 1.0)

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
    monkeypatch.setattr(sfb, "get_spot_from_cboe_quote", lambda _s: (500.0, "test", now))
    monkeypatch.setattr(sfb, "get_spot_from_dx", lambda _p: None)
    monkeypatch.setattr(sfb, "get_spot_from_yahoo", lambda: (None, None, None))
    monkeypatch.setattr(sfb, "watchlist_from_live", lambda _l: rows)
    monkeypatch.setattr(
        sfb,
        "regime_snapshot",
        lambda _spot: {
            "timeUserTz": "test-time",
            "regime": "Neutral",
            "realizedVol": {"rv10": 0.2, "rv20": 0.2},
        },
    )
    monkeypatch.setattr(sfb, "vol_state", lambda _rows, _rv10, _rv20: {"ivCurrent": 0.2, "volLabel": "Neutral"})

    sfb.main()
    payload = json.loads(capsys.readouterr().out)
    tb = payload["TRADE BRIEF"]

    assert tb["NoCandidatesReason"] == NO_CAND_MSG
    assert len(tb["Candidates"]) == 3
    assert tb["ClosestNearMiss"]["flipHint"]
