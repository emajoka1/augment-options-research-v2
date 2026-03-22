#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.promotion import promote_proposal, reject_proposal, rollback_latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Approval/rollback admin for AK system")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("approve")
    ap.add_argument("proposal_file")
    ap.add_argument("--approver", default="human")

    rp = sub.add_parser("reject")
    rp.add_argument("proposal_file")
    rp.add_argument("--reason", default="Manual rejection")

    sub.add_parser("rollback")

    args = parser.parse_args()
    root = Path(args.root).resolve()
    paths = build_paths(root)
    ensure_dirs(paths)

    if args.cmd == "approve":
        p, a = promote_proposal(paths, Path(args.proposal_file), approver=args.approver)
        print(f"Pending copy: {p}\nApproved: {a}")
    elif args.cmd == "reject":
        out = reject_proposal(paths, Path(args.proposal_file), reason=args.reason)
        print(f"Rejected: {out}")
    elif args.cmd == "rollback":
        src = rollback_latest(paths)
        print(f"Rolled back from snapshot: {src}")


if __name__ == "__main__":
    main()
