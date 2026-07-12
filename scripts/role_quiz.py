from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.validators import run_role_quiz


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the BUAA thesis content-role classification quiz.")
    parser.add_argument("--official-template", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("output/role_quiz_report.json"))
    args = parser.parse_args(argv)
    report = run_role_quiz(args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
