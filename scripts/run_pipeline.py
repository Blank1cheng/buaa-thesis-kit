from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.pipeline import run_pipeline  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the BUAA thesis Phase 1 pipeline.")
    parser.add_argument("source", type=Path, help="Source thesis DOCX file.")
    parser.add_argument("--out", required=True, type=Path, help="Public output directory.")
    parser.add_argument("--template", type=Path, default=None, help="Optional Word DOCX template.")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Retain the adjacent process work directory for inspection.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail finalization when any output or report item still needs manual review.",
    )
    namespace = parser.parse_args(args)

    report = run_pipeline(
        namespace.source,
        namespace.out,
        template_path=namespace.template,
        keep_work=namespace.keep_work,
        strict=namespace.strict,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"pass", "needs_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
