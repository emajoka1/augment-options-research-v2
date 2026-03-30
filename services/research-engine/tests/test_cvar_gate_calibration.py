from types import SimpleNamespace

from ak_system.mc_options.gates import evaluate_survival_gates


class Metrics:
    def __init__(self, *, min_pl, cvar95, pot=0.5):
        self.min_pl = min_pl
        self.cvar95 = cvar95
        self.pot = pot


def _multi_seed():
    return {
        'ev_mid': 0.1,
        'ev_real': 0.08,
        'ev_stress': 0.02,
        'ev_5th_percentile': 0.03,
        'cvar_mean': -2.0,
        'cvar_worst': -2.5,
        'pop_mean': 0.7,
    }


def test_defined_risk_cvar_within_max_loss_passes():
    metrics = Metrics(min_pl=-3.82, cvar95=-2.76)
    config = SimpleNamespace(strategy_name='iron_condor', strategy_type='iron_condor')
    gates, _ = evaluate_survival_gates(metrics, _multi_seed(), 'mean_revert|vol_contracting', {}, config)
    assert gates['cvar_ratio'] < 1.0
    assert gates['cvar_gate'] is True
    assert gates['cvar_worst_gate'] is True
    assert gates['cvar_gate_status'] in {'PASS', 'WARN'}


def test_defined_risk_cvar_exceeding_max_loss_fails():
    metrics = Metrics(min_pl=-3.00, cvar95=-3.30)
    config = SimpleNamespace(strategy_name='put_credit_spread', strategy_type='put_credit_spread')
    gates, _ = evaluate_survival_gates(metrics, _multi_seed(), 'mean_revert|vol_contracting', {}, config)
    assert gates['cvar_ratio'] > 1.05
    assert gates['cvar_gate'] is False
    assert gates['cvar_worst_gate'] is False
    assert gates['cvar_gate_status'] == 'FAIL'
