from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .metadata_extract import REQUIRED_UNDERGRADUATE_METADATA, RECOMMENDED_METADATA


GATES = {
    "E00": "source_identity",
    "E01": "text_extraction",
    "E02": "metadata_extraction",
    "E03": "abstract_extraction",
    "E04": "body_structure_extraction",
    "E05": "figure_extraction",
    "E06": "equation_extraction",
    "E07": "reference_extraction",
    "E08": "chunk_traceability",
    "E09": "forbidden_content_check",
}

FORBIDDEN_MODEL_TOKENS = (
    "MERGEFORMAT",
    "[Figure inserted]",
    "[Figure requires review]",
    "D:\\",
    ".worktrees",
    "output_work_",
    "公式章",
    "下一章",
)
BODY_FORBIDDEN_TOKENS = (
    "目录",
    "本人声明",
    "北京航空航天大学毕业设计(论文)",
    "北京航空航天大学毕业设计（论文）",
    "单位代码",
    "学号",
    "分类号",
)
CN_ABSTRACT_FORBIDDEN = ("Research on", "Author:", "Tutor:", "Abstract", "Key Words")
EN_ABSTRACT_FORBIDDEN = ("摘 要", "关键词：")
REFERENCE_SAMPLE_FORBIDDEN = ("Mao Xia", "刘国钧", "沧水电迁移")


def validate_extraction_model(
    model: dict[str, Any],
    *,
    source_path: str | Path,
    out_dir: str | Path,
    sample_mode: str = "full",
    allow_missing_metadata: bool = False,
) -> dict[str, Any]:
    source = Path(source_path).resolve(strict=False)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    context = _Context(model=model, source=source, sample_mode=sample_mode, allow_missing_metadata=allow_missing_metadata)

    reports = {
        "source_identity": _source_identity(context),
        "metadata": _metadata_report(context),
        "abstract": _abstract_report(context),
        "body_structure": _body_structure_report(context),
        "figure": _figure_report(context),
        "equation": _equation_report(context),
        "reference": _reference_report(context),
        "chunk_trace": _chunk_trace_report(context),
        "forbidden": _forbidden_report(context),
    }

    gate_board = _gate_board(context)
    result = {
        "status": _overall_status(gate_board),
        "gate_board": gate_board,
        "failure_queue": context.failures,
        "reports": reports,
    }
    _write_reports(out, result, reports)
    return result


class _Context:
    def __init__(self, *, model: dict[str, Any], source: Path, sample_mode: str, allow_missing_metadata: bool) -> None:
        self.model = model
        self.source = source
        self.sample_mode = sample_mode
        self.allow_missing_metadata = allow_missing_metadata
        self.statuses = {gate: "pass" for gate in GATES}
        self.failures: list[dict[str, Any]] = []

    def add(self, gate: str, status: str, reason: str, evidence: str, suggested_fix: str, field: str = "") -> None:
        self.statuses[gate] = _worse_status(self.statuses[gate], status)
        ordinal = sum(1 for item in self.failures if item["gate"] == gate) + 1
        item = {
            "id": f"H-{gate}-{ordinal:03d}",
            "gate": gate,
            "reason": reason,
            "field": field,
            "evidence": evidence,
            "suggested_fix": suggested_fix,
        }
        self.failures.append(item)


