from __future__ import annotations

from pathlib import Path


def get_service_artifact_dir(root: str | Path | None = None) -> Path:
    base = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    legacy_kb = base / 'kb' / 'experiments'
    if legacy_kb.exists() or (base / 'kb').exists():
        legacy_kb.mkdir(parents=True, exist_ok=True)
        return legacy_kb
    artifact_dir = base / 'artifacts' / 'options-mc'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir
