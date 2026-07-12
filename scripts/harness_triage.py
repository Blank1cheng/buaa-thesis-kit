from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.progress import load_progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print prioritized harness failures.")
    parser.add_argument("--out", type=Path, default=Path("output/harness"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--fix", help="Show the exact next-fix scope for a single H-xxx id.")
    parser.add_argument("--evidence", help="Show evidence for a single H-xxx id.")
    args = parser.parse_args(argv)
    progress = load_progress(args.out)
    failures = (progress.get("failure_queue") or {}).get("failures", [])
    if args.fix:
        payload = _find_failure(failures, args.fix)
        if payload:
            payload = {"allowed_scope": args.fix, "failure": payload, "instruction": f"Only fix {args.fix}; do not change unrelated gates."}
        print(json.dumps(payload or {"error": f"failure id not found: {args.fix}"}, ensure_ascii=False, indent=2))
        return 0 if payload else 1
    if args.evidence:
        payload = _find_failure(failures, args.evidence)
        if payload:
            packet = progress.get("evidence_packet") or {}
            payload = {
                "failure": payload,
                "candidate_path": packet.get("candidate_path"),
                "candidate_sha256": packet.get("candidate_sha256"),
                "commit": packet.get("commit"),
                "reports": packet.get("reports", {}),
                "artifacts": packet.get("artifacts", {}),
            }
        print(json.dumps(payload or {"error": f"failure id not found: {args.evidence}"}, ensure_ascii=False, indent=2))
        return 0 if payload else 1
    print(json.dumps({"failures": failures[: args.limit]}, ensure_ascii=False, indent=2))
    return 0


def _find_failure(failures: list[dict], failure_id: str) -> dict | None:
    for failure in failures:
        if failure.get("id") == failure_id:
            return failure
    return None


if __name__ == "__main__":
    raise SystemExit(main())
