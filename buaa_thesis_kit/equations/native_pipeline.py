from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from buaa_thesis_kit.latex.assets import stage_latex_image_asset

from .mathtype_sdk import MathTypeSdkConverter
from .omml_to_latex import OmmlConversionError, omml_to_latex
from .verify import compare_formula_images, compile_latex_candidate, validate_latex_candidate


FAILURE_IDS = {
    "native_source_missing": "H-EQ-001",
    "native_conversion_failed": "H-EQ-002",
    "mathtype_translator_warning": "H-EQ-003",
    "unsafe_latex_candidate": "H-EQ-004",
    "latex_compile_failed": "H-EQ-005",
    "visual_comparison_failed": "H-EQ-006",
    "image_recognizer_unavailable": "H-EQ-007",
    "source_preview_missing": "H-EQ-008",
    "image_recognition_review_required": "H-EQ-009",
    "image_recognition_failed": "H-EQ-010",
    "no_equations_located": "H-EQ-011",
}


def run_equation_items(
    equations: list[dict[str, Any]],
    out_dir: str | Path,
    *,
    model_root: str | Path | None = None,
    mathtype_converter: Any | None = None,
    compiler: Callable[[str, Path], dict[str, Any]] = compile_latex_candidate,
    comparator: Callable[[Path, Path], dict[str, Any]] = compare_formula_images,
    recognizer: Any | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    model_root = Path(model_root) if model_root else Path.cwd()
    equation_root = out_dir / "equations"
    equation_root.mkdir(parents=True, exist_ok=True)
    converter = mathtype_converter or MathTypeSdkConverter()
    failures: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for ordinal, equation in enumerate(equations, 1):
        equation_id = _safe_id(equation.get("id") or f"eq-{ordinal}")
        item_dir = equation_root / equation_id
        if item_dir.exists():
            shutil.rmtree(item_dir)
        item_dir.mkdir(parents=True)
        source_record = _source_record(equation, equation_id)
        (item_dir / "source.json").write_text(json.dumps(source_record, ensure_ascii=False, indent=2), encoding="utf-8")
        source_preview = _stage_source_preview(equation, item_dir, model_root)
        conversion = _convert_equation(equation, item_dir, model_root, converter, source_preview, recognizer)
        latex = str(conversion.get("latex") or "").strip()
        item_failures: list[dict[str, Any]] = []

        def add_failure(reason: str, evidence: str, expected: str, suggested_fix: str, can_fix_now: bool = True) -> None:
            failure = {
                "id": f"{FAILURE_IDS[reason]}-{equation_id}",
                "gate": "EQ_NATIVE",
                "reason": reason,
                "region": f"equations.{equation_id}",
                "evidence_text": evidence,
                "expected": expected,
                "suggested_fix": suggested_fix,
                "can_fix_now": can_fix_now,
            }
            failures.append(failure)
            item_failures.append(failure)

        if conversion["status"] == "failed":
            reason = "image_recognition_failed" if conversion.get("method") == "image_recognizer" else "native_conversion_failed"
            add_failure(
                reason,
                str(conversion.get("warning") or conversion),
                "Native equation data converts to a non-empty LaTeX candidate.",
                "Inspect the OMML/MTEF source and converter status; retain the preview until resolved.",
            )
        elif conversion["status"] == "unsupported":
            reason = "native_source_missing" if conversion.get("reason") == "native_source_missing" else "image_recognizer_unavailable"
            add_failure(
                reason,
                str(conversion.get("warning") or conversion.get("reason") or "unsupported"),
                "Every equation has a deterministic native source or an explicitly configured recognizer.",
                "Recover OMML/MTEF data or configure a reviewed image recognizer.",
                can_fix_now=False,
            )
        if conversion["status"] == "candidate_needs_review":
            reason = (
                "image_recognition_review_required"
                if conversion.get("method") == "image_recognizer"
                else "mathtype_translator_warning"
            )
            add_failure(
                reason,
                str(conversion.get("warning") or conversion.get("return_code") or conversion.get("confidence")),
                "The candidate has a deterministic native conversion with no recognizer uncertainty.",
                "Compare the candidate against the source preview; image recognition never writes back without review.",
            )

        validation = validate_latex_candidate(latex) if latex else ["empty_latex"]
        if latex:
            (item_dir / "candidate.tex").write_text(latex, encoding="utf-8")
        if latex and validation:
            add_failure(
                "unsafe_latex_candidate",
                ", ".join(validation),
                "The candidate is expression-only LaTeX with balanced groups and no file/document commands.",
                "Repair or reject the candidate before compilation.",
            )

        compile_report: dict[str, Any] = {"status": "not_run"}
        if latex and not validation:
            compile_report = compiler(latex, item_dir)
            if compile_report.get("status") not in {"success"}:
                add_failure(
                    "latex_compile_failed",
                    json.dumps(compile_report, ensure_ascii=False),
                    "The candidate compiles in an isolated XeLaTeX document.",
                    "Inspect standalone.tex and compile.log; do not write the candidate into body.tex.",
                )

        visual_report: dict[str, Any] = {"status": "not_available"}
        rendered = Path(str(compile_report.get("rendered_png") or ""))
        if source_preview and rendered.is_file():
            visual_report = comparator(source_preview, rendered)
            if visual_report.get("status") != "pass":
                add_failure(
                    "visual_comparison_failed",
                    json.dumps(visual_report, ensure_ascii=False),
                    "The compiled candidate meets the fixed visual similarity threshold against the source preview.",
                    "Review the candidate and source crop; do not lower the threshold to force a pass.",
                )
        elif conversion.get("method") == "mathtype_sdk" and compile_report.get("status") == "success":
            add_failure(
                "source_preview_missing",
                "MathType native source converted but no source preview was available for comparison.",
                "A MathType conversion has a source preview or an equivalent independent verification artifact.",
                "Recover the OLE preview image before automatic write-back.",
                can_fix_now=False,
            )

        if any(item["reason"] in {"native_conversion_failed", "unsafe_latex_candidate", "latex_compile_failed"} for item in item_failures):
            status = "failed"
        elif conversion.get("status") == "unsupported" and not latex:
            status = "unsupported"
        elif item_failures:
            status = "candidate_needs_review"
        elif latex and compile_report.get("status") == "success":
            status = "converted"
        else:
            status = "unsupported"
        verification = {
            "equation_id": equation_id,
            "status": status,
            "conversion": conversion,
            "validation": validation,
            "compile": compile_report,
            "visual": visual_report,
            "failures": item_failures,
        }
        (item_dir / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = _artifact_manifest(item_dir)
        (item_dir / "artifact_hashes.json").write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(
            {
                "id": equation_id,
                "kind": equation.get("kind") or "unknown",
                "status": status,
                "latex": latex,
                "source": source_record.get("source"),
                "conversion": conversion,
                "compile": compile_report,
                "visual": visual_report,
                "artifacts": artifacts,
            }
        )

    if not results:
        failures.append(
            {
                "id": "H-EQ-011-document",
                "gate": "EQ_LOCATE",
                "reason": "no_equations_located",
                "region": "document",
                "evidence_text": "The equation locator returned zero items.",
                "expected": "The locator reports every equation region, or explicitly verifies that the source contains none.",
                "suggested_fix": "Inspect DOCX OMML/OLE objects or PDF equation-region detection before rendering.",
                "can_fix_now": True,
            }
        )
    status = (
        "failed"
        if not results or any(item["status"] == "failed" for item in results)
        else "needs_review"
        if failures
        else "pass"
    )
    report = {
        "status": status,
        "equation_count": len(results),
        "converted": sum(item["status"] == "converted" for item in results),
        "needs_review": sum(item["status"] == "candidate_needs_review" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "unsupported": sum(item["status"] == "unsupported" for item in results),
        "equations": results,
        "failure_queue": failures,
    }
    (out_dir / "equation_manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "failure_queue.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _convert_equation(
    equation: dict[str, Any],
    item_dir: Path,
    model_root: Path,
    converter: Any,
    source_preview: Path | None,
    recognizer: Any | None,
) -> dict[str, Any]:
    kind = str(equation.get("kind") or "")
    is_pdf_text_candidate = kind.lower() == "pdf-text-equation"
    trusted_latex = str(equation.get("latex") or equation.get("tex") or "").strip()
    omml = str(equation.get("omml") or "").strip()
    if omml and not is_pdf_text_candidate:
        (item_dir / "source.omml").write_text(omml, encoding="utf-8")
        try:
            latex = omml_to_latex(omml)
            return {"status": "converted", "method": "omml_parser", "latex": latex}
        except OmmlConversionError as exc:
            return {"status": "failed", "method": "omml_parser", "latex": "", "warning": str(exc)}
    native_path = _resolve_asset(equation, model_root, "native_path", "native_asset")
    if native_path and native_path.is_file():
        native = native_path.read_bytes()
        shutil.copy2(native_path, item_dir / "source.mtef")
        converted = converter.convert(native).to_dict()
        converted["method"] = "mathtype_sdk"
        return converted
    if (
        trusted_latex
        and not bool(equation.get("requires_review"))
        and kind.lower() in {"latex", "tex"}
    ):
        return {"status": "converted", "method": "trusted_source_latex", "latex": trusted_latex}
    if source_preview is not None:
        if recognizer is None:
            return {
                "status": "unsupported",
                "method": "image_recognizer",
                "latex": "",
                "reason": "image_recognizer_unavailable",
                "warning": "A source preview exists, but no image recognizer was configured.",
            }
        recognized = recognizer.recognize(source_preview)
        converted = recognized.to_dict() if hasattr(recognized, "to_dict") else dict(recognized)
        converted["method"] = "image_recognizer"
        return converted
    return {
        "status": "unsupported",
        "method": "none",
        "latex": "",
        "reason": "native_source_missing",
        "warning": "No trusted LaTeX, OMML, or MathType native stream was found.",
    }


def _stage_source_preview(equation: dict[str, Any], item_dir: Path, model_root: Path) -> Path | None:
    preview = _resolve_asset(equation, model_root, "preview_path", "render_asset")
    if preview is None:
        preview_name = str(equation.get("preview_asset_name") or "")
        if preview_name:
            stem = Path(preview_name).stem
            preview = next(
                (path for suffix in (".png", ".jpg", ".jpeg", ".pdf") if (path := model_root / "assets" / "equations" / f"{stem}{suffix}").is_file()),
                None,
            )
    if preview is None or not preview.is_file():
        return None
    staged = stage_latex_image_asset(preview, item_dir, set())
    if staged is None:
        return None
    target = item_dir / ("source_preview.pdf" if staged.suffix.lower() == ".pdf" else "source_preview.png")
    if staged != target:
        staged.replace(target)
    return target


def _resolve_asset(equation: dict[str, Any], root: Path, *keys: str) -> Path | None:
    for key in keys:
        value = str(equation.get(key) or "").strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if path.exists():
            return path
    return None


def _source_record(equation: dict[str, Any], equation_id: str) -> dict[str, Any]:
    source = equation.get("source") if isinstance(equation.get("source"), dict) else {
        "source_page": equation.get("source_page"),
        "paragraph_index": equation.get("paragraph_index"),
    }
    return {
        "id": equation_id,
        "kind": equation.get("kind") or "unknown",
        "source": source,
        "native_format": equation.get("native_format") or "",
        "native_sha256": equation.get("native_sha256") or "",
        "source_text": equation.get("source_text") or equation.get("text") or "",
        "region_bbox": list(equation.get("region_bbox") or []),
    }


def _artifact_manifest(item_dir: Path) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(item_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "artifact_hashes.json":
            continue
        manifest[path.name] = {"path": str(path), "size": path.stat().st_size, "sha256": _sha256(path)}
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "equation")).strip("._") or "equation"
