from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.latex.pipeline import run_latex_pipeline  # noqa: E402


def _print_json_report(report: dict[str, Any], *, stream: TextIO | None = None) -> None:
    target = stream or sys.stdout
    reconfigure = getattr(target, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass
    print(json.dumps(report, ensure_ascii=False, indent=2), file=target)


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run DOCX/PDF -> model -> BUAAthesis LaTeX pipeline.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--buaa-template-path", required=True, type=Path)
    parser.add_argument("--degree-type", default="undergraduate")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sample-mode", default="full")
    parser.add_argument("--ranges", default="")
    parser.add_argument("--allow-extraction-fail", action="store_true")
    parser.add_argument("--allow-missing-metadata", action="store_true")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--equation-review", type=Path)
    namespace = parser.parse_args(args)

    report = run_latex_pipeline(
        namespace.input,
        template_path=namespace.buaa_template_path,
        degree_type=namespace.degree_type,
        out_dir=namespace.out,
        compile_pdf=not namespace.no_compile,
        sample_mode=namespace.sample_mode,
        ranges=namespace.ranges,
        allow_extraction_fail=namespace.allow_extraction_fail,
        allow_missing_metadata=namespace.allow_missing_metadata,
        equation_review_path=namespace.equation_review,
    )
    _print_json_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
