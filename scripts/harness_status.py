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
    parser = argparse.ArgumentParser(description="Print current harness gate status.")
    parser.add_argument("--out", type=Path, default=Path("output/harness"))
    args = parser.parse_args(argv)
    progress = load_progress(args.out)
    gate_board = progress.get("gate_board") or {}
    failures = (progress.get("failure_queue") or {}).get("failures", [])
    payload = {
        "overall_status": gate_board.get("overall_status"),
        "current_phase": gate_board.get("current_phase"),
        "candidate_path": gate_board.get("candidate_path"),
        "candidate_sha256": gate_board.get("candidate_sha256"),
        "commit": gate_board.get("commit"),
        "next_failure": failures[0] if failures else None,
        "gate_board": gate_board.get("gates", []),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
