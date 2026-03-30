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


def test_compute_execution_quality_for_tight_condor_legs():
    legs = [
        {'symbol': 'P1', 'bid': 1.14, 'ask': 1.16, 'openInterest': 5000, 'dayVolume': 1500},
        {'symbol': 'P2', 'bid': 0.54, 'ask': 0.56, 'openInterest': 5000, 'dayVolume': 1500},
        {'symbol': 'C1', 'bid': 1.14, 'ask': 1.16, 'openInterest': 5000, 'dayVolume': 1500},
        {'symbol': 'C2', 'bid': 0.54, 'ask': 0.56, 'openInterest': 5000, 'dayVolume': 1500},
    ]
    quality = sfb.compute_execution_quality(legs, ['sell', 'buy', 'sell', 'buy'])
    assert quality['all_legs_liquid'] is True
    assert quality['worst_leg_spread_pct'] < 5.0
    assert quality['avg_leg_spread_pct'] < 5.0
    assert quality['multi_spread_pct'] < 10.0


def test_build_trade_condor_not_rejected_by_tight_spreads_alone():
    legs = [
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 625.0, 'side': 'P', 'symbol': 'P1', 'bid': 1.14, 'ask': 1.16, 'mark': 1.15, 'delta': -0.18, 'iv': 0.30, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 620.0, 'side': 'P', 'symbol': 'P2', 'bid': 0.54, 'ask': 0.56, 'mark': 0.55, 'delta': -0.10, 'iv': 0.31, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 645.0, 'side': 'C', 'symbol': 'C1', 'bid': 1.14, 'ask': 1.16, 'mark': 1.15, 'delta': 0.18, 'iv': 0.29, 'openInterest': 5000, 'dayVolume': 1500},
        {'expiry': '2026-03-31', 'dte': 1, 'strike': 650.0, 'side': 'C', 'symbol': 'C2', 'bid': 0.54, 'ask': 0.56, 'mark': 0.55, 'delta': 0.10, 'iv': 0.30, 'openInterest': 5000, 'dayVolume': 1500},
    ]
    trade = sfb.build_trade('condor', legs, 636.0, {'ivCurrent': 0.30, 'volLabel': 'Neutral', 'classifier': {}}, {'regime': {'riskState': 'Neutral'}, 'realizedVol': {'rv10': 0.2, 'rv20': 0.2}})
    assert 'spread_bps_exceeded' not in (trade.get('gateFailures') or [])
    execution = ((trade.get('structure') or {}).get('pricing') or {}).get('execution') or {}
    assert execution.get('multi_spread_pct') is not None
    assert execution.get('multi_spread_pct') < 10.0


def test_regime_data_quality_one_of_three_caps_score_to_one_third():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'US10Y day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
            ],
        }
    }
    score = sfb.score_components({'type': 'condor', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] <= 8
    assert score['machineFactors']['regimeDataQualityFactor'] <= 0.33


def test_regime_data_quality_all_null_gives_zero_score():
    context = {
        'regime': {
            'riskState': 'Neutral',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'VIX day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'US10Y day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
            ],
        }
    }
    score = sfb.score_components({'type': 'condor', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] == 0


def test_regime_data_quality_all_fresh_preserves_raw_score():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'trend': 'up',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': -0.5, 'interpretation': 'risk-on', 'observedAt': now},
                {'metric': 'US10Y day change', 'value': 0.1, 'interpretation': 'context', 'observedAt': now},
            ],
        }
    }
    score = sfb.score_components({'type': 'condor', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] == 8
    assert score['machineFactors']['regimeDataQualityFactor'] == 1.0


def test_regime_score_recalibration_condor_neutral_down_flat_one_third_quality():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'trend': 'down_or_flat',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'not-uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'US10Y day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
            ],
        }
    }
    score = sfb.score_components({'type': 'condor', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] == 3


def test_regime_score_recalibration_credit_neutral_down_flat_one_third_quality():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'trend': 'down_or_flat',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'not-uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'US10Y day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
            ],
        }
    }
    score = sfb.score_components({'type': 'credit', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] == 1


def test_regime_score_recalibration_debit_neutral_down_flat_one_third_quality():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'trend': 'down_or_flat',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'not-uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
                {'metric': 'US10Y day change', 'value': None, 'interpretation': 'unknown', 'observedAt': None},
            ],
        }
    }
    score = sfb.score_components({'type': 'debit', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'classifier': {}}, True, True)
    assert score['Regime'] == 1


