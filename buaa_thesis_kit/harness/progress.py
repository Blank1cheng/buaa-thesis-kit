from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from buaa_thesis_kit.harness.artifact_identity import artifact_identity, sha256_file


CONFIG_DIR = Path(__file__).resolve().parent / "config"
STATUS_VALUES = {"pass", "failed", "needs_review", "skipped", "todo"}
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
REPORT_BY_GATE = {
    "artifact_identity": ("artifact_identity.json",),
    "role_quiz": ("role_quiz_report.json",),
    "model_validation": ("model_validation_report.json",),
    "instrumented_template": ("instrumented_template_report.json",),
    "bad_fixture_regression": ("bad_fixture_regression_report.json",),
    "pre_finalize_output_text": ("output_text_report.json",),
    "post_finalize_output_text": ("output_text_post_finalize_report.json",),
    "template_inheritance": ("template_inheritance_report.json",),
    "render_smoke": ("render_smoke/report.json",),
}
FAILURE_REPORTS = {
    "artifact_identity.json": "artifact_identity",
    "role_quiz_report.json": "role_quiz",
    "model_validation_report.json": "model_validation",
    "instrumented_template_report.json": "instrumented_template",
    "bad_fixture_regression_report.json": "bad_fixture_regression",
    "output_text_report.json": "pre_finalize_output_text",
    "output_text_post_finalize_report.json": "post_finalize_output_text",
    "template_inheritance_report.json": "template_inheritance",
    "render_smoke/report.json": "render_smoke",
}


def write_progress_artifacts(
    harness_dir: Path,
    *,
    candidate_path: Path | None = None,
    template_path: Path | None = None,
    model_path: Path | None = None,
    sample_mode: str = "full",
    commands: list[str] | None = None,
    reports: dict[str, str] | None = None,
    artifacts: dict[str, Any] | None = None,
    fixed_failures: list[str] | None = None,
    render_smoke_dir: Path | None = None,
) -> dict[str, Any]:
    """Aggregate harness reports into user-facing progress artifacts."""
    harness = Path(harness_dir)
    harness.mkdir(parents=True, exist_ok=True)
    render_dir = _resolve_render_smoke_dir(harness, render_smoke_dir)
    candidate = _resolve_candidate_path(harness, candidate_path)
    model = _resolve_existing_path(model_path)
    template = _resolve_existing_path(template_path)
    identity = _load_or_create_identity(harness, candidate, model, template)
    run_id = _run_id()
    commit = _git_commit()

    gates = _build_gates(
        harness,
        render_dir=render_dir,
        candidate=candidate,
        identity=identity,
    )
    gate_board = {
        "run_id": run_id,
        "commit": identity.get("commit") or commit,
        "source_candidate_path": identity.get("source_candidate_path"),
        "bad_fixture_path": identity.get("bad_fixture_path"),
        "candidate_path": identity.get("candidate_path") or (str(candidate) if candidate else None),
        "candidate_sha256": identity.get("candidate_sha256"),
        "candidate_size": identity.get("candidate_size"),
        "template_path": identity.get("template_path") or (str(template) if template else None),
        "template_sha256": identity.get("template_sha256") or _optional_sha(template),
        "model_path": identity.get("source_model_path") or (str(model) if model else None),
        "model_sha256": identity.get("source_model_sha256") or _optional_sha(model),
        "sample_mode": sample_mode,
        "overall_status": _overall_status(gates),
        "current_phase": _current_phase(gates),
        "gates": gates,
    }

    failure_queue = _build_failure_queue(
        harness,
        render_dir=render_dir,
        gates=gates,
        identity=identity,
    )
    generated_reports = _report_index(harness, render_dir=render_dir)
    if reports:
        generated_reports.update(reports)
    generated_artifacts = _artifact_index(harness, render_dir=render_dir, candidate=candidate)
    if artifacts:
        generated_artifacts.update(artifacts)

    packet = {
        "run_id": run_id,
        "source_candidate_path": identity.get("source_candidate_path"),
        "bad_fixture_path": identity.get("bad_fixture_path"),
        "candidate_path": identity.get("candidate_path") or (str(candidate) if candidate else None),
        "candidate_sha256": identity.get("candidate_sha256"),
        "candidate_size": identity.get("candidate_size"),
        "commit": identity.get("commit") or commit,
        "commands": commands or [],
        "reports": generated_reports,
        "artifacts": generated_artifacts,
        "fixed_failures": fixed_failures or [],
        "remaining_failures": [item["id"] for item in failure_queue["failures"]],
    }

    _write_json(harness / "gate_board.json", gate_board)
    _write_json(harness / "failure_queue.json", failure_queue)
    _write_json(harness / "evidence_packet.json", packet)
    _write_progress_md(harness / "progress.md", gate_board, failure_queue, packet)
    _ensure_status_json(harness, gate_board)
    return packet


