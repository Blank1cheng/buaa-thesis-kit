from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from buaa_thesis_kit.equations.verify import (
    compare_formula_images,
    compile_latex_candidate,
    validate_latex_candidate,
)


def apply_agent_equation_reviews(
    native_report: dict[str, Any],
    review_path: str | Path,
    source_path: str | Path,
    native_root: str | Path,
    *,
    compiler: Callable[[str, Path], dict[str, Any]] = compile_latex_candidate,
    comparator: Callable[[Path, Path], dict[str, Any]] = compare_formula_images,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = Path(source_path).resolve(strict=True)
    root = Path(native_root).resolve(strict=True)
    ledger_path = Path(review_path).resolve(strict=True)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not isinstance(ledger, dict):
        raise ValueError("invalid_equation_review_ledger")

    ledger_source = Path(str(ledger.get("source_candidate_path") or "")).resolve(strict=True)
    if ledger_source != source:
        raise ValueError("source_candidate_path_mismatch")
    source_sha256 = _sha256(source)
    ledger_sha256 = _sha256(ledger_path)
    if str(ledger.get("source_sha256") or "").lower() != source_sha256:
        raise ValueError("source_sha256_mismatch")

    updated = copy.deepcopy(native_report)
    equations = {
        str(item.get("id") or ""): item
        for item in updated.get("equations") or []
        if isinstance(item, dict) and item.get("id")
    }
    approved_ids: list[str] = []
    for review in ledger.get("reviews") or []:
        if not isinstance(review, dict):
            raise ValueError("invalid_equation_review_entry")
        equation_id = str(review.get("equation_id") or "")
        if review.get("decision") != "approved" or not equation_id:
            raise ValueError(f"invalid_equation_review_decision:{equation_id or '<missing>'}")
        equation = equations.get(equation_id)
        if equation is None:
            raise ValueError(f"unknown_equation_id:{equation_id}")
        if str(review.get("reviewer") or "") != "agent_visual":
            raise ValueError(f"invalid_equation_reviewer:{equation_id}")
        if not str(review.get("evidence_text") or "").strip():
            raise ValueError(f"missing_equation_review_evidence:{equation_id}")

        equation_dir = root / "equations" / equation_id
        candidate = equation_dir / "candidate.tex"
        source_preview = equation_dir / "source_preview.png"
        rendered = equation_dir / "rendered.png"
        _verify_hash(candidate, review.get("candidate_sha256"), "candidate_sha256_mismatch", equation_id)
        _verify_hash(source_preview, review.get("source_preview_sha256"), "source_preview_sha256_mismatch", equation_id)
        _verify_hash(rendered, review.get("rendered_sha256"), "rendered_sha256_mismatch", equation_id)
        original_candidate_sha256 = _sha256(candidate)
        original_source_preview_sha256 = _sha256(source_preview)
        original_rendered_sha256 = _sha256(rendered)

        latex = str(review.get("latex") or "").strip()
        candidate_latex = candidate.read_text(encoding="utf-8").strip()
        if not latex:
            raise ValueError(f"reviewed_latex_candidate_mismatch:{equation_id}")
        candidate_corrected = latex != candidate_latex
        if candidate_corrected:
            if not str(review.get("correction_reason") or "").strip():
                raise ValueError(f"missing_equation_correction_reason:{equation_id}")
            expected_latex_sha = str(review.get("corrected_latex_sha256") or "").lower()
            if expected_latex_sha != _text_sha256(latex):
                raise ValueError(f"corrected_latex_sha256_mismatch:{equation_id}")
        compile_report = equation.get("compile") if isinstance(equation.get("compile"), dict) else {}
        visual_report = equation.get("visual") if isinstance(equation.get("visual"), dict) else {}
        if compile_report.get("status") != "success" or visual_report.get("status") != "pass":
            raise ValueError(f"equation_candidate_not_verified:{equation_id}")
        corrected_candidate_sha256 = ""
        corrected_rendered_sha256 = ""
        if candidate_corrected:
            validation_failures = validate_latex_candidate(latex)
            if validation_failures:
                raise ValueError(f"corrected_equation_unsafe:{equation_id}")
            compile_report = compiler(latex, equation_dir)
            if compile_report.get("status") != "success":
                raise ValueError(f"corrected_equation_compile_failed:{equation_id}")
            corrected_rendered = Path(str(compile_report.get("rendered_png") or ""))
            if (
                not candidate.is_file()
                or candidate.read_text(encoding="utf-8").strip() != latex
                or not corrected_rendered.is_file()
            ):
                raise ValueError(f"corrected_equation_artifact_missing:{equation_id}")
            visual_report = comparator(source_preview, corrected_rendered)
            if visual_report.get("status") != "pass":
                raise ValueError(f"corrected_equation_visual_failed:{equation_id}")
            corrected_candidate_sha256 = _sha256(candidate)
            corrected_rendered_sha256 = _sha256(corrected_rendered)
            equation["compile"] = compile_report
            equation["visual"] = visual_report

        equation["status"] = "converted"
        equation["latex"] = latex
        conversion = equation.get("conversion") if isinstance(equation.get("conversion"), dict) else {}
        conversion["status"] = "converted"
        conversion["latex"] = latex
        conversion["method"] = "agent_visual_review"
        equation["conversion"] = conversion
        equation["agent_review"] = {
            "reviewer": "agent_visual",
            "evidence_text": str(review["evidence_text"]),
            "ledger_name": ledger_path.name,
            "ledger_sha256": ledger_sha256,
            "source_sha256": source_sha256,
            "candidate_sha256": original_candidate_sha256,
            "source_preview_sha256": original_source_preview_sha256,
            "rendered_sha256": original_rendered_sha256,
            "candidate_corrected": candidate_corrected,
            "corrected_latex_sha256": _text_sha256(latex),
            "corrected_candidate_sha256": corrected_candidate_sha256,
            "corrected_rendered_sha256": corrected_rendered_sha256,
            "correction_reason": str(review.get("correction_reason") or ""),
            "requires_post_render_visual_review": False,
        }
        equation["artifacts"] = _refresh_artifact_manifest(equation_dir)
        approved_ids.append(equation_id)

    approved = set(approved_ids)
    updated["failure_queue"] = [
        failure
        for failure in updated.get("failure_queue") or []
        if _failure_equation_id(failure) not in approved
    ]
    statuses = [str(item.get("status") or "") for item in equations.values()]
    updated["equation_count"] = len(equations)
    updated["converted"] = sum(status == "converted" for status in statuses)
    updated["needs_review"] = sum(status == "candidate_needs_review" for status in statuses)
    updated["failed"] = sum(status == "failed" for status in statuses)
    updated["unsupported"] = sum(status == "unsupported" for status in statuses)
    updated["status"] = (
        "failed"
        if updated["failed"]
        else "needs_review"
        if updated["needs_review"] or updated["unsupported"]
        else "pass"
    )
    audit = {
        "status": "pass",
        "ledger_name": ledger_path.name,
        "ledger_sha256": ledger_sha256,
        "source_candidate_path": str(source),
        "source_sha256": source_sha256,
        "approved_equation_ids": approved_ids,
    }
    return updated, audit


def _verify_hash(path: Path, expected: Any, reason: str, equation_id: str) -> None:
    if not path.is_file() or str(expected or "").lower() != _sha256(path):
        raise ValueError(f"{reason}:{equation_id}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _failure_equation_id(failure: Any) -> str:
    if not isinstance(failure, dict):
        return ""
    region = str(failure.get("region") or "")
    return region.split("equations.", 1)[1] if region.startswith("equations.") else ""


def _refresh_artifact_manifest(equation_dir: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(equation_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "artifact_hashes.json":
            continue
        artifacts[path.name] = {
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
    (equation_dir / "artifact_hashes.json").write_text(
        json.dumps(artifacts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return artifacts


__all__ = ["apply_agent_equation_reviews"]
