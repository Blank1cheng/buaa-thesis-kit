from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.equations.recognizer import CommandImageRecognizer, parse_recognizer_argv  # noqa: E402
from buaa_thesis_kit.equations.runner import run_equation_pipeline  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Locate, convert, compile, and verify native LaTeX equations from model JSON, DOCX, or PDF."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    recognizer_group = parser.add_mutually_exclusive_group()
    recognizer_group.add_argument(
        "--image-recognizer-command",
        default="",
        help='JSON argv array; use "{image}" for the absolute source preview path.',
    )
    recognizer_group.add_argument(
        "--rapid-latex-ocr-python",
        type=Path,
        help="Python executable from an isolated environment containing rapid_latex_ocr==0.0.9.",
    )
    parser.add_argument("--recognizer-timeout", type=float, default=60.0)
    namespace = parser.parse_args(args)

    recognizer = None
    if namespace.image_recognizer_command:
        try:
            argv = parse_recognizer_argv(namespace.image_recognizer_command)
        except ValueError as exc:
            parser.error(str(exc))
        recognizer = CommandImageRecognizer(argv, timeout_seconds=namespace.recognizer_timeout)
    elif namespace.rapid_latex_ocr_python:
        python_executable = namespace.rapid_latex_ocr_python.resolve()
        if not python_executable.is_file():
            parser.error(f"RapidLaTeXOCR Python executable not found: {python_executable}")
        recognizer = CommandImageRecognizer(
            [str(python_executable), str(ROOT / "scripts" / "rapid_latex_ocr_adapter.py"), "{image}"],
            timeout_seconds=namespace.recognizer_timeout,
        )

    report = run_equation_pipeline(namespace.input, namespace.out, recognizer=recognizer)
    summary = {
        "status": report.get("status"),
        "artifact_identity": report.get("artifact_identity"),
        "source_type": report.get("source_type"),
        "equation_count": report.get("equation_count"),
        "converted": report.get("converted"),
        "needs_review": report.get("needs_review"),
        "failed": report.get("failed"),
        "unsupported": report.get("unsupported"),
        "report": str((namespace.out / "report.json").resolve()),
        "failure_queue": str((namespace.out / "failure_queue.json").resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
