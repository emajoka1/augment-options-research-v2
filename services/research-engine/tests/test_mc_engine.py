from ak_system.mc_options.engine import MCEngine, MCEngineConfig
import ak_system.mc_options.engine as engine_module


def test_mc_engine_returns_complete_result(tmp_path):
    result = MCEngine().run(MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=False))
    assert 'assumptions' in result.payload
    assert isinstance(result.allow_trade, bool)
    assert isinstance(result.metrics.ev, float)


def test_mc_engine_supports_custom_strategy(tmp_path):
    result = MCEngine().run(MCEngineConfig(spot=600, strategy_type='iron_fly', n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=False))
    assert result.payload['assumptions']['strategy'] == 'iron_fly'
    assert result.payload['assumptions']['spot'] == 600


def test_mc_engine_accepts_explicit_strategy_legs(tmp_path):
    result = MCEngine().run(
        MCEngineConfig(
            spot=600,
            strategy_type='call_debit_spread',
            strategy_legs=[
                {'side': 'long', 'option_type': 'call', 'strike': 600.0, 'qty': 1},
                {'side': 'short', 'option_type': 'call', 'strike': 605.0, 'qty': 1},
            ],
            n_batches=1,
            paths_per_batch=100,
            expiry_days=5,
            dt_days=1,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )
    assert result.payload['assumptions']['strategy'] == 'call_debit_spread'
    assert [leg['strike'] for leg in result.payload['assumptions']['legs']] == [600.0, 605.0]
    assert [leg['side'] for leg in result.payload['assumptions']['legs']] == ['long', 'short']


def test_mc_engine_skip_shape(tmp_path):
    engine = MCEngine()
    cfg = MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=True)
    first = engine.run(cfg)
    second = engine.run(cfg)
    assert second.payload['status'] in {'NO_NEW_INPUTS', 'FULL_REFRESH', 'NO_ACTION_DQ_FAIL_DUPLICATE'}


def test_mc_engine_uses_db_persistence_when_available(tmp_path, monkeypatch):
    async def fake_persist(payload, config):
        return 'db-row-1'

    monkeypatch.setattr(engine_module, 'persist_mc_result', fake_persist)
    result = MCEngine().run(MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=True))
    assert result.payload.get('db_result_id') == 'db-row-1'
    assert result.artifact_json is None


def test_mc_engine_falls_back_to_files_when_db_missing(tmp_path, monkeypatch):
    async def fake_persist(payload, config):
        return None

    monkeypatch.setattr(engine_module, 'persist_mc_result', fake_persist)
    result = MCEngine().run(MCEngineConfig(n_batches=1, paths_per_batch=100, expiry_days=1, dt_days=1, output_root=str(tmp_path), write_artifacts=True))
    assert result.artifact_json is not None
