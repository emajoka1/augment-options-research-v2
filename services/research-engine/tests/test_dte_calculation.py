from datetime import datetime, timezone, timedelta
import json

import scripts.spy_free_brief as sfb


def test_compute_dte_tomorrow_morning_et():
    now = datetime.fromisoformat('2026-03-30T10:00:00-04:00')
    assert sfb.compute_dte('2026-03-31', now) == 1


def test_compute_dte_tomorrow_afternoon_et():
    now = datetime.fromisoformat('2026-03-30T15:00:00-04:00')
    assert sfb.compute_dte('2026-03-31', now) == 1


def test_compute_dte_same_day_before_close_et():
    now = datetime.fromisoformat('2026-03-31T10:00:00-04:00')
    assert sfb.compute_dte('2026-03-31', now) == 0


def test_compute_dte_same_day_after_close_et():
    now = datetime.fromisoformat('2026-03-31T17:00:00-04:00')
    assert sfb.compute_dte('2026-03-31', now) == 0


def test_compute_dte_eighteen_days_et():
    now = datetime.fromisoformat('2026-03-30T10:00:00-04:00')
    assert sfb.compute_dte('2026-04-17', now) == 18


def test_compute_dte_seventy_seven_days_et():
    now = datetime.fromisoformat('2026-01-02T09:30:00-05:00')
    assert sfb.compute_dte('2026-03-20', now) == 77


def test_watchlist_from_live_recomputes_dte_and_ignores_stale_input():
    now = datetime.fromisoformat('2026-03-30T10:00:00-04:00')
    live = {
        'contracts': [
            {'expiry': '2026-03-31', 'dte': 37, 'strike': 625.0, 'side': 'P', 'symbol': 'SYM1'},
        ],
        'data': {
            'SYM1': {'bid': 1.0, 'ask': 1.1, 'mark': 1.05, 'delta': -0.2, 'iv': 0.25, 'openInterest': 5000, 'dayVolume': 1500}
        },
    }
    rows = sfb.watchlist_from_live(live) if False else None
    original = sfb.current_market_now
    try:
        sfb.current_market_now = lambda: now
        rows = sfb.watchlist_from_live(live)
    finally:
        sfb.current_market_now = original
    assert rows[0]['dte'] == 1
    assert rows[0]['expiry'] == '2026-03-31'


def test_canonical_dte_summary_reports_nearest_and_by_expiry():
    rows = [
        {'expiry': '2026-03-31', 'dte': 1},
        {'expiry': '2026-03-31', 'dte': 1},
        {'expiry': '2026-04-17', 'dte': 18},
    ]
    summary = sfb.canonical_dte_summary(rows)
    assert summary['nearestExpiry'] == '2026-03-31'
    assert summary['nearestDte'] == 1
    assert summary['byExpiry']['2026-03-31'] == 1
    assert summary['byExpiry']['2026-04-17'] == 18


def test_candidate_structure_dte_matches_leg_dte_and_expiry_math():
    now = datetime.fromisoformat('2026-03-30T10:00:00-04:00')
    rows = [
        {
            'expiry': '2026-03-31', 'dte': 1, 'strike': 625.0, 'side': 'P', 'symbol': 'P1',
            'bid': 1.0, 'ask': 1.1, 'mark': 1.05, 'delta': -0.2, 'iv': 0.25, 'openInterest': 5000, 'dayVolume': 1500,
            'liquid': True,
        },
        {
            'expiry': '2026-03-31', 'dte': 1, 'strike': 620.0, 'side': 'P', 'symbol': 'P2',
            'bid': 0.5, 'ask': 0.6, 'mark': 0.55, 'delta': -0.1, 'iv': 0.24, 'openInterest': 5000, 'dayVolume': 1500,
            'liquid': True,
        },
    ]
    trade = sfb.build_trade('credit', rows, 630.0, {'ivCurrent': 0.25, 'volLabel': 'Neutral', 'classifier': {}}, {'regime': {'riskState': 'Neutral'}, 'realizedVol': {'rv10': 0.2, 'rv20': 0.2}})
    assert trade['structure']['dte'] == 1
    assert all(leg['dte'] == 1 for leg in trade['structure']['legs'])
    assert sfb.compute_dte(trade['structure']['expiry'], now) == trade['structure']['dte']


def test_expected_move_uses_decimal_atm_iv_for_one_dte():
    em = sfb.expected_move(636.0, 0.30, 1)
    assert 8.0 <= em <= 12.0


def test_expected_move_uses_decimal_atm_iv_for_thirty_dte():
    em = sfb.expected_move(636.0, 0.30, 30)
    assert 50.0 <= em <= 60.0


