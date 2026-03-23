from ak_system.mc_options.strategy import ExitRules, should_exit


def test_credit_strategy_take_profit_triggers_on_fraction_of_credit():
    rules = ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0)
    assert should_exit(
        current_pnl=1.0,
        entry_debit_or_credit=-2.0,
        dte_days=10,
        iv_shift=0.0,
        rules=rules,
        is_short_premium=True,
    ) is True


def test_credit_strategy_stop_loss_triggers_on_multiple_of_credit():
    rules = ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0)
    assert should_exit(
        current_pnl=-2.0,
        entry_debit_or_credit=-2.0,
        dte_days=10,
        iv_shift=0.0,
        rules=rules,
        is_short_premium=True,
    ) is True


def test_debit_strategy_take_profit_still_triggers():
    rules = ExitRules(take_profit_pct=0.7, stop_loss_pct=0.5)
    assert should_exit(
        current_pnl=0.7,
        entry_debit_or_credit=1.0,
        dte_days=10,
        iv_shift=0.0,
        rules=rules,
        is_short_premium=False,
    ) is True


def test_zero_entry_value_skips_pnl_gates():
    rules = ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0)
    assert should_exit(
        current_pnl=100.0,
        entry_debit_or_credit=0.0,
        dte_days=10,
        iv_shift=0.0,
        rules=rules,
        is_short_premium=True,
    ) is False
