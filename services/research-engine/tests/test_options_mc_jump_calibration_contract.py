import numpy as np

from ak_system.mc_options.iv_dynamics import IVDynamicsParams
from ak_system.mc_options.models import JumpDiffusionParams
from ak_system.mc_options.simulator import FrictionConfig, simulate_strategy_paths
from ak_system.mc_options.strategy import ExitRules, make_long_straddle


def test_simulator_uses_supplied_jump_params(monkeypatch):
    captured = {}

    def fake_simulate_jump_diffusion_paths(S0, n_paths, n_steps, dt, params, seed=42):
        captured['params'] = params
        return np.full((n_paths, n_steps + 1), S0, dtype=float)

    monkeypatch.setattr('ak_system.mc_options.simulator.simulate_jump_diffusion_paths', fake_simulate_jump_diffusion_paths)

    jump = JumpDiffusionParams(mu=0.01, sigma=0.22, jump_lambda=0.03, jump_mu=-0.02, jump_sigma=0.05)
    simulate_strategy_paths(
        strategy=make_long_straddle(K=100, expiry_years=5 / 365),
        S0=100,
        r=0.02,
        q=0.0,
        n_paths=4,
        n_steps=3,
        dt=(5 / 365) / 3,
        iv_params=IVDynamicsParams(iv_atm=0.25),
        exit_rules=ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25),
        friction=FrictionConfig(),
        model='jump',
        seed=7,
        jump_params=jump,
    )

    assert captured['params'].jump_lambda == 0.03
    assert captured['params'].jump_mu == -0.02
    assert captured['params'].jump_sigma == 0.05


def test_simulator_default_jump_params_are_not_hardcoded_tail_heavy(monkeypatch):
    captured = {}

    def fake_simulate_jump_diffusion_paths(S0, n_paths, n_steps, dt, params, seed=42):
        captured['params'] = params
        return np.full((n_paths, n_steps + 1), S0, dtype=float)

    monkeypatch.setattr('ak_system.mc_options.simulator.simulate_jump_diffusion_paths', fake_simulate_jump_diffusion_paths)

    simulate_strategy_paths(
        strategy=make_long_straddle(K=100, expiry_years=5 / 365),
        S0=100,
        r=0.02,
        q=0.0,
        n_paths=4,
        n_steps=3,
        dt=(5 / 365) / 3,
        iv_params=IVDynamicsParams(iv_atm=0.25),
        exit_rules=ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25),
        friction=FrictionConfig(),
        model='jump',
        seed=7,
    )

    assert captured['params'].jump_lambda != 0.35
    assert captured['params'].jump_mu != -0.05
    assert captured['params'].jump_sigma != 0.18


def test_engine_passes_calibrated_jump_params(monkeypatch, tmp_path):
    from ak_system.mc_options.engine import MCEngine, MCEngineConfig
    import ak_system.mc_options.engine as engine_module
    from ak_system.mc_options.calibration import CalibratedPack
    from ak_system.mc_options.models import GBMParams, HestonParams

    captured = {'jump_params': []}

    def fake_simulate_strategy_paths(**kwargs):
        captured['jump_params'].append(kwargs.get('jump_params'))
        return np.zeros(kwargs['n_paths']), np.zeros(kwargs['n_paths'])

    fake_jump = JumpDiffusionParams(mu=0.02, sigma=0.21, jump_lambda=0.04, jump_mu=-0.01, jump_sigma=0.06)

    def fake_calibrate(snapshot, dt=1 / 252):
        return CalibratedPack(
            gbm=GBMParams(),
            jump=fake_jump,
            heston=HestonParams(),
            iv=IVDynamicsParams(iv_atm=0.25),
            rv10=0.2,
            rv20=0.22,
        )

    snap = tmp_path / 'chain.json'
    snap.write_text('{"spot": 100.0, "chain": [{"strike": 100, "iv": 0.25, "expiry_days": 5}], "returns": [0.01, -0.02, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01]}')

    monkeypatch.setattr(engine_module, 'calibrate_from_snapshot', fake_calibrate)
    engine = MCEngine(deps={'simulate_strategy_paths': fake_simulate_strategy_paths})
    engine.run(MCEngineConfig(snapshot_file=str(snap), n_batches=1, paths_per_batch=5, output_root=str(tmp_path), write_artifacts=False))

    assert captured['jump_params']
    assert all(jump.jump_lambda == 0.04 for jump in captured['jump_params'])
