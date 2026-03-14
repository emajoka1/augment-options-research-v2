#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.pipeline import propose_if_improved_from_regime_report, run_regime_validation


def _to_markdown(report: dict) -> str:
    lines = []
    lines.append("# Regime Harness Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Paths simulated: {report.get('n_paths')}")
    lines.append("")

    lines.append("## Ranking by regime")
    for regime, rows in report.get("ranking_by_regime", {}).items():
        lines.append(f"### {regime}")
        for i, r in enumerate(rows, start=1):
            ci = r.get("ci95", [0, 0])
            lines.append(
                f"{i}. {r['playbook']} | mean_R={r['mean_r']:.3f} | CI95=[{ci[0]:.3f}, {ci[1]:.3f}] | n={r['n']}"
            )
        lines.append("")

    lines.append("## Failure modes (avg impact per path)")
    for pb, fm in report.get("failure_modes", {}).items():
        lines.append(f"### {pb}")
        for k, v in fm.items():
            lines.append(f"- {k}: {v:.4f}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full Monte Carlo + regime validation harness")
    parser.add_argument("--root", default=".")
    parser.add_argument("--paths", type=int, default=500)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    paths = build_paths(root)
    ensure_dirs(paths)

    report_file = run_regime_validation(paths, n_paths=args.paths)
    report = json.loads(report_file.read_text(encoding="utf-8"))

    md_file = report_file.with_suffix(".md")
    md_file.write_text(_to_markdown(report), encoding="utf-8")

    proposal = propose_if_improved_from_regime_report(paths, report_file)

    out = {
        "report_json": str(report_file),
        "report_md": str(md_file),
        "proposal": str(proposal) if proposal else None,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