def test_atm_iv_for_expected_move_interpolates_near_spot():
    rows = [
        {'strike': 635.0, 'iv': 0.29, 'dte': 1, 'side': 'P'},
        {'strike': 640.0, 'iv': 0.31, 'dte': 1, 'side': 'C'},
        {'strike': 620.0, 'iv': 0.40, 'dte': 30, 'side': 'P'},
    ]
    iv = sfb.atm_iv_for_expected_move(rows, 636.0, 1)
    assert 0.29 <= iv <= 0.31


def test_build_trade_expected_move_is_sane_for_credit_condor():
    legs = [
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 625.0, 'side': 'P', 'symbol': 'P1', 'bid': 1.10, 'ask': 1.20, 'mark': 1.15, 'delta': -0.18, 'iv': 0.30, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 620.0, 'side': 'P', 'symbol': 'P2', 'bid': 0.50, 'ask': 0.60, 'mark': 0.55, 'delta': -0.10, 'iv': 0.31, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 645.0, 'side': 'C', 'symbol': 'C1', 'bid': 1.10, 'ask': 1.20, 'mark': 1.15, 'delta': 0.18, 'iv': 0.29, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 650.0, 'side': 'C', 'symbol': 'C2', 'bid': 0.50, 'ask': 0.60, 'mark': 0.55, 'delta': 0.10, 'iv': 0.30, 'openInterest': 5000, 'dayVolume': 1500},
    ]
    trade = sfb.build_trade('condor', legs, 636.0, {'ivCurrent': 6.89, 'volLabel': 'Neutral', 'classifier': {}}, {'regime': {'riskState': 'Neutral'}, 'realizedVol': {'rv10': 0.2, 'rv20': 0.2}})
    em = trade['expectedMove']['value']
    assert 8.0 <= em <= 12.0
    assert trade['expectedMove']['lower1SD'] > 0
    assert trade['expectedMove']['upper1SD'] > 636.0
    assert trade['expectedMove']['lower1SD'] < 636.0


def test_aggregate_iv_current_averages_nearest_atm_put_and_call():
    rows = [
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 635.0, 'side': 'P', 'iv': 0.30, 'dayVolume': 1000},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 640.0, 'side': 'C', 'iv': 0.28, 'dayVolume': 1200},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 620.0, 'side': 'P', 'iv': 0.45, 'dayVolume': 100},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 655.0, 'side': 'C', 'iv': 0.44, 'dayVolume': 100},
    ]
    iv_current = sfb.aggregate_iv_current(rows, 636.0)
    assert 0.28 <= iv_current <= 0.30
    assert abs(iv_current - 0.29) < 0.02


def test_normalize_iv_decimal_auto_converts_percent_form():
    assert abs(sfb.normalize_iv_decimal(30.0) - 0.30) < 1e-9
    assert abs(sfb.normalize_iv_decimal(0.30) - 0.30) < 1e-9


def test_vol_state_ivcurrent_within_leg_band():
    rows = [
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 635.0, 'side': 'P', 'iv': 0.30, 'dayVolume': 1000},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 640.0, 'side': 'C', 'iv': 0.28, 'dayVolume': 1200},
        {'expiry': '2026-04-17', 'dte': 18, 'strike': 610.0, 'side': 'P', 'iv': 0.31, 'dayVolume': 800},
        {'expiry': '2026-04-17', 'dte': 18, 'strike': 660.0, 'side': 'C', 'iv': 0.29, 'dayVolume': 900},
    ]
    vol = sfb.vol_state(rows, rv10=0.20, rv20=0.18, spot=636.0)
    assert 0.05 <= vol['ivCurrent'] <= 1.50
    assert 0.23 <= vol['ivCurrent'] <= 0.35
    assert 0.5 <= vol['classifier']['ivRvRatio'] <= 10.0


def test_load_dxlink_candles_collapses_intraday_to_daily_closes(tmp_path, monkeypatch):
    candle_path = tmp_path / 'dxlink_live_candles.json'
    base = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    candles = []
    for day_index in range(3):
        day = base + timedelta(days=day_index)
        candles.append({'time': int(day.replace(hour=15, minute=0).timestamp() * 1000), 'close': 100 + day_index})
        candles.append({'time': int(day.replace(hour=20, minute=0).timestamp() * 1000), 'close': 101 + day_index})
    candles.append({'time': 2147483648023, 'close': 'NaN'})
    candle_path.write_text(json.dumps({'candles': candles}))
    monkeypatch.setattr(sfb, 'DXLINK_CANDLE_OUT', str(candle_path))
    closes = sfb._load_dxlink_candles()
    assert closes == [101.0, 102.0, 103.0]


def test_ann_realized_vol_matches_annualized_log_return_formula():
    closes = [100, 101, 99, 102, 101, 103, 102, 104, 103, 105, 104]
    rv10 = sfb.ann_realized_vol(closes, 10)
    assert rv10 is not None
    assert 0.01 <= rv10 <= 2.00