def test_vol_edge_score_condor_elevated_iv_is_good():
    score = sfb.compute_vol_edge_score(0.29, 0.15, 0.14, 'condor', max_score=20)
    assert score == 16


def test_vol_edge_score_debit_elevated_iv_is_poor():
    score = sfb.compute_vol_edge_score(0.29, 0.15, 0.14, 'debit', max_score=20)
    assert score == 2


def test_classify_vol_regime_recalibrated_elevated_vol():
    out = sfb.classify_vol_regime(0.29, 0.15, 0.14, None, None)
    assert out['regime'] == 'ELEVATED_VOL'
    assert 1.8 <= out['ivRvRatio'] <= 2.0


def test_compute_final_score_caps_three_plus_critical_failures_at_30():
    scores = {'Regime': 10, 'Vol': 16, 'Structure': 20, 'Event': 15, 'Execution': 18}
    out = sfb.compute_final_score(scores, ['expected_move_mismatch', 'mc:ev_gate', 'mc:cvar_worst_gate'])
    assert out['rawTotal'] == 79
    assert out['adjustedTotal'] == 30
    assert out['gatePenalty'] == 49


def test_compute_final_score_caps_two_critical_failures_at_45():
    scores = {'Regime': 10, 'Vol': 16, 'Structure': 20, 'Event': 15, 'Execution': 10}
    out = sfb.compute_final_score(scores, ['expected_move_mismatch', 'mc:ev_gate'])
    assert out['rawTotal'] == 71
    assert out['adjustedTotal'] == 45


def test_compute_final_score_caps_warning_only_at_75():
    scores = {'Regime': 10, 'Vol': 16, 'Structure': 20, 'Event': 15, 'Execution': 18}
    out = sfb.compute_final_score(scores, ['score_below_70'])
    assert out['rawTotal'] == 79
    assert out['adjustedTotal'] == 75


def test_compute_final_score_treats_directional_mismatch_as_critical():
    scores = {'Regime': 10, 'Vol': 16, 'Structure': 20, 'Event': 15, 'Execution': 18}
    out = sfb.compute_final_score(scores, ['directional_mismatch'])
    assert out['rawTotal'] == 79
    assert out['adjustedTotal'] == 60


def test_set_trade_target_condor_one_dte_uses_80pct_profit_target():
    target, pct = sfb.set_trade_target('condor', 1.18, None, 1.18, 1)
    assert target == 0.24
    assert pct == 0.80


def test_set_trade_target_debit_short_dte_is_less_aggressive():
    target, pct = sfb.set_trade_target('debit', None, 5.0, None, 1)
    assert target == 6.5
    assert pct == 1.30


def test_validate_pot_flags_unrealistic_short_premium_target():
    out = sfb.validate_pot(0.752, 0.0, 'condor')
    assert out is not None
    assert out['flag'] == 'target_unrealistic'


def test_validate_mc_inputs_blocks_invalid_unit_errors():
    legs = [
        {'symbol': 'L1', 'iv': 6.89, 'delta': 0.2, 'bid': 1.0, 'ask': 1.1},
    ]
    out = sfb.validate_mc_inputs(636.0, 6.89, 0.15, 37, legs, 'condor')
    assert out['valid'] is False
    assert any('IV is 6.89' in e for e in out['errors'])


def test_validate_mc_inputs_warns_on_zero_dte_but_can_proceed():
    legs = [
        {'symbol': 'L1', 'iv': 0.30, 'delta': 0.2, 'bid': 1.0, 'ask': 1.1},
    ]
    out = sfb.validate_mc_inputs(636.0, 0.30, 0.15, 0, legs, 'condor')
    assert out['valid'] is True
    assert any('DTE is 0' in w for w in out['warnings'])


