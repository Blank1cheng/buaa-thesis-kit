from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from buaa_thesis_kit.docx_extract import extract_thesis_model
from buaa_thesis_kit.equations.native_pipeline import run_equation_items
from buaa_thesis_kit.extract.chunking import chunk_document, chunk_ranges_to_dict, parse_ranges
from buaa_thesis_kit.extract.equation_extract import equation_review_items
from buaa_thesis_kit.extract.figure_extract import (
    bind_figures_to_captions,
    figure_candidates,
    figure_number,
    is_figure_caption,
    strip_caption_number,
)
from buaa_thesis_kit.extract.harness import validate_extraction_model
from buaa_thesis_kit.extract.metadata_normalize import normalized_metadata_values
from buaa_thesis_kit.extract.reference_extract import normalize_reference_items
from buaa_thesis_kit.pdf_extract import extract_pdf_model

from .assets import CONVERTIBLE_PREVIEW_EXTENSIONS, SUPPORTED_LATEX_IMAGE_EXTENSIONS, stage_latex_image_asset
from .equation_review import apply_agent_equation_reviews
from .layout_validate import validate_layout
from .render_buaa import render_buaa_latex
from .template_manager import normalize_degree_type


def run_latex_pipeline(
    source: str | Path,
    *,
    template_path: str | Path,
    degree_type: str,
    out_dir: str | Path,
    compile_pdf: bool = True,
    sample_mode: str = "full",
    ranges: str | None = None,
    allow_extraction_fail: bool = False,
    allow_missing_metadata: bool = False,
    equation_review_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(source).resolve(strict=True)
    out_dir = Path(out_dir)
    degree = normalize_degree_type(degree_type)
    source_identity = _pipeline_source_identity(source)
    _prepare_out_dir(out_dir)
    work_extract = Path(tempfile.mkdtemp(prefix="latex_extract_", dir=str(out_dir.parent.resolve(strict=False))))
    try:
        chunk_report = None
        parsed_ranges = parse_ranges(ranges)
        if parsed_ranges:
            chunk_report = chunk_document(source, parsed_ranges, out_dir / "chunks")
        thesis_model = _extract_source(source, work_extract)
        source_model = thesis_model.to_dict()
        equation_native_report = run_equation_items(
            list(source_model.get("equations") or []),
            out_dir / "equation_native",
            model_root=work_extract,
        )
        equation_review_audit = None
        if equation_review_path is not None:
            equation_native_report, equation_review_audit = apply_agent_equation_reviews(
                equation_native_report,
                equation_review_path,
                source,
                out_dir / "equation_native",
            )
            (out_dir / "equation_native" / "report.json").write_text(
                json.dumps(equation_native_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (out_dir / "equation_native" / "failure_queue.json").write_text(
                json.dumps(equation_native_report.get("failure_queue") or [], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (out_dir / "equation_native" / "agent_review_audit.json").write_text(
                json.dumps(equation_review_audit, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        source_model = _apply_native_equation_results(source_model, equation_native_report)
        latex_model = _latex_model_from_thesis_model(source_model, degree)
        latex_model["source"] = source_identity
        latex_model.setdefault("debug", {})["equation_native"] = _equation_native_summary(
            equation_native_report,
            out_dir,
        )
        if equation_review_audit is not None:
            latex_model["debug"]["agent_equation_review"] = equation_review_audit
        if chunk_report:
            latex_model["chunks"] = chunk_report
            latex_model["chunk_ranges"] = chunk_ranges_to_dict(parsed_ranges)
        _stage_latex_assets(latex_model, out_dir)
        _write_model(out_dir, latex_model)
        extraction_result = validate_extraction_model(
            latex_model,
            source_path=source,
            out_dir=out_dir / "harness",
            sample_mode=sample_mode,
            allow_missing_metadata=allow_missing_metadata,
        )
        _write_debug(out_dir, thesis_model.to_dict(), latex_model)
        if extraction_result["status"] == "failed" and not allow_extraction_fail:
            report = {
                "status": "failed",
                "blocked_by_extraction": True,
                "input": str(source),
                "source_identity": source_identity,
                "degree_type": degree,
                "compile_status": {"status": "skipped_extraction_failed"},
                "extraction_status": extraction_result["status"],
                "equation_native": _equation_native_summary(equation_native_report, out_dir),
                "equation_review": equation_review_audit,
                "harness": {
                    "extraction_gate_board": str(out_dir / "harness" / "extraction_gate_board.json"),
                    "extraction_failure_queue": str(out_dir / "harness" / "extraction_failure_queue.json"),
                    "metadata_report": str(out_dir / "harness" / "metadata_report.json"),
                },
                "debug": _debug_paths(out_dir),
            }
            (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return report
        report = render_buaa_latex(
            latex_model,
            template_path=template_path,
            degree_type=degree,
            out_dir=out_dir,
            compile_pdf=compile_pdf,
        )
        latex_gate_result = _write_latex_gate_reports(out_dir, latex_model, report, extraction_result)
        report["input"] = str(source)
        report["source_identity"] = source_identity
        compile_pipeline_status = {
            "success": "pass",
            "skipped": "needs_review",
        }.get(str(report.get("compile_status", {}).get("status") or ""), "failed")
        report["status"] = _merge_status(
            _merge_status(compile_pipeline_status, extraction_result["status"]),
            latex_gate_result["status"],
        )
        report["blocked_by_extraction"] = False
        report["extraction_status"] = extraction_result["status"]
        report["equation_native"] = _equation_native_summary(equation_native_report, out_dir)
        report["equation_review"] = equation_review_audit
        report["harness"] = {
            "extraction_gate_board": str(out_dir / "harness" / "extraction_gate_board.json"),
            "extraction_failure_queue": str(out_dir / "harness" / "extraction_failure_queue.json"),
            "metadata_report": str(out_dir / "harness" / "metadata_report.json"),
            "gate_board": str(out_dir / "harness" / "gate_board.json"),
            "failure_queue": str(out_dir / "harness" / "failure_queue.json"),
        }
        report["debug"] = _debug_paths(out_dir)
        (out_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report
    finally:
        shutil.rmtree(work_extract, ignore_errors=True)


def _extract_source(source: Path, work_dir: Path):
    suffix = source.suffix.lower()
    if suffix == ".docx":
        return extract_thesis_model(source, work_dir)
    if suffix == ".pdf":
        return extract_pdf_model(source, work_dir)
    raise ValueError(f"Unsupported input for LaTeX pipeline: {source}")


def _latex_model_from_thesis_model(model: dict[str, Any], degree: str) -> dict[str, Any]:
    front = dict(model.get("front_matter") or {})
    metadata = _metadata_with_fallbacks(normalized_metadata_values(dict(model.get("metadata") or {})), front)
    equation_blocks, equations_need_review = _equation_items_from_source(model.get("equations") or [], 0)
    equation_block_by_id = {str(item.get("id")): item for item in equation_blocks if item.get("id")}
    body, source_toc = _body_from_sections(model.get("sections") or [], equation_block_by_id)
    body, figure_debug = _inject_figure_blocks(body, model.get("figures") or [])
    used_equation_ids = _body_equation_ids(body)
    body.extend([item for item in equation_blocks if str(item.get("id")) not in used_equation_ids])
    references = _references_from_source(model.get("references") or [])
    acknowledgement = _acknowledgement(model.get("sections") or [])
    task_book = _task_book_defaults(model.get("task_book") or {}, metadata)
    back_matter = {
        "acknowledgement": acknowledgement,
        "references": references,
        "appendix": model.get("appendices") or [],
    }
    return {
        "degree_type": degree,
        "source_type": _model_source_type(model),
        "metadata": metadata,
        "task_book": task_book,
        "abstract_cn": {
            "body": front.get("chinese_abstract", ""),
            "keywords": _split_keywords(front.get("keywords_cn", "")),
        },
        "abstract_en": {
            "body": front.get("english_abstract", ""),
            "keywords": _split_keywords(front.get("keywords_en", "")),
            "author": metadata.get("author_en", ""),
            "tutor": metadata.get("tutor_en", ""),
        },
        "body": body,
        "back_matter": back_matter,
        "references": references,
        "acknowledgement": acknowledgement,
        "equations_need_review": equations_need_review,
        "debug": {
            "source_toc": source_toc,
            "heading_candidates": _heading_candidates(model.get("sections") or []),
            "task_book_blocks": task_book.get("blocks") or [],
            "references_taskbook": task_book.get("references") or [],
            "references_main": references,
            "figure_candidates": figure_debug["candidates"],
            "figure_captions": figure_debug["captions"],
            "figure_bindings": figure_debug["bindings"],
            "figure_needs_review": figure_debug["needs_review"],
            "render_mapping": _render_mapping(body),
        },
    }


def _model_source_type(model: dict[str, Any]) -> str:
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    evidence = metadata.get("evidence") if isinstance(metadata.get("evidence"), dict) else {}
    sources = [item for item in evidence.values() if isinstance(item, dict)]
    sources.extend(
        item.get("source")
        for item in model.get("sections") or []
        if isinstance(item, dict) and isinstance(item.get("source"), dict)
    )
    for source in sources:
        source_type = str(source.get("source_type") or "").lower()
        source_file = str(source.get("file") or source.get("source_file") or "").lower()
        if source_type in {"pdf", "docx"}:
            return source_type
        if source_file.endswith(".pdf"):
            return "pdf"
        if source_file.endswith(".docx"):
            return "docx"
    return "unknown"


def _references_from_source(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = normalize_reference_items(items)
    by_raw = [item for item in items if isinstance(item, dict)]
    references: list[dict[str, Any]] = []
    for index, item in enumerate(normalized):
        source = by_raw[index].get("source") if index < len(by_raw) else None
        references.append({"raw": item["raw"], "source_trace": _source_trace(source, "references", index)})
    return references


def _body_from_sections(
    sections: list[dict[str, Any]],
    equation_block_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    equation_block_by_id = equation_block_by_id or {}
    body: list[dict[str, Any]] = []
    for section in sections:
        section_type = str(section.get("type") or "").lower()
        if section_type in {"acknowledgement", "acknowledgements", "reference", "references"}:
            continue
        heading = _body_heading(section, len(body))
        body.append(heading)
        if section.get("text"):
            body.extend(_section_text_body_items(section, len(body), equation_block_by_id))
    return _drop_source_toc_prefix(body)


def _section_text_body_items(
    section: dict[str, Any],
    block_index: int,
    equation_block_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pending: list[str] = []
    for line in str(section.get("text") or "").splitlines():
        marker = _equation_marker_id(line)
        if marker:
            if pending:
                items.append(
                    {
                        "type": "paragraph",
                        "text": "\n".join(pending).strip(),
                        "source_trace": _source_trace(section.get("source"), "body", block_index + len(items)),
                    }
                )
                pending = []
            equation_block = equation_block_by_id.get(marker)
            if equation_block:
                item = dict(equation_block)
                item["source_trace"] = item.get("source_trace") or _source_trace(section.get("source"), "body", block_index + len(items))
                items.append(item)
            continue
        if _contains_equation_marker(line):
            if pending:
                items.append(
                    {
                        "type": "paragraph",
                        "text": "\n".join(pending).strip(),
                        "source_trace": _source_trace(section.get("source"), "body", block_index + len(items)),
                    }
                )
                pending = []
            mixed_item = _mixed_paragraph_item(line, equation_block_by_id)
            if mixed_item:
                mixed_item["source_trace"] = _source_trace(section.get("source"), "body", block_index + len(items))
                items.append(mixed_item)
            continue
        pending.append(line)
    if pending:
        items.append(
            {
                "type": "paragraph",
                "text": "\n".join(pending).strip(),
                "source_trace": _source_trace(section.get("source"), "body", block_index + len(items)),
            }
        )
    return items


def _equation_marker_id(line: str) -> str:
    match = re.fullmatch(r"\s*__BUAA_EQUATION_([A-Za-z0-9_.:-]+)__\s*", str(line or ""))
    return match.group(1) if match else ""


EQUATION_MARKER_RE = re.compile(r"__BUAA_EQUATION_([A-Za-z0-9_.:-]+)__")


def _contains_equation_marker(line: str) -> bool:
    return bool(EQUATION_MARKER_RE.search(str(line or "")))


def _mixed_paragraph_item(line: str, equation_block_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    segments: list[dict[str, Any]] = []
    cursor = 0
    for match in EQUATION_MARKER_RE.finditer(str(line or "")):
        if match.start() > cursor:
            segments.append({"type": "text", "text": line[cursor : match.start()]})
        equation_block = equation_block_by_id.get(match.group(1))
        if equation_block:
            segment = dict(equation_block)
            segment["inline"] = True
            segments.append(segment)
        cursor = match.end()
    if cursor < len(line):
        segments.append({"type": "text", "text": line[cursor:]})
    segments = [segment for segment in segments if segment.get("type") != "text" or str(segment.get("text") or "").strip()]
    if not segments:
        return None
    return {"type": "paragraph_mixed", "segments": segments}


def _body_equation_ids(body: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for item in body:
        if item.get("type") in {"equation", "equation_preview"} and item.get("id"):
            ids.add(str(item.get("id")))
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") in {"equation", "equation_preview"} and segment.get("id"):
                ids.add(str(segment.get("id")))
    return ids


def _inject_figure_blocks(body: list[dict[str, Any]], figures: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    captions = _body_figure_captions(body)
    bindings, needs_review = bind_figures_to_captions(figures, captions)
    binding_by_number = {str(item.get("number_hint") or ""): item for item in bindings if item.get("number_hint")}
    expanded: list[dict[str, Any]] = []
    for item in body:
        if item.get("type") != "paragraph":
            expanded.append(item)
            continue
        paragraph_lines = str(item.get("text") or "").splitlines()
        pending: list[str] = []
        for line in paragraph_lines:
            if is_figure_caption(line):
                if pending:
                    paragraph = dict(item)
                    paragraph["text"] = "\n".join(pending).strip()
                    expanded.append(paragraph)
                    pending = []
                number = figure_number(line)
                binding = binding_by_number.get(number)
                if binding:
                    figure_block = dict(binding)
                    if item.get("source_trace"):
                        figure_block["source_trace"] = item.get("source_trace")
                    expanded.append(figure_block)
                else:
                    expanded.append(
                        {
                            "type": "figure",
                            "caption": strip_caption_number(line),
                            "number_hint": number,
                            "missing_asset": True,
                            "needs_review": True,
                            "source_trace": item.get("source_trace"),
                        }
                    )
                continue
            pending.append(line)
        if pending:
            paragraph = dict(item)
            paragraph["text"] = "\n".join(pending).strip()
            expanded.append(paragraph)
    return expanded, {
        "candidates": figure_candidates(figures),
        "captions": _figure_caption_records(captions),
        "bindings": bindings,
        "needs_review": needs_review,
    }


def _body_figure_captions(body: list[dict[str, Any]]) -> list[str]:
    captions: list[str] = []
    for item in body:
        if item.get("type") != "paragraph":
            continue
        for line in str(item.get("text") or "").splitlines():
            if is_figure_caption(line):
                captions.append(line)
    return captions


def _figure_caption_records(captions: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "number_hint": figure_number(caption),
            "caption": strip_caption_number(caption),
            "raw": caption,
        }
        for caption in captions
    ]


def _body_heading(section: dict[str, Any], block_index: int) -> dict[str, Any]:
    raw_title = str(section.get("title") or "")
    number = _heading_number(raw_title)
    return {
        "type": _body_type(section),
        "number": number,
        "title": _clean_heading_title(raw_title, number),
        "_source_title": raw_title,
        "source_trace": _source_trace(section.get("source"), "body", block_index),
    }


def _drop_source_toc_prefix(body: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    first_chapter = next((index for index, item in enumerate(body) if item.get("type") == "chapter"), None)
    if first_chapter is None:
        return [_body_contract_item(item) for item in _insert_missing_chapter_anchors(body)], []
    if first_chapter == 0:
        return [_body_contract_item(item) for item in _insert_missing_chapter_anchors(body)], []
    return (
        [_body_contract_item(item) for item in _insert_missing_chapter_anchors(body[first_chapter:])],
        [_source_toc_item(item) for item in body[:first_chapter]],
    )


def _insert_missing_chapter_anchors(body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchored: list[dict[str, Any]] = []
    current_chapter = ""
    for item in body:
        if item.get("type") == "chapter":
            current_chapter = str(item.get("number") or "")
            anchored.append(item)
            continue
        if item.get("type") == "section":
            chapter_number = _section_chapter_number(str(item.get("number") or ""))
            if chapter_number and chapter_number != current_chapter:
                anchored.append(
                    {
                        "type": "chapter",
                        "number": chapter_number,
                        "title": _synthetic_chapter_title(chapter_number),
                        "synthetic_heading": True,
                        "source_trace": item.get("source_trace"),
                    }
                )
                current_chapter = chapter_number
        anchored.append(item)
    return anchored


def _section_chapter_number(number: str) -> str:
    match = re.match(r"^([1-9]\d*)\.\d+", str(number or ""))
    return match.group(1) if match else ""


def _synthetic_chapter_title(number: str) -> str:
    if number == "1":
        return "绪论"
    return f"第{number}章"


def _body_contract_item(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(item)
    cleaned.pop("_source_title", None)
    return cleaned


def _source_toc_item(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = _body_contract_item(item)
    if item.get("_source_title"):
        cleaned["title"] = item["_source_title"]
    return cleaned


def _equations_need_review(equations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for index, equation in enumerate(equations):
        source = equation.get("source") if isinstance(equation.get("source"), dict) else {}
        review.append(
            {
                "id": str(equation.get("id") or equation.get("text") or f"eq-{index + 1}"),
                "kind": str(equation.get("kind") or "unknown"),
                "source_text": str(equation.get("text") or equation.get("kind") or equation.get("id") or ""),
                "source_page": source.get("page_hint"),
                "paragraph_index": source.get("paragraph_index"),
                "context": "",
                "needs_review": True,
            }
        )
    return review


def _apply_native_equation_results(model: dict[str, Any], native_report: dict[str, Any]) -> dict[str, Any]:
    promoted = copy.deepcopy(model)
    results = {
        str(item.get("id") or ""): item
        for item in native_report.get("equations") or []
        if isinstance(item, dict) and item.get("id")
    }
    failures_by_equation: dict[str, list[str]] = {}
    for failure in native_report.get("failure_queue") or []:
        if not isinstance(failure, dict):
            continue
        region = str(failure.get("region") or "")
        equation_id = region.split("equations.", 1)[1] if region.startswith("equations.") else ""
        if equation_id:
            failures_by_equation.setdefault(equation_id, []).append(str(failure.get("id") or ""))
    for equation in promoted.get("equations") or []:
        if not isinstance(equation, dict):
            continue
        equation_id = str(equation.get("id") or "")
        result = results.get(equation_id)
        if not result:
            continue
        conversion = result.get("conversion") if isinstance(result.get("conversion"), dict) else {}
        visual = result.get("visual") if isinstance(result.get("visual"), dict) else {}
        equation["native_conversion"] = {
            "status": str(result.get("status") or ""),
            "method": str(conversion.get("method") or ""),
            "visual_status": str(visual.get("status") or ""),
            "visual_score": visual.get("score"),
            "failure_ids": failures_by_equation.get(equation_id, []),
            "candidate_asset": f"equation_native/equations/{equation_id}/candidate.tex",
        }
        if result.get("status") != "converted":
            continue
        latex = str(result.get("latex") or "").strip()
        if not latex:
            continue
        equation["source_kind"] = str(equation.get("kind") or "")
        equation["kind"] = "latex"
        equation["latex"] = latex
        equation["requires_review"] = False
    return promoted


def _equation_native_summary(native_report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    return {
        "status": native_report.get("status"),
        "equation_count": int(native_report.get("equation_count") or 0),
        "converted": int(native_report.get("converted") or 0),
        "needs_review": int(native_report.get("needs_review") or 0),
        "failed": int(native_report.get("failed") or 0),
        "unsupported": int(native_report.get("unsupported") or 0),
        "report": str(out_dir / "equation_native" / "report.json"),
        "failure_queue": str(out_dir / "equation_native" / "failure_queue.json"),
    }


def _equation_items_from_source(equations: list[dict[str, Any]], body_index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rendered: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    for index, equation in enumerate(equations):
        equation_id = str(equation.get("id") or f"eq-{index + 1}")
        if _has_trusted_latex_equation(equation):
            rendered_item = {
                "type": "equation",
                "id": equation_id,
                "kind": str(equation.get("kind") or "latex"),
                "source_kind": str(equation.get("source_kind") or equation.get("kind") or ""),
                "latex": str(equation.get("latex") or equation.get("tex") or "").strip(),
                "number": str(equation.get("number") or ""),
                "conversion_status": "native_latex",
                "source_trace": _source_trace(equation.get("source"), "body", body_index + len(rendered)),
            }
            for key in ("native_format", "native_sha256", "native_size"):
                if equation.get(key):
                    rendered_item[key] = equation[key]
            if isinstance(equation.get("native_conversion"), dict):
                rendered_item["native_conversion"] = copy.deepcopy(equation["native_conversion"])
            rendered.append(rendered_item)
            continue
        preview_path = str(equation.get("preview_path") or "").strip()
        if preview_path:
            preview_item = {
                "type": "equation_preview",
                "id": equation_id,
                "kind": str(equation.get("kind") or "embedded-object"),
                "asset": preview_path,
                "source_text": str(equation.get("text") or equation.get("kind") or equation_id),
                "needs_review": True,
                "conversion_status": _equation_conversion_status(equation, preview_path),
                "source_trace": _source_trace(equation.get("source"), "body", body_index + len(rendered)),
            }
            preview_item.update(_equation_native_fields(equation))
            if isinstance(equation.get("native_conversion"), dict):
                preview_item["native_conversion"] = copy.deepcopy(equation["native_conversion"])
            rendered.append(preview_item)
        review_item = equation_review_items([equation])[0]
        review_item["id"] = equation_id
        native_conversion = equation.get("native_conversion") if isinstance(equation.get("native_conversion"), dict) else {}
        if native_conversion.get("status") == "candidate_needs_review":
            review_item["workflow_action"] = "review_native_latex_candidate"
        elif _has_mathtype_native_stream(equation):
            review_item["workflow_action"] = "native_stream_extracted_converter_required"
        else:
            review_item["workflow_action"] = "manual_review_required"
        review_item["conversion_status"] = _equation_conversion_status(equation, preview_path)
        if native_conversion:
            review_item["native_conversion"] = copy.deepcopy(native_conversion)
        review_item["rendered_preview"] = bool(preview_path)
        if preview_path:
            review_item["preview_asset_name"] = Path(preview_path).name
        needs_review.append(review_item)
    return rendered, needs_review


def _has_trusted_latex_equation(equation: dict[str, Any]) -> bool:
    latex = str(equation.get("latex") or equation.get("tex") or "").strip()
    if not latex:
        return False
    if bool(equation.get("requires_review")):
        return False
    return str(equation.get("kind") or "").lower() in {"latex", "tex"}


def _equation_conversion_status(equation: dict[str, Any], preview_path: str) -> str:
    native_conversion = equation.get("native_conversion") if isinstance(equation.get("native_conversion"), dict) else {}
    if native_conversion.get("status") == "candidate_needs_review":
        failure_ids = [str(item) for item in native_conversion.get("failure_ids") or []]
        if any(item.startswith("H-EQ-003") for item in failure_ids):
            return "mathtype_translator_warning"
        return "native_latex_candidate_needs_review"
    if native_conversion.get("status") in {"failed", "unsupported"}:
        return f"native_equation_{native_conversion['status']}"
    if _has_mathtype_native_stream(equation):
        return "mtef_native_available_converter_missing"
    return "visual_preview_rendered_native_latex_missing" if preview_path else "unsupported_without_trusted_latex"


def _has_mathtype_native_stream(equation: dict[str, Any]) -> bool:
    return str(equation.get("native_format") or "") == "mathtype_mtef" and bool(equation.get("native_sha256"))


def _equation_native_fields(equation: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in ("native_path", "native_format", "native_stream_name", "native_sha256", "native_size", "native_asset"):
        value = equation.get(key)
        if value:
            fields[key] = value
    if fields.get("native_format") == "mathtype_mtef":
        fields.setdefault("conversion_tool", "mathtype_mtef_probe")
    return fields


def _metadata_with_fallbacks(metadata: dict[str, Any], front: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(metadata)
    if front.get("title_en") and not metadata.get("title_en"):
        metadata["title_en"] = front.get("title_en")
    author_en = str(front.get("author_en") or metadata.get("author_en") or "").strip()
    tutor_en = str(front.get("tutor_en") or metadata.get("tutor_en") or "").strip()
    if not author_en and metadata.get("student_name"):
        author_en = _english_name_fallback(str(metadata.get("student_name")))
        metadata["author_en_fallback"] = "pinyin" if _has_pypinyin() else "chinese"
    if not tutor_en and metadata.get("advisor"):
        tutor_en = _english_name_fallback(str(metadata.get("advisor")))
        metadata["tutor_en_fallback"] = "pinyin" if _has_pypinyin() else "chinese"
    metadata["author_en"] = author_en
    metadata["tutor_en"] = tutor_en
    return metadata


def _english_name_fallback(name: str) -> str:
    try:
        from pypinyin import lazy_pinyin

        parts = lazy_pinyin(name)
        if parts:
            return " ".join(part.capitalize() for part in parts)
    except Exception:
        pass
    return name


def _has_pypinyin() -> bool:
    try:
        import pypinyin  # noqa: F401
    except Exception:
        return False
    return True


def _task_book_defaults(task_book: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    task = dict(task_book)
    fallback_fields = set(task.get("fallback_fields") or [])
    if not task.get("title") and metadata.get("title_cn"):
        task["title"] = metadata.get("title_cn", "")
        fallback_fields.add("title")
    for task_key, metadata_key in {
        "student_name": "student_name",
        "advisor": "advisor",
        "college": "college",
        "major": "major",
        "major_class": "major_display_for_taskbook",
        "major_raw": "major_raw",
        "major_normalized": "major_normalized",
        "major_class_display": "major_class_display",
        "class_name": "class_name",
    }.items():
        if not task.get(task_key):
            task[task_key] = metadata.get(metadata_key, "")
            if task[task_key]:
                fallback_fields.add(task_key)
    if not task.get("major_normalized") and task.get("major"):
        task["major_normalized"] = task.get("major")
    if not task.get("major_raw") and task.get("major"):
        task["major_raw"] = task.get("major")
    if not task.get("major_class_display") and task.get("major_class"):
        task["major_class_display"] = (
            str(task.get("major_class")) if "专业类" in str(task.get("major_class")) else f"{task.get('major_class')} 专业类"
        ).strip()
    task["bottom_fields"] = {
        "college": task.get("college", ""),
        "major": task.get("major_normalized") or task.get("major", ""),
        "major_class": task.get("major_class_display") or task.get("major_class", ""),
        "class_name": task.get("class_name", ""),
        "student_name": task.get("student_name", ""),
        "date_range": task.get("date_range", ""),
        "defense_date": task.get("defense_date", ""),
        "grade": task.get("grade", ""),
        "advisor": task.get("advisor", ""),
        "department_director": task.get("department_director", ""),
    }
    task["references"] = normalize_reference_items(task.get("references") or [])
    task["missing_fields"] = [field for field in ("raw_materials", "work_content") if not task.get(field)]
    task["fallback_fields"] = sorted(fallback_fields)
    return task


def _heading_candidates(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": section.get("type"),
            "level": section.get("level"),
            "title": section.get("title"),
        }
        for section in sections
    ]


def _render_mapping(body: list[dict[str, Any]]) -> list[dict[str, str]]:
    mapping: list[dict[str, str]] = []
    for item in body:
        item_type = item.get("type")
        if item_type not in {"chapter", "section", "subsection"}:
            if item_type == "figure":
                mapping.append(
                    {
                        "model_block": f"figure {item.get('number_hint') or ''} {item.get('caption') or ''}".strip(),
                        "latex": "\\begin{figure}...",
                    }
                )
            elif item_type == "equation":
                mapping.append(
                    {
                        "model_block": f"equation {item.get('id') or ''}".strip(),
                        "latex": "\\begin{equation}...",
                    }
                )
            continue
        command = {"chapter": "chapter", "section": "section", "subsection": "subsection"}[item_type]
        number = str(item.get("number") or "").strip()
        title = str(item.get("title") or "").strip()
        label = f"{item_type} {number} {title}".strip()
        mapping.append({"model_block": label, "latex": rf"\{command}{{{title}}}"})
    return mapping


def _clean_heading_title(title: str, number: str) -> str:
    value = str(title or "").strip()
    if number:
        value = re.sub(rf"^{re.escape(number)}\s*", "", value).strip()
    value = _strip_probable_source_page_suffix(value)
    return value or title


def _strip_probable_source_page_suffix(value: str) -> str:
    if re.search(r"[\u4e00-\u9fffA-Za-z]\d{1,3}$", value):
        return re.sub(r"\d{1,3}$", "", value).strip()
    return value


def _legacy_latex_model_from_thesis_model(model: dict[str, Any], degree: str) -> dict[str, Any]:
    metadata = dict(model.get("metadata") or {})
    front = dict(model.get("front_matter") or {})
    body = []
    for section in model.get("sections") or []:
        body.append(
            {
                "type": _body_type(section),
                "number": _heading_number(str(section.get("title") or "")),
                "title": _heading_title(str(section.get("title") or "")),
                "source_trace": _source_trace(section.get("source"), "body", len(body)),
            }
        )
        if section.get("text"):
            body.append(
                {
                    "type": "paragraph",
                    "text": section.get("text"),
                    "source_trace": _source_trace(section.get("source"), "body", len(body)),
                }
            )
    for equation in model.get("equations") or []:
        body.append(
            {
                "type": "equation_placeholder",
                "source_text": equation.get("text") or equation.get("kind") or equation.get("id"),
                "needs_review": True,
                "source_trace": _source_trace(equation.get("source"), "body", len(body)),
            }
        )
    return {
        "degree_type": degree,
        "metadata": metadata,
        "abstract_cn": {
            "body": front.get("chinese_abstract", ""),
            "keywords": _split_keywords(front.get("keywords_cn", "")),
        },
        "abstract_en": {
            "body": front.get("english_abstract", ""),
            "keywords": _split_keywords(front.get("keywords_en", "")),
        },
        "body": body,
        "references": [
            {
                "raw": item.get("text") or item.get("title") or "",
                "source_trace": _source_trace(item.get("source"), "references", index),
            }
            for index, item in enumerate(model.get("references") or [])
        ],
        "acknowledgement": _acknowledgement(model.get("sections") or []),
    }


def _write_debug(out_dir: Path, raw_model: dict[str, Any], latex_model: dict[str, Any]) -> None:
    debug = out_dir / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    metadata = raw_model.get("metadata") or {}
    (debug / "metadata_candidates.json").write_text(
        json.dumps(metadata.get("candidates") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "metadata_resolution.json").write_text(
        json.dumps(metadata.get("resolution") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata_report = out_dir / "harness" / "metadata_report.json"
    if metadata_report.exists():
        (debug / "metadata_report.json").write_text(metadata_report.read_text(encoding="utf-8"), encoding="utf-8")
    (debug / "abstract_candidates.json").write_text(
        json.dumps(raw_model.get("front_matter") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "body_blocks.json").write_text(
        json.dumps(latex_model.get("body") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    latex_debug = latex_model.get("debug") or {}
    (debug / "task_book_blocks.json").write_text(
        json.dumps(latex_debug.get("task_book_blocks") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "source_toc.json").write_text(
        json.dumps(latex_debug.get("source_toc") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "heading_candidates.json").write_text(
        json.dumps(latex_debug.get("heading_candidates") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "back_matter_blocks.json").write_text(
        json.dumps(latex_model.get("back_matter") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "equation_report.json").write_text(
        json.dumps(_equation_debug_report(latex_model), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "references_taskbook.json").write_text(
        json.dumps(latex_debug.get("references_taskbook") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "references_main.json").write_text(
        json.dumps(latex_debug.get("references_main") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "figure_candidates.json").write_text(
        json.dumps(latex_debug.get("figure_candidates") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "figure_captions.json").write_text(
        json.dumps(latex_debug.get("figure_captions") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "figure_bindings.json").write_text(
        json.dumps(latex_debug.get("figure_bindings") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "render_mapping.json").write_text(
        json.dumps(latex_debug.get("render_mapping") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "figures.json").write_text(
        json.dumps(raw_model.get("figures") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "references.json").write_text(
        json.dumps(latex_model.get("references") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_model(out_dir: Path, latex_model: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model.json").write_text(json.dumps(latex_model, ensure_ascii=False, indent=2), encoding="utf-8")


def _equation_debug_report(latex_model: dict[str, Any]) -> dict[str, Any]:
    body = latex_model.get("body") or []
    native = _collect_body_items_by_type(body, "equation")
    previews = _collect_body_items_by_type(body, "equation_preview")
    placeholders = _collect_body_items_by_type(body, "equation_placeholder")
    review = [item for item in latex_model.get("equations_need_review") or [] if isinstance(item, dict)]
    ids = {
        str(item.get("id"))
        for item in [*native, *previews, *placeholders, *review]
        if isinstance(item, dict) and item.get("id")
    }
    total = len(ids) if ids else len(native) + len(previews) + len(placeholders) + len(review)
    native_streams = [item for item in review if item.get("native_format")]
    return {
        "total_equations": total,
        "latex_converted": len(native),
        "image_fallback": len(previews),
        "placeholders": len(placeholders),
        "needs_review": len(review),
        "conversion_attempted": True,
        "conversion_tool": "mathtype_mtef_probe" if native_streams else "none",
        "native_streams_found": len(native_streams),
        "mathtype_mtef": len([item for item in native_streams if item.get("native_format") == "mathtype_mtef"]),
        "native_latex_complete": total > 0 and len(native) == total and not review and not previews and not placeholders,
        "items": review,
    }


def _collect_body_items_by_type(body: list[Any], item_type: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        if item.get("type") == item_type:
            items.append(item)
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") == item_type:
                items.append(segment)
    return items


def _stage_latex_assets(latex_model: dict[str, Any], out_dir: Path) -> None:
    figure_dir = out_dir / "assets" / "figures"
    equation_dir = out_dir / "assets" / "equations"
    used_names: set[str] = set()
    used_equation_names: set[str] = set()
    staged_by_original: dict[str, str] = {}
    for item in _iter_latex_asset_items(latex_model.get("body") or []):
        raw_asset = str(item.get("asset") or "")
        if not raw_asset:
            continue
        source = Path(raw_asset)
        target_dir = equation_dir if item.get("type") == "equation_preview" else figure_dir
        used_for_type = used_equation_names if item.get("type") == "equation_preview" else used_names
        if not source.exists() or source.suffix.lower() not in SUPPORTED_LATEX_IMAGE_EXTENSIONS | CONVERTIBLE_PREVIEW_EXTENSIONS:
            staged_by_original[raw_asset] = ""
            item["source_asset_name"] = source.name
            item["asset"] = ""
            item["needs_review"] = True
            item["missing_asset"] = True
            continue
        target = stage_latex_image_asset(source, target_dir, used_for_type)
        if target is None:
            staged_by_original[raw_asset] = ""
            item["source_asset_name"] = source.name
            item["asset"] = ""
            item["needs_review"] = True
            item["missing_asset"] = True
            continue
        asset_group = "equations" if item.get("type") == "equation_preview" else "figures"
        staged = f"assets/{asset_group}/{target.name}".replace("\\", "/")
        item["asset"] = staged
        item["render_asset"] = staged
        staged_by_original[raw_asset] = staged
    _sanitize_figure_debug_assets(latex_model, staged_by_original)
    _stage_equation_native_assets(latex_model, out_dir)


def _iter_latex_asset_items(body: list[Any]):
    for item in body:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"figure", "equation_preview"}:
            yield item
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") == "equation_preview":
                yield segment


def _stage_equation_native_assets(latex_model: dict[str, Any], out_dir: Path) -> None:
    native_dir = out_dir / "debug" / "equations_native"
    staged_by_original: dict[str, str] = {}
    used_names: set[str] = set()
    for item in _iter_equation_review_items(latex_model):
        native_path = str(item.get("native_path") or "")
        if not native_path:
            continue
        if native_path in staged_by_original:
            item["native_asset"] = staged_by_original[native_path]
            item.pop("native_path", None)
            continue
        source = Path(native_path)
        if not source.exists():
            item["native_missing"] = True
            item.pop("native_path", None)
            continue
        native_dir.mkdir(parents=True, exist_ok=True)
        target = native_dir / _unique_asset_name(f"{item.get('id') or source.stem}.mtef", used_names)
        shutil.copy2(source, target)
        staged = f"debug/equations_native/{target.name}".replace("\\", "/")
        staged_by_original[native_path] = staged
        item["native_asset"] = staged
        item.pop("native_path", None)


def _iter_equation_review_items(latex_model: dict[str, Any]):
    for item in _iter_equation_items(latex_model.get("body") or []):
        yield item
    for item in latex_model.get("equations_need_review") or []:
        if isinstance(item, dict):
            yield item


def _iter_equation_items(body: list[Any]):
    for item in body:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"equation", "equation_preview", "equation_placeholder"}:
            yield item
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") in {"equation", "equation_preview", "equation_placeholder"}:
                yield segment


def _sanitize_figure_debug_assets(latex_model: dict[str, Any], staged_by_original: dict[str, str]) -> None:
    debug = latex_model.get("debug")
    if not isinstance(debug, dict):
        return
    for key in ("figure_candidates", "figure_bindings", "figure_needs_review"):
        for item in debug.get(key) or []:
            if not isinstance(item, dict):
                continue
            raw_asset = str(item.get("asset") or "")
            if not raw_asset:
                continue
            if raw_asset in staged_by_original:
                staged = staged_by_original[raw_asset]
                if staged:
                    item["asset"] = staged
                else:
                    item["source_asset_name"] = Path(raw_asset).name
                    item["asset"] = ""
                continue
            path = Path(raw_asset)
            if path.is_absolute():
                item["source_asset_name"] = path.name
                item["asset"] = ""


def _unique_asset_name(name: str, used_names: set[str]) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name).strip("._") or "figure"
    candidate = safe
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _debug_paths(out_dir: Path) -> dict[str, str]:
    return {
        "metadata_candidates": str(out_dir / "debug" / "metadata_candidates.json"),
        "metadata_resolution": str(out_dir / "debug" / "metadata_resolution.json"),
        "metadata_report": str(out_dir / "debug" / "metadata_report.json"),
        "source_toc": str(out_dir / "debug" / "source_toc.json"),
        "heading_candidates": str(out_dir / "debug" / "heading_candidates.json"),
        "task_book_blocks": str(out_dir / "debug" / "task_book_blocks.json"),
        "body_blocks": str(out_dir / "debug" / "body_blocks.json"),
        "back_matter_blocks": str(out_dir / "debug" / "back_matter_blocks.json"),
        "equation_report": str(out_dir / "debug" / "equation_report.json"),
        "equations_native": str(out_dir / "debug" / "equations_native"),
        "references_taskbook": str(out_dir / "debug" / "references_taskbook.json"),
        "references_main": str(out_dir / "debug" / "references_main.json"),
        "figure_candidates": str(out_dir / "debug" / "figure_candidates.json"),
        "figure_captions": str(out_dir / "debug" / "figure_captions.json"),
        "figure_bindings": str(out_dir / "debug" / "figure_bindings.json"),
        "render_mapping": str(out_dir / "debug" / "render_mapping.json"),
        "figures": str(out_dir / "debug" / "figures.json"),
        "references": str(out_dir / "debug" / "references.json"),
    }


def _prepare_out_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for artifact in ("thesis.tex", "thesis.pdf", "compile.log", "report.json", "template_inspection.json", "model.json"):
        path = out_dir / artifact
        if path.exists():
            path.unlink()
    for directory in ("workdir", "debug", "harness", "chunks", "assets", "equation_native"):
        path = out_dir / directory
        if path.exists():
            shutil.rmtree(path)


def _pipeline_source_identity(source: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "candidate_path": str(source),
        "source_sha256": digest.hexdigest(),
        "source_size": source.stat().st_size,
        "source_type": source.suffix.lower().lstrip("."),
    }


def _merge_status(render_status: str, extraction_status: str) -> str:
    order = {"pass": 0, "needs_review": 1, "failed": 2}
    return render_status if order[render_status] >= order[extraction_status] else extraction_status


def _source_trace(source: Any, chunk_id: str, block_index: int) -> dict[str, Any] | None:
    if not isinstance(source, dict):
        return None
    return {
        "source_file": source.get("file") or "",
        "source_type": "pdf" if str(source.get("file") or "").lower().endswith(".pdf") else "docx",
        "chunk_id": chunk_id,
        "page_start": source.get("page_hint"),
        "page_end": source.get("page_hint"),
        "paragraph_start": source.get("paragraph_index"),
        "paragraph_end": source.get("paragraph_index"),
        "block_index": block_index,
        "confidence": source.get("confidence", 0.0),
    }


def _write_latex_gate_reports(
    out_dir: Path,
    latex_model: dict[str, Any],
    render_report: dict[str, Any],
    extraction_result: dict[str, Any],
) -> dict[str, Any]:
    harness = out_dir / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    board = {gate: {"name": name, "status": "pass"} for gate, name in {
        "G20": "latex_template_inspection",
        "G21": "latex_model_validation",
        "G22": "latex_render",
        "G23": "latex_compile",
        "G24": "latex_pdf_smoke",
        "G25": "latex_metadata_completeness",
        "G26": "latex_chunk_traceability",
        "G27": "latex_semantic_review",
        "G28": "latex_layout_contract",
    }.items()}
    failures: list[dict[str, Any]] = []

    failure_counts: dict[str, int] = {}

    def add(
        gate: str,
        status: str,
        reason: str,
        evidence: str,
        suggested_fix: str,
        *,
        region: str | None = None,
        expected: str | None = None,
        can_fix_now: bool = True,
    ) -> None:
        board[gate]["status"] = _merge_status(board[gate]["status"], status)
        base_id = _latex_failure_id(gate, reason)
        failure_counts[base_id] = failure_counts.get(base_id, 0) + 1
        failure_id = base_id if failure_counts[base_id] == 1 else f"{base_id}-{failure_counts[base_id]:02d}"
        failures.append(
            {
                "id": failure_id,
                "gate": gate,
                "reason": reason,
                "region": region or board[gate]["name"],
                "evidence_text": evidence,
                "expected": expected or f"{board[gate]['name']} passes without {reason}.",
                "suggested_fix": suggested_fix,
                "can_fix_now": can_fix_now,
            }
        )

    if not (out_dir / "template_inspection.json").exists():
        add("G20", "failed", "missing_template_inspection", str(out_dir / "template_inspection.json"), "Inspect BUAAthesis template before render.")
    model_text = json.dumps(latex_model, ensure_ascii=False)
    for token in ("MERGEFORMAT", "[Figure", "D:\\", ".worktrees"):
        if token in model_text:
            add("G21", "failed", "forbidden_model_token", token, "Remove debug/path residue from model.json.")
    body = [item for item in latex_model.get("body") or [] if isinstance(item, dict)]
    first_heading = next((item for item in body if item.get("type") in {"chapter", "section", "subsection"}), None)
    if first_heading and first_heading.get("type") != "chapter":
        add("G21", "failed", "body_first_heading_not_chapter", str(first_heading), "Ensure model.body starts with chapter 1 before section blocks.")
    seen_chapter = False
    for index, item in enumerate(body):
        item_type = item.get("type")
        if item_type == "chapter":
            seen_chapter = True
        elif item_type in {"section", "subsection"} and not seen_chapter:
            add("G21", "failed", "body_section_before_chapter", f"body[{index}] {item}", "Filter source TOC and classify chapter headings before render.")
        if _looks_like_source_toc_text(" ".join(str(item.get(key) or "") for key in ("title", "text"))):
            add("G21", "failed", "source_toc_leak", str(item), "Keep source TOC only in debug/source_toc.json.")
    thesis_tex = out_dir / "thesis.tex"
    tex_text = thesis_tex.read_text(encoding="utf-8") if thesis_tex.exists() else ""
    if not thesis_tex.exists():
        add("G22", "failed", "missing_thesis_tex", str(thesis_tex), "Render BUAAthesis LaTeX source.")
    if r"\maketitle" not in tex_text:
        add("G22", "failed", "missing_maketitle", "thesis.tex", "Use BUAAthesis cover implementation via \\maketitle.")
    if r"\begin{titlepage}" in tex_text:
        add("G22", "failed", "manual_titlepage", "thesis.tex", "Do not manually reconstruct the cover.")
    body_tex = out_dir / "workdir" / "data" / "body.tex"
    body_tex_text = body_tex.read_text(encoding="utf-8") if body_tex.exists() else ""
    combined_tex = "\n".join([tex_text, body_tex_text])
    if re.search(r"\\(?:section|subsection|subsubsection)\s*\{\s*0\.\d+\b", combined_tex):
        add("G22", "failed", "zero_numbered_heading_in_tex", "0.x", "Do not emit sections before the first chapter.")
    if re.search(r"oleObject\d*\.bin", combined_tex, flags=re.IGNORECASE):
        add("G22", "failed", "ole_object_filename_in_tex", "oleObject*.bin", "Report OLE equations in report.json instead of final LaTeX body.")
    com_info = out_dir / "workdir" / "data" / "com_info.tex"
    com_info_text = com_info.read_text(encoding="utf-8") if com_info.exists() else ""
    if re.search(r"\\thesisauthor\{[^{}]*\}\{(?:\s|\\mbox\{\})*\}", com_info_text):
        add("G25", "failed", "blank_author_en", "\\thesisauthor second argument", "Populate author_en with pinyin or configured fallback.")
    if re.search(r"\\teacher\{[^{}]*\}\{(?:\s|\\mbox\{\})*\}", com_info_text):
        add("G25", "failed", "blank_tutor_en", "\\teacher second argument", "Populate tutor_en with pinyin or configured fallback.")
    compile_status = render_report.get("compile_status", {})
    compile_state = str(compile_status.get("status") or "")
    if compile_state == "skipped":
        add(
            "G23",
            "needs_review",
            "latex_compile_skipped",
            str(compile_status),
            "Run XeLaTeX before final delivery; --no-compile is debug-only.",
        )
    elif compile_state == "skipped_missing_xelatex":
        add(
            "G23",
            "failed",
            "latex_engine_missing",
            str(compile_status),
            "Install XeLaTeX/latexmk and compile the candidate PDF.",
        )
    elif compile_state != "success":
        add("G23", "failed", "latex_compile_failed", str(compile_status), "Inspect compile.log and fix render input.")
    if not (out_dir / "thesis.pdf").exists():
        add("G24", "failed", "missing_pdf_after_compile", str(out_dir / "thesis.pdf"), "Ensure compiled PDF is copied to output.")
    if (out_dir / "thesis.pdf").exists() and (out_dir / "thesis.pdf").stat().st_size <= 0:
        add("G24", "failed", "empty_pdf", str(out_dir / "thesis.pdf"), "Regenerate PDF.")
    pdf_text = _read_pdf_text(out_dir / "thesis.pdf")
    pdf_smoke: dict[str, Any] = {"pdf": str(out_dir / "thesis.pdf"), "exists": (out_dir / "thesis.pdf").exists(), "checked_text": bool(pdf_text)}
    if pdf_text:
        if _pdf_has_zero_numbered_heading(pdf_text):
            add("G24", "failed", "zero_numbered_heading_in_pdf", "0.x", "Fix heading mapping so LaTeX does not generate chapter 0 sections.")
        if re.search(r"oleObject\d*\.bin", pdf_text, flags=re.IGNORECASE):
            add("G24", "failed", "ole_object_filename_in_pdf", "oleObject*.bin", "Do not expose OLE equation filenames in final PDF.")
        if "MERGEFORMAT" in pdf_text:
            add("G24", "failed", "field_code_residue_in_pdf", "MERGEFORMAT", "Remove Word field-code residue before render.")
    if extraction_result["gate_board"]["E02"]["status"] != "pass":
        add("G25", extraction_result["gate_board"]["E02"]["status"], "metadata_not_complete", "E02", "Improve metadata extraction.")
    if extraction_result["gate_board"]["E08"]["status"] != "pass":
        add("G26", extraction_result["gate_board"]["E08"]["status"], "chunk_trace_needs_review", "E08", "Attach source_trace to extracted blocks.")
    task_report = render_report.get("task_book") if isinstance(render_report.get("task_book"), dict) else {}
    bottom_fields = task_report.get("bottom_fields") if isinstance(task_report.get("bottom_fields"), dict) else {}
    for field in ("college", "major_class", "student_name", "advisor"):
        if not str(bottom_fields.get(field) or "").strip():
            add("G27", "needs_review", "taskbook_metadata_missing", field, "Fill task book bottom fields from task book or metadata fallback.")
    if task_report.get("missing_fields"):
        add("G27", "needs_review", "taskbook_bottom_field_parse_failed", str(task_report.get("missing_fields")), "Improve task book section extraction.")
    references_report = render_report.get("references") if isinstance(render_report.get("references"), dict) else {}
    if references_report.get("bad_wrapping_detected"):
        add("G27", "failed", "main_reference_entry_merge_failed", "bad_wrapping_detected", "Repair reference entry splitting and spacing before render.")
    figures_report = render_report.get("figures") if isinstance(render_report.get("figures"), dict) else {}
    for missing in figures_report.get("missing") or []:
        add("G27", "needs_review", "figure_missing_asset", json.dumps(missing, ensure_ascii=False), "Bind caption to an extracted image or keep a reported review placeholder.")
    equations_report = render_report.get("equations") if isinstance(render_report.get("equations"), dict) else {}
    if int(equations_report.get("image_fallback") or 0) > 0:
        add("G27", "needs_review", "equation_image_fallback_needs_review", str(equations_report.get("image_fallback")), "Keep preview fallback but continue native LaTeX conversion work.")
    if int(equations_report.get("total") or 0) > 0 and not equations_report.get("native_latex_complete"):
        add("G27", "needs_review", "equation_not_native_latex", str(equations_report.get("total")), "Report which equations are image fallbacks instead of claiming native LaTeX completion.")

    layout_result = validate_layout(out_dir, latex_model, render_report)
    board["G28"] = layout_result["gate"]
    failures.extend(layout_result["failures"])

    status = "failed" if any(item["status"] == "failed" for item in board.values()) else "needs_review" if any(item["status"] == "needs_review" for item in board.values()) else "pass"
    reports = {
        "gate_board.json": board,
        "failure_queue.json": failures,
        "latex_model_report.json": {"forbidden_checked": True, "metadata_fields": sorted((latex_model.get("metadata") or {}).keys())},
        "latex_render_report.json": {"thesis_tex": str(thesis_tex), "uses_maketitle": r"\maketitle" in tex_text, "manual_titlepage": r"\begin{titlepage}" in tex_text},
        "latex_compile_report.json": compile_status,
        "latex_pdf_smoke_report.json": pdf_smoke,
    }
    for filename, payload in reports.items():
        (harness / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": status, "gate_board": board, "failure_queue": failures}


_LATEX_FAILURE_IDS = {
    ("G20", "missing_template_inspection"): "H-G20-001",
    ("G21", "forbidden_model_token"): "H-G21-001",
    ("G21", "body_first_heading_not_chapter"): "H-G21-002",
    ("G21", "body_section_before_chapter"): "H-G21-003",
    ("G21", "source_toc_leak"): "H-G21-004",
    ("G22", "missing_thesis_tex"): "H-G22-001",
    ("G22", "missing_maketitle"): "H-G22-002",
    ("G22", "manual_titlepage"): "H-G22-003",
    ("G22", "zero_numbered_heading_in_tex"): "H-G22-004",
    ("G22", "ole_object_filename_in_tex"): "H-G22-005",
    ("G23", "latex_compile_failed"): "H-G23-001",
    ("G23", "latex_compile_skipped"): "H-G23-002",
    ("G23", "latex_engine_missing"): "H-G23-003",
    ("G24", "missing_pdf_after_compile"): "H-G24-001",
    ("G24", "empty_pdf"): "H-G24-002",
    ("G24", "zero_numbered_heading_in_pdf"): "H-G24-003",
    ("G24", "ole_object_filename_in_pdf"): "H-G24-004",
    ("G24", "field_code_residue_in_pdf"): "H-G24-005",
    ("G25", "blank_author_en"): "H-G25-001",
    ("G25", "blank_tutor_en"): "H-G25-002",
    ("G25", "metadata_not_complete"): "H-G25-003",
    ("G26", "chunk_trace_needs_review"): "H-G26-001",
    ("G27", "equation_image_fallback_needs_review"): "H-G27-001",
    ("G27", "equation_not_native_latex"): "H-G27-002",
    ("G27", "taskbook_metadata_missing"): "H-G27-003",
    ("G27", "taskbook_bottom_field_parse_failed"): "H-G27-004",
    ("G27", "main_reference_entry_merge_failed"): "H-G27-005",
    ("G27", "figure_missing_asset"): "H-G27-006",
}


def _latex_failure_id(gate: str, reason: str) -> str:
    return _LATEX_FAILURE_IDS.get((gate, reason), f"H-{gate}-999")


def _pdf_has_zero_numbered_heading(pdf_text: str) -> bool:
    for raw_line in str(pdf_text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        match = re.match(r"^0\.\d+(?:\.\d+)*\s+(.+)$", line)
        if not match:
            continue
        title = match.group(1).strip()
        if re.match(r"^[时为是的及和与或、，,。；;：:）)]", title):
            continue
        if re.search(r"[，,、。；;=<>]|\(\d+(?:[.\-]\d+)+\)|[\ufffd-\uffff]", title):
            continue
        if re.match(
            r"^(?:sin|cos|tan|arccos|exp|det|sinc|rad(?:/|\b)|[A-Za-z]\b)",
            title,
            flags=re.IGNORECASE,
        ):
            continue
        if re.match(r"^[\u4e00-\u9fffA-Za-z]", title):
            return True
    return False


def _looks_like_source_toc_text(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return False
    if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d{1,3}$", value):
        return True
    if re.match(r"^\d+(?:\.\d+)+\s+\S.{0,100}\s+\d{1,3}$", value):
        return True
    return bool(re.match(r"^第[一二三四五六七八九十百零〇两]+章\s+\S.{0,100}\s+\d{1,3}$", value))


def _read_pdf_text(pdf_path: Path) -> str:
    if not pdf_path.exists():
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _body_type(section: dict[str, Any]) -> str:
    level = int(section.get("level") or 1)
    if level <= 1:
        return "chapter"
    if level == 2:
        return "section"
    return "subsection"


def _heading_number(title: str) -> str:
    match = __import__("re").match(r"^(\d+(?:\.\d+)*)\s+", title)
    return match.group(1) if match else ""


def _heading_title(title: str) -> str:
    return __import__("re").sub(r"^\d+(?:\.\d+)*\s+", "", title).strip() or title


def _split_keywords(value: str) -> list[str]:
    import re

    return [item.strip() for item in re.split(r"[;,，；]", str(value or "")) if item.strip()]


def _acknowledgement(sections: list[dict[str, Any]]) -> str:
    for section in sections:
        if str(section.get("type") or "").lower() in {"acknowledgement", "acknowledgements"}:
            return str(section.get("text") or "")
    return ""
