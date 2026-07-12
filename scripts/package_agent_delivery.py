from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.delivery_packaging import package_agent_delivery  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package a reviewed BUAA thesis run into the flat public output contract."
    )
    parser.add_argument("source", type=Path, help="Exact DOCX or PDF source candidate.")
    parser.add_argument("--run", required=True, type=Path, help="LaTeX pipeline run directory.")
    parser.add_argument("--output", required=True, type=Path, help="Public delivery directory.")
    parser.add_argument(
        "--visual-manifest",
        required=True,
        type=Path,
        help="Agent-reviewed visual_review.json; screenshots must be beside it.",
    )
    parser.add_argument(
        "--template", required=True, type=Path, help="Pinned BUAAthesis template directory."
    )
    parser.add_argument(
        "--editable-docx",
        type=Path,
        help="Semantic editable DOCX; required when the source candidate is PDF.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace an existing output directory.")
    parser.add_argument(
        "--out", required=True, type=Path, help="Packaging report path outside public output."
    )
    return parser


def main(args: list[str] | None = None) -> int:
    parser = _build_parser()
    namespace = parser.parse_args(args)
    try:
        output = namespace.output.resolve()
        report = namespace.out.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(f"unable to resolve output paths: {exc}")
    if report == output or report.is_relative_to(output):
        parser.error("--out must be outside the public output directory")

    result = package_agent_delivery(
        source_path=namespace.source,
        pipeline_run_dir=namespace.run,
        output_dir=namespace.output,
        visual_manifest_path=namespace.visual_manifest,
        template_dir=namespace.template,
        editable_docx_path=namespace.editable_docx,
        replace_existing=namespace.replace,
    )
    namespace.out.parent.mkdir(parents=True, exist_ok=True)
    namespace.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