def test_directional_alignment_flags_bullish_strategy_in_down_flat_trend():
    out = sfb.check_directional_alignment('credit_put', 'down_or_flat')
    assert out['aligned'] is False
    assert out['score_multiplier'] == 0.2
    assert out['gate'] == 'directional_mismatch'


def test_directional_alignment_allows_neutral_condor_in_down_flat_with_penalty_only():
    out = sfb.check_directional_alignment('condor', 'down_or_flat')
    assert out['aligned'] is True
    assert out['score_multiplier'] == 0.6
    assert out['gate'] is None


def test_regime_score_applies_directional_alignment_multiplier():
    now = datetime.now(timezone.utc).isoformat()
    context = {
        'regime': {
            'riskState': 'Neutral',
            'trend': 'down_or_flat',
            'metrics': [
                {'metric': 'MA5-MA20', 'value': 1.0, 'interpretation': 'not-uptrend', 'observedAt': now},
                {'metric': 'VIX day change', 'value': -0.5, 'interpretation': 'risk-on', 'observedAt': now},
                {'metric': 'US10Y day change', 'value': 0.1, 'interpretation': 'context', 'observedAt': now},
            ],
        },
        'realizedVol': {'rv10': 0.15, 'rv20': 0.14},
    }
    score = sfb.score_components({'type': 'credit', 'maxLoss': 1, 'breakevens': [1, 2]}, context, {'ivCurrent': 0.29, 'classifier': {'ivRvRatio': 1.9, 'regime': 'ELEVATED_VOL'}}, True, True)
    assert score['Regime'] == 2
    assert score['machineFactors']['directionalAlignment']['gate'] == 'directional_mismatch'


def test_compute_invalidation_debit_call_is_near_spot_and_long_strike():
    legs = [
        {'side': 'C', 'action': 'buy', 'strike': 640.0},
        {'side': 'C', 'action': 'sell', 'strike': 645.0},
    ]
    text, level = sfb.compute_invalidation('debit_call', legs, 636.2, 1)
    assert 'fails to trade above 640.0' in text
    assert level == round(636.2 * 0.98, 2)


def test_validate_invalidation_level_rejects_absurd_distance():
    out = sfb.validate_invalidation_level(360.88, 636.2)
    assert out['valid'] is False
    assert 'unrealistic' in out['warning']


def test_build_counterfactuals_debit_is_strategy_specific():
    legs = [
        {'side': 'C', 'strike': 650.0, 'dte': 18},
        {'side': 'C', 'strike': 665.0, 'dte': 18},
    ]
    ticket = {'maxLoss': 558.0, 'entryRange': [5.47, 5.75], 'target': 11.16, 'invalidation': 'SPY fails to trade above 650.0 or drops below 624.66'}
    expected = {'value': 35.59, 'breakevens': [655.52], 'ivUsed': 0.2516}
    context = {'realizedVol': {'rv10': 0.15, 'rv20': 0.14}}
    out = sfb.build_counterfactuals('debit', legs, ticket, expected, 636.2, context, greeks={'thetaPerDay': -17.24})
    assert 'fails to move above 650.0 by expiry' in out['loseQuicklyIf']
    assert '~$-17.24/day' in out['loseQuicklyIf']
    assert 'IV contraction (vol crush)' in out['volBreak']
    assert 'Max loss of $558.0 occurs if SPY is at or below 650.0 at expiry.' in out['priceInvalidation']


def test_build_counterfactuals_credit_is_strategy_specific():
    legs = [
        {'side': 'P', 'strike': 610.0, 'dte': 18},
        {'side': 'P', 'strike': 595.0, 'dte': 18},
    ]
    ticket = {'maxLoss': 1271.0, 'entryRange': [2.22, 2.36], 'target': 1.37, 'invalidation': 'SPY < 610.0'}
    expected = {'value': 41.76, 'breakevens': [607.71], 'ivUsed': 0.2952}
    context = {'realizedVol': {'rv10': 0.15, 'rv20': 0.14}}
    out = sfb.build_counterfactuals('credit', legs, ticket, expected, 637.13, context)
    assert 'SPY drops below 610.0 with momentum.' in out['loseQuicklyIf']
    assert 'move to 39.5%' in out['volBreak']
    assert 'Full max loss of $1271.0 below 595.0.' in out['priceInvalidation']


