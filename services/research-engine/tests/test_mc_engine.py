from ak_system.mc_options.engine import MCEngine, MCEngineConfig


def test_mc_engine_returns_complete_result(tmp_path):
    result = MCEngine().run(MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=False))
    assert 'assumptions' in result.payload
    assert isinstance(result.allow_trade, bool)
    assert isinstance(result.metrics.ev, float)


def test_mc_engine_supports_custom_strategy(tmp_path):
    result = MCEngine().run(MCEngineConfig(spot=600, strategy_type='iron_fly', n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=False))
    assert result.payload['assumptions']['strategy'] == 'iron_fly'
    assert result.payload['assumptions']['spot'] == 600


def test_mc_engine_skip_shape(tmp_path):
    engine = MCEngine()
    cfg = MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=True)
    first = engine.run(cfg)
    second = engine.run(cfg)
    assert second.payload['status'] in {'NO_NEW_INPUTS', 'FULL_REFRESH', 'NO_ACTION_DQ_FAIL_DUPLICATE'}
