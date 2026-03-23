import ak_system.mc_options.engine as engine_module
from ak_system.mc_options.engine import MCEngine, MCEngineConfig


def test_engine_uses_actual_entry_value_for_breakevens(tmp_path, monkeypatch):
    captured = {}

    def fake_compute_breakevens(strategy, entry_value):
        captured['entry_value'] = entry_value
        return [600.0], None, {'grid_points': 1, 'sign_flips': 1}

    monkeypatch.setattr(engine_module, 'compute_breakevens', fake_compute_breakevens)
    monkeypatch.setattr(engine_module, 'strategy_mid_value', lambda *args, **kwargs: -2.5)

    result = MCEngine().run(
        MCEngineConfig(
            spot=600,
            strategy_type='iron_fly',
            n_batches=1,
            paths_per_batch=50,
            expiry_days=1,
            dt_days=1,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )

    assert captured['entry_value'] == -2.5
    assert result.breakevens == [600.0]


def test_engine_payload_breakevens_do_not_require_metrics_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, 'strategy_mid_value', lambda *args, **kwargs: -1.75)
    monkeypatch.setattr(engine_module, 'compute_breakevens', lambda strategy, entry_value: ([599.0, 601.0], None, {'grid_points': 2, 'sign_flips': 2}))

    result = MCEngine().run(
        MCEngineConfig(
            spot=600,
            strategy_type='iron_fly',
            n_batches=1,
            paths_per_batch=50,
            expiry_days=1,
            dt_days=1,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )

    assert result.payload['breakevens'] == [599.0, 601.0]


def test_engine_entry_value_path_runs_with_default_surface(tmp_path):
    result = MCEngine().run(
        MCEngineConfig(
            spot=600,
            strategy_type='iron_fly',
            n_batches=1,
            paths_per_batch=50,
            expiry_days=1,
            dt_days=1,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )
    assert isinstance(result.breakevens, list) or result.breakevens is None