def _source_identity(context: _Context) -> dict[str, Any]:
    source = context.source
    if not source.exists():
        context.add("E00", "failed", "source_missing", str(source), "Pass an existing DOCX/PDF source path.")
        return {"source_path": str(source), "exists": False}
    return {
        "source_path": str(source),
        "exists": True,
        "size": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _metadata_report(context: _Context) -> dict[str, Any]:
    metadata = dict(context.model.get("metadata") or {})
    evidence = dict(metadata.get("evidence") or {})
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    conflicts = list(metadata.get("conflicts") or [])

    for field in [*REQUIRED_UNDERGRADUATE_METADATA, *RECOMMENDED_METADATA]:
        value = str(metadata.get(field) or "").strip()
        field_evidence = evidence.get(field) if isinstance(evidence.get(field), dict) else {}
        if not value:
            missing.append(field)
            if field in REQUIRED_UNDERGRADUATE_METADATA:
                status = "needs_review" if context.allow_missing_metadata else "failed"
                context.add("E02", status, "missing_required_metadata", field, "Improve metadata extraction or pass --allow-missing-metadata.", field)
            else:
                context.add("E02", "needs_review", "missing_recommended_metadata", field, "Improve metadata extraction.", field)
            continue
        confidence = _confidence(field_evidence)
        evidence_text = str(
            field_evidence.get("evidence_text")
            or field_evidence.get("evidence")
            or field_evidence.get("method")
            or ""
        )
        if not field_evidence:
            context.add("E02", "failed", "metadata_without_evidence", value, "Attach extraction evidence to every metadata value.", field)
        elif confidence < 0.75:
            context.add("E02", "needs_review", "low_confidence_metadata", f"{field}={value} confidence={confidence}", "Improve candidate scoring or add a stronger source.", field)
        resolved[field] = {
            "value": value,
            "confidence": confidence,
            "source_page": field_evidence.get("page_hint") or field_evidence.get("source_page") or 1,
            "source_region": _source_region(field_evidence),
            "evidence": evidence_text,
            "rule": field_evidence.get("method") or field_evidence.get("rule") or "unknown",
        }
    for conflict in conflicts:
        context.add("E02", "needs_review", "metadata_conflict", json.dumps(conflict, ensure_ascii=False), "Resolve conflicting high-confidence candidates.")
    return {"resolved": resolved, "missing": missing, "conflicts": conflicts, "warnings": []}


def _abstract_report(context: _Context) -> dict[str, Any]:
    cn = dict(context.model.get("abstract_cn") or {})
    en = dict(context.model.get("abstract_en") or {})
    warnings: list[str] = []
    cn_body = str(cn.get("body") or "")
    en_body = str(en.get("body") or "")
    cn_keywords = cn.get("keywords") or []
    en_keywords = en.get("keywords") or []
    if not cn_body:
        context.add("E03", "failed", "missing_abstract_cn", "", "Improve Chinese abstract extraction.")
    if not cn_keywords:
        context.add("E03", "needs_review", "missing_keywords_cn", "", "Extract Chinese keywords.")
    if not en_body:
        status = "needs_review" if context.sample_mode == "truncated" else "failed"
        context.add("E03", status, "missing_abstract_en", "", "Extract English abstract.")
    if not en_keywords:
        status = "needs_review" if context.sample_mode == "truncated" else "failed"
        context.add("E03", status, "missing_keywords_en", "", "Extract English keywords.")
    for token in CN_ABSTRACT_FORBIDDEN:
        if token in cn_body or any(token in str(item) for item in cn_keywords):
            context.add("E03", "failed", "cn_abstract_contamination", token, "Separate Chinese and English abstract regions.")
    for token in EN_ABSTRACT_FORBIDDEN:
        if token in en_body or any(token in str(item) for item in en_keywords):
            context.add("E03", "failed", "en_abstract_contamination", token, "Separate English abstract from Chinese residue.")
    return {"cn_exists": bool(cn_body), "en_exists": bool(en_body), "warnings": warnings}


def _body_structure_report(context: _Context) -> dict[str, Any]:
    body = list(context.model.get("body") or [])
    has_heading = any(str(item.get("type") or "") in {"chapter", "section", "subsection"} for item in body if isinstance(item, dict))
    if body and not has_heading:
        context.add("E04", "needs_review", "missing_body_heading", "body has text but no heading", "Improve heading classification.")
    if not body:
        context.add("E04", "needs_review", "missing_body", "", "Extract body blocks.")
    seen_chapter = False
    first_heading = ""
    for index, item in enumerate(body):
        item_type = str(item.get("type") or "") if isinstance(item, dict) else ""
        if item_type in {"chapter", "section", "subsection"} and not first_heading:
            first_heading = item_type
        if item_type == "chapter":
            seen_chapter = True
        elif item_type in {"section", "subsection"} and not seen_chapter:
            context.add(
                "E04",
                "failed",
                "body_section_before_chapter",
                f"body[{index}] {item_type} {_block_text(item)[:80]}",
                "Filter source TOC/front matter and ensure body starts with chapter 1 before sections.",
            )
        text = _block_text(item)
        if _looks_like_source_toc_line(text):
            context.add(
                "E04",
                "failed",
                "source_toc_leak",
                text[:120],
                "Keep extracted source TOC only in debug/source_toc.json; do not render it as body.",
            )
        for token in BODY_FORBIDDEN_TOKENS:
            if token and token in text:
                context.add("E04", "failed", "body_forbidden_content", token, "Remove front matter/header/footer residue from body.")
    if first_heading and first_heading != "chapter":
        context.add(
            "E04",
            "failed",
            "body_first_heading_not_chapter",
            first_heading,
            "Classify or filter blocks so the first body heading is chapter 1.",
        )
    return {"block_count": len(body), "has_heading": has_heading, "first_heading": first_heading}


def _figure_report(context: _Context) -> dict[str, Any]:
    figures = list(context.model.get("figures") or [])
    missing_assets = []
    for figure in figures:
        path = str(figure.get("path") or figure.get("asset_path") or "")
        if path and not Path(path).exists():
            missing_assets.append(path)
            context.add("E05", "needs_review", "missing_figure_asset", path, "Extract or replace the figure asset with a review placeholder.")
    return {"figures": len(figures), "missing_assets": missing_assets}


def _equation_report(context: _Context) -> dict[str, Any]:
    equations = list(context.model.get("equations") or [])
    body_equations = [item for item in context.model.get("body") or [] if isinstance(item, dict) and item.get("type") == "equation_placeholder"]
    review_equations = list(context.model.get("equations_need_review") or [])
    body_equation_text = json.dumps(body_equations, ensure_ascii=False)
    bad_tokens = [token for token in FORBIDDEN_MODEL_TOKENS if token in body_equation_text]
    bad_tokens.extend(sorted(set(re.findall(r"oleObject\d*\.bin", body_equation_text, flags=re.IGNORECASE))))
    for token in bad_tokens:
        context.add("E06", "failed", "raw_equation_residue", token, "Convert unsupported equations to clean placeholders.")
    return {
        "equations": len(equations) + len(body_equations) + len(review_equations),
        "body_equation_placeholders": len(body_equations),
        "equations_need_review": len(review_equations),
        "raw_residue": bad_tokens,
    }


def _reference_report(context: _Context) -> dict[str, Any]:
    references = list(context.model.get("references") or [])
    for item in references:
        text = _block_text(item)
        for token in REFERENCE_SAMPLE_FORBIDDEN:
            if token in text:
                context.add("E07", "failed", "template_reference_leak", token, "Remove official template sample references.")
        if isinstance(item, dict) and not item.get("source_trace"):
            context.add("E07", "needs_review", "reference_missing_trace", text[:80], "Attach source trace to reference entries.")
    if not references and context.sample_mode != "truncated":
        context.add("E07", "needs_review", "missing_references", "", "Extract reference section.")
    return {"references": len(references)}


def _chunk_trace_report(context: _Context) -> dict[str, Any]:
    missing = []
    for collection_name in ("body", "references"):
        for index, item in enumerate(context.model.get(collection_name) or []):
            if isinstance(item, dict) and not item.get("source_trace"):
                missing.append({"collection": collection_name, "index": index})
                context.add("E08", "needs_review", "missing_source_trace", f"{collection_name}[{index}]", "Attach source_trace to every extracted block.")
    return {"missing_trace": missing, "missing_count": len(missing)}


def _forbidden_report(context: _Context) -> dict[str, Any]:
    content_model = {
        key: value for key, value in context.model.items() if key != "source"
    }
    text = json.dumps(content_model, ensure_ascii=False)
    found = []
    for token in FORBIDDEN_MODEL_TOKENS:
        if token in text:
            found.append(token)
            context.add("E09", "failed", "forbidden_content", token, "Remove debug/path/field-code residue before rendering.")
    return {"tokens": found}


def _gate_board(context: _Context) -> dict[str, dict[str, str]]:
    if any(context.model.get(key) for key in ("metadata", "abstract_cn", "abstract_en", "body", "references")):
        context.statuses["E01"] = _worse_status(context.statuses["E01"], "pass")
    else:
        context.add("E01", "failed", "no_extracted_text", "", "Extractor produced no model content.")
    return {gate: {"name": GATES[gate], "status": context.statuses[gate]} for gate in GATES}


def _write_reports(out: Path, result: dict[str, Any], reports: dict[str, Any]) -> None:
    files = {
        "extraction_gate_board.json": result["gate_board"],
        "extraction_failure_queue.json": result["failure_queue"],
        "extraction_report.json": {"status": result["status"], "failure_count": len(result["failure_queue"])},
        "source_identity_report.json": reports["source_identity"],
        "metadata_report.json": reports["metadata"],
        "abstract_report.json": reports["abstract"],
        "body_structure_report.json": reports["body_structure"],
        "figure_report.json": reports["figure"],
        "equation_report.json": reports["equation"],
        "reference_report.json": reports["reference"],
        "chunk_trace_report.json": reports["chunk_trace"],
    }
    for filename, payload in files.items():
        (out / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _overall_status(gate_board: dict[str, dict[str, str]]) -> str:
    statuses = [item["status"] for item in gate_board.values()]
    if "failed" in statuses:
        return "failed"
    if "needs_review" in statuses:
        return "needs_review"
    return "pass"


def _worse_status(left: str, right: str) -> str:
    order = {"pass": 0, "needs_review": 1, "failed": 2}
    return left if order[left] >= order[right] else right


def _confidence(evidence: dict[str, Any]) -> float:
    try:
        return float(evidence.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _source_region(evidence: dict[str, Any]) -> str:
    explicit = str(evidence.get("source_region") or "")
    if explicit:
        return explicit
    method = str(evidence.get("method") or evidence.get("rule") or "")
    for region in ("cover", "task_book", "abstract_cn", "declaration", "doc_props", "body"):
        if region in method:
            return region
    if method.startswith("metadata"):
        return "cover"
    return "unknown"


def _block_text(item: Any) -> str:
    if isinstance(item, dict):
        return " ".join(str(item.get(key) or "") for key in ("title", "text", "raw", "source_text", "caption"))
    return str(item or "")


def _looks_like_source_toc_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return False
    if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d{1,3}$", value):
        return True
    if re.match(r"^\d+(?:\.\d+)+\s+\S.{0,100}\s+\d{1,3}$", value):
        return True
    return bool(re.match(r"^第[一二三四五六七八九十百零〇两]+章\s+\S.{0,100}\s+\d{1,3}$", value))