def load_progress(harness_dir: Path) -> dict[str, Any]:
    harness = Path(harness_dir)
    return {
        "status": _read_json(harness / "status.json"),
        "gate_board": _read_json(harness / "gate_board.json"),
        "failure_queue": _read_json(harness / "failure_queue.json"),
        "evidence_packet": _read_json(harness / "evidence_packet.json"),
    }


def _load_gates() -> list[dict[str, Any]]:
    data = yaml.safe_load((CONFIG_DIR / "gates.yaml").read_text(encoding="utf-8")) or {}
    return [dict(item) for item in data.get("gates", [])]


def _build_gates(
    harness: Path,
    *,
    render_dir: Path | None,
    candidate: Path | None,
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for spec in _load_gates():
        name = str(spec["name"])
        report_path = _find_gate_report(harness, name, render_dir=render_dir)
        status = _gate_status(name, report_path, candidate=candidate, identity=identity)
        result.append(
            {
                "id": spec["id"],
                "name": name,
                "required": bool(spec.get("required", False)),
                "phase": spec.get("phase", "P5"),
                "status": status,
                "report": str(report_path) if report_path is not None else None,
            }
        )
    return result


def _gate_status(
    name: str,
    report_path: Path | None,
    *,
    candidate: Path | None,
    identity: dict[str, Any],
) -> str:
    if name == "artifact_identity":
        if identity.get("status") == "failed":
            return "failed"
        if identity.get("candidate_sha256") and candidate is not None and candidate.exists():
            return "pass"
        report = _read_json(report_path) if report_path else {}
        return _normalize_status(report.get("status", "todo"))
    if report_path is None:
        return "todo"
    report = _read_json(report_path)
    if name == "template_inheritance" and "status" not in report:
        return "failed"
    return _normalize_status(report.get("status", "failed"))


def _find_gate_report(harness: Path, name: str, *, render_dir: Path | None) -> Path | None:
    for report_name in REPORT_BY_GATE.get(name, ()):
        if report_name == "render_smoke/report.json":
            candidates = []
            if render_dir is not None:
                candidates.append(render_dir / "report.json")
            candidates.append(harness.parent / "render_smoke" / "report.json")
            candidates.append(harness / "render_smoke" / "report.json")
        elif name == "template_inheritance":
            candidates = _template_inheritance_candidates(harness, report_name)
        else:
            candidates = [harness / report_name]
        for path in candidates:
            if path.exists() and path.is_file():
                return path
    return None


def _overall_status(gates: list[dict[str, Any]]) -> str:
    required = [gate for gate in gates if gate["required"]]
    optional = [gate for gate in gates if not gate["required"]]
    if any(gate["status"] == "failed" for gate in gates):
        return "failed"
    if any(gate["status"] in {"needs_review", "todo"} for gate in required):
        return "needs_review"
    if any(gate["status"] == "needs_review" for gate in optional):
        return "needs_review"
    return "pass"


def _current_phase(gates: list[dict[str, Any]]) -> str:
    for gate in gates:
        if gate["status"] in {"failed", "needs_review", "todo"}:
            return str(gate["phase"])
    return str(gates[-1]["phase"]) if gates else "P0"


def _build_failure_queue(
    harness: Path,
    *,
    render_dir: Path | None,
    gates: list[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    gate_order = {gate["name"]: index for index, gate in enumerate(gates)}
    raw: list[dict[str, Any]] = []
    for report_name, gate in FAILURE_REPORTS.items():
        path = _failure_report_path(harness, report_name, render_dir=render_dir)
        if path is None:
            continue
        report = _read_json(path)
        raw.extend(_report_failures(gate, path, report))

    raw.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], gate_order.get(item["gate"], 99), item["reason"]))
    failures: list[dict[str, Any]] = []
    for index, failure in enumerate(raw, start=1):
        failures.append({"id": f"H-{index:03d}", **failure})
    return {
        "artifact_sha256": identity.get("candidate_sha256"),
        "source_candidate_path": identity.get("source_candidate_path"),
        "bad_fixture_path": identity.get("bad_fixture_path"),
        "candidate_sha256": identity.get("candidate_sha256"),
        "candidate_size": identity.get("candidate_size"),
        "commit": identity.get("commit"),
        "failures": failures,
    }