def test_compute_position_greeks_surfaces_dominant_risk_and_gamma_class():
    legs = [
        {'action': 'buy', 'delta': 0.40, 'gamma': 0.02, 'theta': -0.05, 'vega': 0.12},
        {'action': 'sell', 'delta': 0.20, 'gamma': 0.01, 'theta': -0.03, 'vega': 0.08},
    ]
    out = sfb.compute_position_greeks(legs, 636.0, 1, entry_cost=5.5)
    assert out['netDelta'] == 20.0
    assert out['dominantRiskFactor'] == 'GAMMA'
    assert out['gammaRisk'] in {'LOW', 'MODERATE', 'HIGH', 'EXTREME'}
    assert 'vegaDollarImpact' in out


def test_enrich_leg_greeks_backfills_missing_values_from_bsm():
    leg = {'side': 'C', 'strike': 650.0, 'iv': 0.25, 'delta': 0.4, 'gamma': None, 'theta': None, 'vega': None}
    out = sfb.enrich_leg_greeks(leg, 636.0, 18)
    assert out['gamma'] is not None
    assert out['theta'] is not None
    assert out['vega'] is not None


def test_evaluate_portfolio_context_computes_delta_and_risk_shift():
    new_trade = {'underlying': 'SPY', 'net_delta': 20.0, 'notional': 12000.0, 'max_loss': 500.0}
    existing = [
        {'underlying': 'SPY', 'net_delta': -10.0, 'notional': 10000.0, 'max_loss': 400.0},
        {'underlying': 'QQQ', 'net_delta': 5.0, 'notional': 8000.0, 'max_loss': 300.0},
    ]
    out = sfb.evaluate_portfolio_context(new_trade, existing, 100000.0)
    assert out['currentDelta'] == -5.0
    assert out['newDelta'] == 15.0
    assert out['deltaShift'] == 20.0
    assert out['correlatedRisk'] == 700.0


def test_compute_liquidity_score_rates_liquid_spy_options_highly():
    legs = [
        {'symbol': 'A', 'openInterest': 12000, 'dayVolume': 6000, 'bid': 1.14, 'ask': 1.16},
        {'symbol': 'B', 'openInterest': 8000, 'dayVolume': 2500, 'bid': 0.54, 'ask': 0.56},
    ]
    out = sfb.compute_liquidity_score(legs)
    assert out['worstLeg'] >= 65
    assert out['gate'] == 'PASS'


def test_compute_liquidity_score_rejects_truly_illiquid_option():
    legs = [
        {'symbol': 'X', 'openInterest': 10, 'dayVolume': 0, 'bid': 0.0, 'ask': 0.5},
    ]
    out = sfb.compute_liquidity_score(legs)
    assert out['worstLeg'] < 30
    assert out['gate'] == 'FAIL'


def test_portfolio_context_fallback_warning_when_unavailable():
    data = sfb.load_portfolio_context('/tmp/definitely_missing_portfolio_context.json')
    assert data is None


def test_build_recommendation_prefers_data_error_when_inputs_incomplete():
    context = {'dataQuality': {'regime': {'availableInputs': 1, 'totalInputs': 3}}}
    analyses = [{'decision': 'PASS', 'gateFailures': ['mc:ev_gate']}]
    out = sfb.build_recommendation(analyses, context, ['realized_vol'], None)
    assert out['signal'] == 'DATA_ERROR'
    assert out['color'] == 'gray'


def test_build_recommendation_no_trade_when_all_candidates_rejected_without_data_error():
    context = {'dataQuality': {'regime': {'availableInputs': 3, 'totalInputs': 3}}}
    analyses = [{'decision': 'PASS', 'gateFailures': ['mc:ev_gate']}]
    out = sfb.build_recommendation(analyses, context, [], None)
    assert out['signal'] == 'NO_TRADE'
    assert out['color'] == 'red'


