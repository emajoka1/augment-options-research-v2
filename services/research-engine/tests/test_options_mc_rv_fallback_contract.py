import numpy as np

from ak_system.mc_options.engine import MCEngine, MCEngineConfig
import ak_system.mc_options.engine as engine_module


def test_engine_does_not_use_local_rv_fallback_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, 'load_local_returns_fallback', lambda root: (_ for _ in ()).throw(AssertionError('should not be called')))
    result = MCEngine().run(
        MCEngineConfig(
            n_batches=1,
            paths_per_batch=20,
            expiry_days=1,
            dt_days=1,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )
    assert result.data_quality_status.startswith('DATA_QUALITY_FAIL')


def test_engine_can_use_local_rv_fallback_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, 'load_local_returns_fallback', lambda root: (np.array([0.01] * 30, dtype=float), 'local_fallback', '2026-03-23T00:00:00+00:00', 0.0))
    result = MCEngine().run(
        MCEngineConfig(
            n_batches=1,
            paths_per_batch=20,
            expiry_days=1,
            dt_days=1,
            allow_local_rv_fallback=True,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )
    assert result.payload['calibration']['rv_source'] == 'local_fallback'


def test_snapshot_rv_still_takes_priority_over_local_fallback(tmp_path, monkeypatch):
    snap = tmp_path / 'chain.json'
    snap.write_text('{"spot": 100.0, "chain": [{"strike": 100, "iv": 0.25, "expiry_days": 5}], "returns": [0.01, -0.02, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01, 0.0, 0.01, -0.01, 0.02, -0.01]}')
    monkeypatch.setattr(engine_module, 'load_local_returns_fallback', lambda root: (np.array([0.03] * 30, dtype=float), 'local_fallback', '2026-03-23T00:00:00+00:00', 0.0))
    result = MCEngine().run(
        MCEngineConfig(
            snapshot_file=str(snap),
            n_batches=1,
            paths_per_batch=20,
            expiry_days=1,
            dt_days=1,
            allow_local_rv_fallback=True,
            output_root=str(tmp_path),
            write_artifacts=False,
        )
    )
    assert result.payload['calibration']['rv_source'] == 'snapshot_primary'
