#!/usr/bin/env python3
import json, sys
from datetime import datetime, timezone
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("usage: write_ticket.py TYPE ID [PRIORITY]", file=sys.stderr)
        sys.exit(2)
    typ = sys.argv[1]
    tid = sys.argv[2]
    pr = sys.argv[3] if len(sys.argv) >= 4 else "P2"
    created = datetime.now(timezone.utc).isoformat()
    inbox = Path("kb/inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fn = inbox / f"{typ}__{tid}__{stamp}.json"
    payload = {
        "type": typ,
        "id": tid,
        "priority": pr,
        "created_utc": created,
        "problem": "",
        "evidence": {},
        "required_change": [],
        "acceptance_tests": [],
        "constraints": [],
        "output_expected": [
            "PR-style summary",
            "files changed list",
            "tests passing proof",
            "commit hash"
        ]
    }
    fn.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(str(fn))

if __name__ == "__main__":
    main()