def test_build_data_quality_dashboard_marks_missing_inputs_degraded():
    context = {
        'regime': {
            'metrics': [
                {'metric': 'VIX day change', 'value': None},
                {'metric': 'US10Y day change', 'value': None},
            ]
        },
        'realizedVol': {'rv10': None},
    }
    vol = {'ivCurrent': 0.29}
    dte_summary = {'nearestDte': 1}
    out = sfb.build_data_quality_dashboard(636.2, context, vol, dte_summary, ['realized_vol'])
    assert out['overall'] == 'DEGRADED'
    assert any(c['input'] == 'rv10' and c['status'] in {'MISSING', 'SUSPECT'} for c in out['checks'])


def test_build_override_policy_blocks_on_error():
    dq = {'overall': 'ERROR'}
    analyses = [{'gateFailures': ['a', 'b', 'c', 'd']}]
    out = sfb.build_override_policy(dq, analyses)
    assert out['allowed'] is False
    assert out['requiresAcknowledgment']


def test_build_override_policy_requires_ack_on_degraded():
    dq = {'overall': 'DEGRADED'}
    analyses = [{'gateFailures': ['a', 'b', 'c', 'd']}]
    out = sfb.build_override_policy(dq, analyses)
    assert out['allowed'] is True
    assert len(out['requiresAcknowledgment']) >= 2


def test_load_dxlink_candles_collapses_intraday_to_daily_closes(tmp_path, monkeypatch):
    candle_path = tmp_path / 'dxlink_live_candles.json'
    daily_path = tmp_path / 'missing_daily.json'
    base = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    candles = []
    for day_index in range(3):
        day = base + timedelta(days=day_index)
        candles.append({'time': int(day.replace(hour=15, minute=0).timestamp() * 1000), 'close': 100 + day_index})
        candles.append({'time': int(day.replace(hour=20, minute=0).timestamp() * 1000), 'close': 101 + day_index})
    candles.append({'time': 2147483648023, 'close': 'NaN'})
    candle_path.write_text(json.dumps({'candles': candles}))
    monkeypatch.setattr(sfb, 'DXLINK_DAILY_CLOSES_OUT', str(daily_path))
    monkeypatch.setattr(sfb, 'DXLINK_DAILY_BACKFILL_SCRIPT', str(tmp_path / 'missing_backfill.py'))
    monkeypatch.setattr(sfb, 'DXLINK_CANDLE_OUT', str(candle_path))
    closes = sfb._load_dxlink_candles()
    assert closes == [101.0, 102.0, 103.0]


def test_load_dxlink_candles_prefers_daily_close_file(tmp_path, monkeypatch):
    daily_path = tmp_path / 'dxlink_daily_closes.json'
    candle_path = tmp_path / 'dxlink_live_candles.json'
    daily_path.write_text(json.dumps({'closes': [
        {'date': '2026-03-10', 'close': 101.0},
        {'date': '2026-03-11', 'close': 102.0},
        {'date': '2026-03-12', 'close': 103.0},
    ]}))
    candle_path.write_text(json.dumps({'candles': [
        {'time': 1770000000000, 'close': 999.0},
    ]}))
    monkeypatch.setattr(sfb, 'DXLINK_DAILY_CLOSES_OUT', str(daily_path))
    monkeypatch.setattr(sfb, 'DXLINK_CANDLE_OUT', str(candle_path))
    closes = sfb._load_dxlink_candles()
    assert closes == [101.0, 102.0, 103.0]


def test_backfill_daily_close_script_collapses_longer_history(tmp_path):
    import scripts.backfill_daily_closes as bdc

    payload = {
        'candles': [
            {'time': int(datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc).timestamp() * 1000), 'close': 101.0},
            {'time': int(datetime(2026, 3, 11, 20, 0, tzinfo=timezone.utc).timestamp() * 1000), 'close': 102.0},
            {'time': int(datetime(2026, 3, 12, 20, 0, tzinfo=timezone.utc).timestamp() * 1000), 'close': 103.0},
        ]
    }
    closes = bdc.collapse_to_daily(payload)
    assert [row['close'] for row in closes] == [101.0, 102.0, 103.0]


def test_ann_realized_vol_matches_annualized_log_return_formula():
    closes = [100, 101, 99, 102, 101, 103, 102, 104, 103, 105, 104]
    rv10 = sfb.ann_realized_vol(closes, 10)
    assert rv10 is not None
    assert 0.01 <= rv10 <= 2.00
