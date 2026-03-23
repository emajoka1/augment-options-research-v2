from ak_system.mc_options.strategy import default_exit_rules_for_strategy


def test_short_premium_defaults_tighten_for_5_dte():
    rules = default_exit_rules_for_strategy('iron_fly', expiry_days=5)
    assert rules.gamma_risk_dte_days == 1.0
    assert rules.dte_stop_days == 1.0


def test_short_premium_defaults_support_longer_dte_management():
    rules = default_exit_rules_for_strategy('iron_condor', expiry_days=45)
    assert rules.gamma_risk_dte_days == 10.0
    assert rules.dte_stop_days == 7.0


def test_debit_strategy_defaults_remain_unchanged():
    rules = default_exit_rules_for_strategy('long_straddle', expiry_days=5)
    assert rules.take_profit_pct == 0.70
    assert rules.stop_loss_pct == 0.50
    assert rules.gamma_risk_dte_days == 0.10


def test_calendar_defaults_remain_roll_like_but_not_short_premium_gamma():
    rules = default_exit_rules_for_strategy('put_calendar', expiry_days=30)
    assert rules.dte_stop_days == 1.0
    assert rules.gamma_risk_dte_days == 0.50
