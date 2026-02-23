#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.framework import maybe_propose_weight_update, run_full_framework, save_framework_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full Regime->Structure->Execution->Risk OOS framework")
    parser.add_argument("--root", default=".")
    parser.add_argument("--paths", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    paths = build_paths(root)
    ensure_dirs(paths)

    report = run_full_framework(paths, n_paths=args.paths, seed=args.seed)
    report_file = save_framework_report(paths, report)
    proposal = maybe_propose_weight_update(paths, report)

    print(
        json.dumps(
            {
                "report": str(report_file),
                "proposal": str(proposal) if proposal else None,
                "oos_delta": report.get("oos_delta"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
