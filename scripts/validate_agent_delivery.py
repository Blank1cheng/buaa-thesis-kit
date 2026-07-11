from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.delivery import validate_delivery  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an Agent thesis delivery bundle.")
    parser.add_argument("--output", required=True, type=Path, help="Delivery output directory.")
    parser.add_argument("--profile", required=True, help="Harness profile name.")
    parser.add_argument("--gate-board", required=True, type=Path, help="Gate board JSON path.")
    parser.add_argument("--candidate", type=Path, help="Original candidate document path.")
    parser.add_argument("--out", required=True, type=Path, help="Explicit validation report path.")
    return parser


def main(args: list[str] | None = None) -> int:
    parser = _build_parser()
    namespace = parser.parse_args(args)
    try:
        output_path = namespace.output.resolve()
        report_path = namespace.out.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(f"unable to resolve output paths: {exc}")
    if report_path == output_path or report_path.is_relative_to(output_path):
        parser.error("--out must be outside the delivery output directory")

    result = validate_delivery(
        namespace.output,
        profile=namespace.profile,
        gate_board_path=namespace.gate_board,
        candidate_path=namespace.candidate,
    )

    namespace.out.parent.mkdir(parents=True, exist_ok=True)
    namespace.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"pass": 0, "needs_review": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
