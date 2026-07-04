from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.validators import (
    run_role_quiz,
    validate_model_file,
    validate_output_text_file,
    validate_render_file,
)


def run_harness(
    *,
    source: Path | None = None,
    official_template: Path | None = None,
    candidate: Path,
    model_json: Path | None = None,
    expected_model: Path | None = None,
    out_dir: Path = Path("output/harness"),
    sample_mode: str = "full",
    continue_on_fail: bool = False,
    include_template_inheritance: bool = False,
    include_render: bool = False,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stages: list[dict[str, Any]] = []

    def record(stage: str, report: dict[str, Any], report_name: str) -> bool:
        report_path = out / report_name
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        stages.append({"stage": stage, "status": report["status"], "report": str(report_path)})
        return report["status"] == "pass"

    role_report = run_role_quiz(out / "role_quiz_report.json")
    if not record("role_quiz", role_report, "role_quiz_report.json") and not continue_on_fail:
        return _write_status(out, "failed", stages, "role_quiz")

    model_path = Path(model_json) if model_json is not None else candidate.with_name("model.json")
    if model_path.exists():
        model_report = validate_model_file(
            model_path,
            expected_model,
            sample_mode=sample_mode,
            output_report=out / "model_validation_report.json",
        )
    else:
        model_report = {"status": "failed", "failures": [{"id": "model_json_missing", "path": str(model_path)}]}
    if not record("model", model_report, "model_validation_report.json") and not continue_on_fail:
        return _write_status(out, "failed", stages, "model")

    output_text_report = validate_output_text_file(candidate, out / "output_text_report.json")
    if not record("output_text", output_text_report, "output_text_report.json") and not continue_on_fail:
        return _write_status(out, "failed", stages, "output_text")

    if include_template_inheritance:
        if official_template is None:
            inheritance_report = {"status": "failed", "failures": [{"id": "official_template_missing"}]}
        else:
            inheritance_report = _run_template_inheritance(official_template, candidate, out / "template_inheritance_report.json")
        if not record("template_inheritance", inheritance_report, "template_inheritance_report.json") and not continue_on_fail:
            return _write_status(out, "failed", stages, "template_inheritance")

    if include_render:
        render_report = validate_render_file(candidate=candidate, reference=source, out_dir=out / "render_diff", sample_mode=sample_mode)
        (out / "render_report.json").write_text(json.dumps(render_report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not record("render", render_report, "render_report.json") and not continue_on_fail:
            return _write_status(out, "failed", stages, "render")

    final_status = "failed" if any(stage["status"] != "pass" for stage in stages) else "pass"
    failed_stage = next((stage["stage"] for stage in stages if stage["status"] != "pass"), None)
    return _write_status(out, final_status, stages, failed_stage)


def _run_template_inheritance(base: Path, candidate: Path, out: Path) -> dict[str, Any]:
    try:
        from scripts.validate_template_inheritance import validate_template_inheritance

        return validate_template_inheritance(base, candidate, out, word_com_finalized=True)
    except Exception as exc:
        report = {"status": "failed", "failures": [{"id": "template_inheritance_exception", "message": str(exc)}]}
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def _write_status(out: Path, status: str, stages: list[dict[str, Any]], failed_stage: str | None) -> dict[str, Any]:
    report = {"status": status, "failed_stage": failed_stage, "stages": stages}
    (out / "status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run BUAA thesis harness gates.")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--official-template", type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--model-json", type=Path)
    parser.add_argument("--expected-model", type=Path)
    parser.add_argument("--sample-mode", default="full", choices=("full", "truncated"))
    parser.add_argument("--out", type=Path, default=Path("output/harness"))
    parser.add_argument("--continue-on-fail", action="store_true")
    parser.add_argument("--include-template-inheritance", action="store_true")
    parser.add_argument("--include-render", action="store_true")
    args = parser.parse_args(argv)
    report = run_harness(
        source=args.source,
        official_template=args.official_template,
        candidate=args.candidate,
        model_json=args.model_json,
        expected_model=args.expected_model,
        out_dir=args.out,
        sample_mode=args.sample_mode,
        continue_on_fail=args.continue_on_fail,
        include_template_inheritance=args.include_template_inheritance,
        include_render=args.include_render,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
