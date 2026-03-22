from __future__ import annotations

from ak_system.local_artifacts import get_service_artifact_dir


def test_get_service_artifact_dir_uses_service_root(tmp_path):
    path = get_service_artifact_dir(tmp_path)
    assert path == tmp_path / 'artifacts' / 'options-mc'
    assert path.exists()


def test_get_service_artifact_dir_is_stable(tmp_path):
    first = get_service_artifact_dir(tmp_path)
    second = get_service_artifact_dir(tmp_path)
    assert first == second


def test_get_service_artifact_dir_uses_legacy_kb_when_present(tmp_path):
    (tmp_path / 'kb').mkdir(parents=True, exist_ok=True)
    path = get_service_artifact_dir(tmp_path)
    assert path == tmp_path / 'kb' / 'experiments'
    assert path.exists()