def _failure_report_path(harness: Path, report_name: str, *, render_dir: Path | None) -> Path | None:
    if report_name == "render_smoke/report.json":
        candidates = []
        if render_dir is not None:
            candidates.append(render_dir / "report.json")
        candidates.extend([harness.parent / "render_smoke" / "report.json", harness / "render_smoke" / "report.json"])
    elif report_name == "template_inheritance_report.json":
        candidates = _template_inheritance_candidates(harness, report_name)
    else:
        candidates = [harness / report_name]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _template_inheritance_candidates(harness: Path, report_name: str) -> list[Path]:
    candidates = [harness / report_name]
    if harness.name == "harness":
        candidates.append(harness.parent / report_name)
    return candidates


def _report_failures(gate: str, path: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    failures = report.get("failures")
    if isinstance(failures, list) and failures:
        return [_format_failure(gate, path, item if isinstance(item, dict) else {"id": str(item)}) for item in failures]
    if report.get("status") == "failed":
        synthesized = _synthesize_report_failure(gate, report)
        return [_format_failure(gate, path, synthesized)]
    return []


def _synthesize_report_failure(gate: str, report: dict[str, Any]) -> dict[str, Any]:
    if gate == "template_inheritance":
        for key in (
            "styles_xml_changed",
            "numbering_xml_changed",
            "header_footer_changed",
            "toc_field_exists",
            "page_number_fields_exist",
            "header_footer_as_body_text",
            "body_contains_header_text",
        ):
            value = report.get(key)
            if value is True or (key in {"toc_field_exists", "page_number_fields_exist"} and value is False):
                return {"id": key, "region": "template", "evidence_text": f"{key}={value}"}
        return {"id": "template_inheritance_failed", "region": "template"}
    if gate == "artifact_identity":
        return {
            "id": "artifact_identity_mismatch",
            "region": "artifact",
            "evidence_text": str(report.get("evidence_text") or report.get("message") or "candidate SHA/size does not match report identity"),
        }
    return {"id": f"{gate}_failed", "region": "unknown"}


def _format_failure(gate: str, path: Path, failure: dict[str, Any]) -> dict[str, Any]:
    reason = str(failure.get("id") or failure.get("rule") or failure.get("reason") or "unknown_failure")
    region = str(failure.get("region") or _infer_region(reason, failure))
    severity = _severity(reason, gate)
    evidence = _evidence_text(failure) or f"{region}: {reason}"
    return {
        "gate": gate,
        "reason": reason,
        "severity": severity,
        "status": _normalize_status(failure.get("status", "failed")),
        "region": region,
        "evidence_text": evidence,
        "expected": _expected(reason, region),
        "suggested_fix": _suggested_fix(reason, gate),
        "can_fix_now": severity != "P5",
        "report": str(path),
    }


def _severity(reason: str, gate: str) -> str:
    p0_markers = (
        "artifact_identity",
        "template_instructions_or_sample_leak",
        "spine_template_instruction_leak",
        "taskbook_template_note_leak",
        "debug_forbidden",
        "wrong_template",
        "template_sample",
        "body_contains_template_page_number_48",
        "body_template_page_residue",
        "toc_template_sample_leak",
    )
    p1_markers = (
        "metadata_mismatch",
        "missing_required",
        "cover_classification_split",
        "cover_metadata_misaligned",
        "cover_metadata_anchor_misaligned",
        "cover_title_orphan_or_bad_wrap",
        "cover_thesis_type_and_title_merged",
        "cover_title_layout_bad",
        "cover_bottom_fields_missing_values",
        "cover_date_merged_into_advisor",
        "cover_wordmark_missing",
        "frontmatter_blank_or_placeholder_fields",
        "taskbook_blank_or_placeholder_fields",
        "abstract_region_issue",
        "cn_abstract_contains_english",
    )
    if any(marker in reason for marker in p0_markers):
        return "P0"
    if any(marker in reason for marker in p1_markers):
        return "P1"
    if gate == "template_inheritance" or "template_inheritance" in reason:
        return "P2"
    if gate == "render_smoke":
        return "P3"
    if "semantic" in reason or "completeness" in reason:
        return "P5"
    return "P4"


def _infer_region(reason: str, failure: dict[str, Any]) -> str:
    if "field" in failure:
        return str(failure["field"])
    for marker, region in (
        ("spine", "spine"),
        ("taskbook", "task_book"),
        ("task_book", "task_book"),
        ("declaration", "declaration"),
        ("abstract_cn", "abstract_cn"),
        ("cn_abstract", "abstract_cn"),
        ("abstract_en", "abstract_en"),
        ("toc", "toc"),
        ("cover", "cover"),
        ("body", "body"),
        ("template", "template"),
        ("figure", "figures_equations"),
        ("equation", "figures_equations"),
    ):
        if marker in reason:
            return region
    return "unknown"


def _evidence_text(failure: dict[str, Any]) -> str:
    for key in ("evidence_text", "detail", "message", "token", "text", "actual"):
        value = failure.get(key)
        if value:
            return str(value)
    tokens = failure.get("tokens")
    if isinstance(tokens, list):
        return " / ".join(str(token) for token in tokens)
    missing = failure.get("missing")
    if isinstance(missing, list):
        return "missing: " + ", ".join(str(token) for token in missing)
    return ""


def _expected(reason: str, region: str) -> str:
    if "template_instructions_or_sample_leak" in reason:
        return "Final thesis text must not contain template instructions or sample values."
    if "cover_classification_split" in reason:
        return "The classification number must render as TP273, not split into spaced characters."
    if "cover_metadata_misaligned" in reason:
        return "Cover metadata fields should be aligned and populated in their official template positions."
    if "cover_metadata_anchor_misaligned" in reason:
        return "Cover unit code, student id, and classification should remain in the official fixed anchor positions."
    if "cover_title_orphan_or_bad_wrap" in reason:
        return "Cover title should wrap cleanly without orphan single-character lines or compressed title text."
    if "cover_wordmark_missing" in reason:
        return "The middle Beihang wordmark image from the official cover must be preserved."
    if "cover_thesis_type_and_title_merged" in reason:
        return "The thesis type text and Chinese title must be separate official cover blocks."
    if "cover_title_layout_bad" in reason:
        return "Chinese title should use the official cover title area with stable two-line layout."
    if "cover_bottom_fields_missing_values" in reason:
        return "Cover bottom fields should contain college, major, student name, advisor, and date in their underline regions."
    if "cover_date_merged_into_advisor" in reason:
        return "The date should be below the bottom field block, not inside the advisor field."
    if "declaration_contamination" in reason:
        return "Declaration signature/date area must not contain thesis title or other cover text."
    if "frontmatter_blank_or_placeholder_fields" in reason:
        return "Front matter required fields should be filled or intentionally preserved as official blanks, not malformed placeholders."
    if "taskbook_blank_or_placeholder_fields" in reason:
        return "Task book fields should be filled from the current thesis model or explicitly marked needs_review in truncated mode."
    if "abstract_render_smoke_failed" in reason:
        return "Chinese and English abstracts should be separated with correct titles and author/tutor fields."
    if "abstract_region_issue" in reason:
        return "Chinese abstract and English abstract must be separate regions without cross-language residue or official sample abstract text."
    if "toc_template_sample_leak" in reason:
        return "TOC must be generated from current body headings only and must not contain declaration entries or official sample references."
    if "body_template_page_residue" in reason:
        return "Body should start from page 1 and must not contain template page numbers, TOC residue, or sample body remnants."
    if "cn_abstract_contains_english" in reason:
        return "Chinese abstract must not contain English title/author/tutor labels."
    if "template_inheritance" in reason or region == "template":
        return "Final DOCX should inherit the official instrumented template in place."
    if "artifact_identity_mismatch" in reason:
        return "The report identity must match the exact candidate path, SHA256, and file size being validated."
    if "render_smoke" in reason:
        return "Rendered first pages should match page-level BUAA thesis structure."
    return f"{region} should satisfy the corresponding harness rule."


def _suggested_fix(reason: str, gate: str) -> str:
    if "template_instructions_or_sample_leak" in reason or "spine_template_instruction_leak" in reason:
        return "Remove leaked template instruction/sample text from the generated artifact; do not relax validators."
    if "taskbook_template_note_leak" in reason:
        return "Clean task book template notes from final output while preserving required task book structure."
    if "cover_classification_split" in reason:
        return "Fix the cover placeholder/value rendering so the classification value stays contiguous."
    if "cover_metadata_misaligned" in reason:
        return "Fix cover field placement using the official template anchors; do not loosen smoke checks."
    if "cover_metadata_anchor_misaligned" in reason:
        return "Instrument and fill the official cover anchors in place; do not rebuild metadata as flowing paragraphs."
    if "cover_title_orphan_or_bad_wrap" in reason:
        return "Fix cover title wrapping in the template fill path while preserving official cover structure."
    if "cover_wordmark_missing" in reason:
        return "Preserve the official cover wordmark image paragraph/anchor when creating cover-only debug artifacts."
    if "cover_thesis_type_and_title_merged" in reason:
        return "Keep the thesis type paragraph separate from TITLE_CN_LINE1 and TITLE_CN_LINE2."
    if "cover_title_layout_bad" in reason:
        return "Fill TITLE_CN_LINE1 and TITLE_CN_LINE2 into the official title anchors without changing cover layout."
    if "cover_bottom_fields_missing_values" in reason:
        return "Fill bottom cover fields into the existing official table/underline anchors."
    if "cover_date_merged_into_advisor" in reason:
        return "Fill DATE_YEAR_MONTH only into the date anchor, not the advisor field."
    if "declaration_contamination" in reason:
        return "Fix declaration field replacement so date text cannot absorb the thesis title."
    if "frontmatter_blank_or_placeholder_fields" in reason:
        return "Fix front-matter field mapping/filling for the affected official template regions."
    if "taskbook_blank_or_placeholder_fields" in reason:
        return "Fix task book field extraction and placement; in truncated mode report uncertain fields as needs_review, not blank placeholders."
    if "abstract_render_smoke_failed" in reason:
        return "Fix abstract region partition/rendering; keep CN and EN abstract fields separated."
    if "abstract_region_issue" in reason:
        return "Fix abstract extraction and region assignment so CN/EN abstract pages are isolated from each other and from template samples."
    if "toc_template_sample_leak" in reason:
        return "Regenerate TOC from the current body heading model and remove front-matter/template sample entries."
    if "body_template_page_residue" in reason:
        return "Fix body insertion boundaries so body page numbering/content starts cleanly after front matter without template residue."
    if "template_inheritance" in reason or gate == "template_inheritance":
        return "Generate by editing a copy of the official instrumented template, preserving styles, numbering, headers, footers, TOC, and page fields."
    if "artifact_identity_mismatch" in reason:
        return "Regenerate harness reports for the exact candidate path; do not reuse stale reports from another artifact."
    if gate == "render_smoke":
        return "Inspect the rendered page evidence and fix the first page-level layout/content mismatch only."
    return "Resolve the reported harness failure without relaxing validator rules."


def _report_index(harness: Path, *, render_dir: Path | None) -> dict[str, str]:
    index: dict[str, str] = {
        "status": str(harness / "status.json"),
        "gate_board": str(harness / "gate_board.json"),
        "failure_queue": str(harness / "failure_queue.json"),
    }
    for report_name, gate in FAILURE_REPORTS.items():
        path = _failure_report_path(harness, report_name, render_dir=render_dir)
        if path is not None:
            index[gate] = str(path)
    artifact_identity_path = harness / "artifact_identity.json"
    if artifact_identity_path.exists():
        index["artifact_identity"] = str(artifact_identity_path)
    return index


def _artifact_index(harness: Path, *, render_dir: Path | None, candidate: Path | None) -> dict[str, Any]:
    output_root = candidate.parent if candidate is not None and candidate.name == "thesis.docx" else harness.parent
    artifacts: dict[str, Any] = {
        "docx": str(candidate) if candidate is not None else str(output_root / "thesis.docx"),
        "pdf": str(output_root / "thesis.pdf"),
        "tex": str(output_root / "thesis.tex"),
    }
    if render_dir is not None and render_dir.exists():
        artifacts["page_images"] = [str(path) for path in sorted(render_dir.glob("page_*.png"))]
    else:
        artifacts["page_images"] = []
    return artifacts


def _write_progress_md(path: Path, gate_board: dict[str, Any], failure_queue: dict[str, Any], packet: dict[str, Any]) -> None:
    failures = failure_queue.get("failures", [])
    next_failure = failures[0] if failures else None
    lines = [
        "# Harness Progress",
        "",
        "## Artifact",
        f"- candidate: {gate_board.get('candidate_path')}",
        f"- sha256: {gate_board.get('candidate_sha256')}",
        f"- commit: {gate_board.get('commit')}",
        f"- sample_mode: {gate_board.get('sample_mode')}",
        "",
        "## Gate Board",
        "| Phase | Gate | Status | Report |",
        "|---|---|---|---|",
    ]
    for gate in gate_board.get("gates", []):
        lines.append(
            f"| {gate['phase']} | {gate['id']} {gate['name']} | {str(gate['status']).upper()} | {gate.get('report') or ''} |"
        )
    lines.extend(["", "## Next Failure To Fix"])
    if next_failure:
        lines.append(f"{next_failure['id']} {next_failure['reason']}")
        lines.append(f"- command: /fix {next_failure['id']}")
        lines.append(f"- evidence: /evidence {next_failure['id']}")
    else:
        lines.append("None")
    lines.extend(["", "## Remaining Failures"])
    if failures:
        for failure in failures:
            lines.append(
                f"- {failure['id']} {failure['severity']} {failure['gate']} {failure['region']}: {failure['reason']}"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Evidence Packet",
            f"- status.json: {packet['reports'].get('status')}",
            f"- gate_board.json: {packet['reports'].get('gate_board')}",
            f"- failure_queue.json: {packet['reports'].get('failure_queue')}",
            f"- render_smoke/report.json: {packet['reports'].get('render_smoke')}",
            f"- docx: {packet['artifacts'].get('docx')}",
            f"- pdf: {packet['artifacts'].get('pdf')}",
            f"- screenshots: {len(packet['artifacts'].get('page_images', []))}",
            "",
            "## Do Not Fix Yet",
            "- semantic_completeness",
            "- figures_equations",
            "- full chapter completeness for truncated fixtures",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _ensure_status_json(harness: Path, gate_board: dict[str, Any]) -> None:
    status_path = harness / "status.json"
    failed_gate = next((gate["name"] for gate in gate_board["gates"] if gate["status"] == "failed"), None)
    identity_fields = {
        "candidate_path": gate_board.get("candidate_path"),
        "candidate_sha256": gate_board.get("candidate_sha256"),
        "candidate_size": gate_board.get("candidate_size"),
        "source_candidate_path": gate_board.get("source_candidate_path"),
        "bad_fixture_path": gate_board.get("bad_fixture_path"),
        "commit": gate_board.get("commit"),
    }
    if status_path.exists():
        status = _read_json(status_path)
        status.update({key: value for key, value in identity_fields.items() if value is not None})
        existing_failed_stage = status.get("failed_stage")
        existing_status = _normalize_status(status.get("status", "todo"))
        status["status"] = gate_board["overall_status"]
        status["failed_stage"] = existing_failed_stage if existing_status == "failed" and existing_failed_stage else failed_gate
        _write_json(status_path, status)
        return
    status = {
        "status": gate_board["overall_status"],
        "failed_stage": failed_gate,
        "stages": [
            {"stage": gate["name"], "status": gate["status"], "report": gate.get("report")}
            for gate in gate_board["gates"]
            if gate.get("report")
        ],
        **identity_fields,
    }
    _write_json(status_path, status)


def _load_or_create_identity(
    harness: Path,
    candidate: Path | None,
    model: Path | None,
    template: Path | None,
) -> dict[str, Any]:
    identity_path = harness / "artifact_identity.json"
    if identity_path.exists():
        identity = _read_json(identity_path)
        if identity:
            identity = _validate_existing_identity(identity, candidate, model, template)
            _write_json(identity_path, identity)
            return identity
    if candidate is None or not candidate.exists():
        return {}
    identity = artifact_identity(candidate_path=candidate, source_model_path=model, template_path=template)
    _write_json(identity_path, identity)
    return identity


def _validate_existing_identity(
    identity: dict[str, Any],
    candidate: Path | None,
    model: Path | None,
    template: Path | None,
) -> dict[str, Any]:
    if candidate is None or not candidate.exists() or not candidate.is_file():
        return identity
    current = artifact_identity(candidate_path=candidate, source_model_path=model, template_path=template)
    expected_sha = identity.get("candidate_sha256")
    expected_size = identity.get("candidate_size")
    mismatch = expected_sha != current["candidate_sha256"] or expected_size != current["candidate_size"]
    merged = {**identity, **current}
    if identity.get("source_candidate_path"):
        merged["source_candidate_path"] = identity["source_candidate_path"]
    if identity.get("bad_fixture_path"):
        merged["bad_fixture_path"] = identity["bad_fixture_path"]
    if identity.get("commit"):
        merged["commit"] = identity["commit"]
    if mismatch:
        merged["status"] = "failed"
        merged["reported_candidate_sha256"] = expected_sha
        merged["reported_candidate_size"] = expected_size
        merged["failures"] = [
            {
                "id": "artifact_identity_mismatch",
                "region": "artifact",
                "evidence_text": (
                    f"reported_sha={expected_sha}; actual_sha={current['candidate_sha256']}; "
                    f"reported_size={expected_size}; actual_size={current['candidate_size']}"
                ),
            }
        ]
    else:
        merged.setdefault("status", "pass")
        merged.setdefault("failures", [])
    return merged


def _resolve_candidate_path(harness: Path, explicit: Path | None) -> Path | None:
    explicit_path = _resolve_existing_path(explicit)
    if explicit_path is not None:
        return explicit_path
    for report_name in ("artifact_identity.json", "status.json", "output_text_report.json", "output_text_post_finalize_report.json"):
        report = _read_json(harness / report_name)
        for key in ("candidate_path", "candidate"):
            value = report.get(key)
            if value:
                candidate = Path(str(value))
                if candidate.exists():
                    return candidate
    candidate = harness.parent / "thesis.docx"
    if candidate.exists():
        return candidate
    return None


def _resolve_render_smoke_dir(harness: Path, explicit: Path | None) -> Path | None:
    explicit_path = _resolve_existing_dir(explicit)
    if explicit_path is not None:
        return explicit_path
    render_candidates = (
        (harness / "render_smoke", harness.parent / "render_smoke", harness.parent.parent / "render_smoke")
        if harness.name != "harness"
        else (harness.parent / "render_smoke", harness / "render_smoke", harness.parent.parent / "render_smoke")
    )
    for candidate in render_candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _resolve_existing_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    return candidate if candidate.exists() and candidate.is_file() else None


def _resolve_existing_dir(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    return candidate if candidate.exists() and candidate.is_dir() else None


def _optional_sha(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return sha256_file(path)


def _normalize_status(value: Any) -> str:
    status = str(value or "todo").strip().lower().replace("-", "_").replace(" ", "_")
    if status == "fail":
        status = "failed"
    return status if status in STATUS_VALUES else "failed"


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else "unknown"


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = ["load_progress", "write_progress_artifacts"]
