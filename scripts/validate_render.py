from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.validators import validate_render_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run render-level harness checks for thesis.docx.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--sample-mode", default="full", choices=("full", "truncated"))
    parser.add_argument("--out", type=Path, default=Path("output/render_diff"))
    args = parser.parse_args(argv)
    report = validate_render_file(candidate=args.candidate, reference=args.reference, out_dir=args.out, sample_mode=args.sample_mode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
