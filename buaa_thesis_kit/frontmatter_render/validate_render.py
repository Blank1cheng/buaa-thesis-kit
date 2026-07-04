from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageChops

from buaa_thesis_kit.frontmatter_render.layout_spec import RenderValidationConfig, normalize_frontmatter_pages
from buaa_thesis_kit.pdf_export import export_pdf_from_docx


PAGE_TO_INDEX = {
    "cover": 0,
    "spine": 1,
    "taskbook": 2,
    "declaration": 3,
    "abstract_cn": 4,
    "abstract_en": 5,
    "toc": 6,
}
FORBIDDEN_RENDER_TEXT_MARKERS = (
    "[Figure inserted]",
    "[Figure requires review]",
    "[Equation preview inserted]",
    "D:\\",
    ".worktrees",
    "output_work_",
    "image1.png",
    ".wmf",
    ".emf",
    "本页由规范化流水线",
    "需人工复核",
    "References 作为中文参考文献标题",
    "MERGEFORMAT",
    "公式章",
    "下一章",
)


def validate_render_frontmatter(
    reference: Path,
    candidate: Path,
    output_dir: Path,
    config: RenderValidationConfig | None = None,
    pages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    cfg = config or RenderValidationConfig()
    selected_pages = normalize_frontmatter_pages(pages)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "pass",
        "sample_mode": cfg.sample_mode,
        "pages_requested": selected_pages,
        "page_status": {},
        "cover": {},
        "spine": {},
        "task_book": {},
        "declaration": {},
        "abstracts": {},
        "toc": {},
        "blocking_items": [],
        "notes": [],
    }
    blocking: list[str] = report["blocking_items"]
    notes: list[str] = report["notes"]

    with tempfile.TemporaryDirectory(prefix="frontmatter-render-") as temp:
        temp_dir = Path(temp)
        reference_pdf, reference_note = _as_pdf(Path(reference), temp_dir / "reference.pdf")
        candidate_pdf, candidate_note = _as_pdf(Path(candidate), temp_dir / "candidate.pdf")
        notes.extend([reference_note, candidate_note])
        if candidate_pdf is None:
            blocking.append("candidate_pdf_unavailable")
            report["status"] = "failed"
            _write_report(out, report)
            return report
        render_dir = out / "pages"
        render_dir.mkdir(parents=True, exist_ok=True)
        candidate_pages = _render_pages(candidate_pdf, render_dir, "candidate", cfg)
        reference_pages = _render_pages(reference_pdf, render_dir, "reference", cfg) if reference_pdf else []
        if reference_pages and candidate_pages:
            _write_diff_images(reference_pages[0], candidate_pages[0], out)
            _write_named_diff_images(reference_pages, candidate_pages, out, selected_pages)
        _write_anchor_report(out, reference_pages, candidate_pages, selected_pages)
        _inspect_candidate_pdf(candidate_pdf, report, cfg, selected_pages)

    report["status"] = "failed" if blocking else _aggregate_status(report, selected_pages)
    _write_report(out, report)
    return report


def _as_pdf(path: Path, target_pdf: Path) -> tuple[Path | None, str]:
    if not path.exists():
        return None, f"missing_source: {path}"
    if path.suffix.lower() == ".pdf":
        return path, f"using_pdf_source: {path}"
    if path.suffix.lower() != ".docx":
        return None, f"unsupported_render_source: {path}"
    ok, message = export_pdf_from_docx(path, target_pdf)
    if ok:
        return target_pdf, message
    return None, message


def _render_pages(pdf: Path, out: Path, prefix: str, cfg: RenderValidationConfig) -> list[Path]:
    rendered: list[Path] = []
    document = fitz.open(pdf)
    for index in range(min(document.page_count, cfg.front_pages_to_render)):
        page_path = out / f"{prefix}_page_{index + 1:03d}.png"
        pix = document.load_page(index).get_pixmap(matrix=fitz.Matrix(cfg.render_zoom, cfg.render_zoom), alpha=False)
        pix.save(page_path)
        rendered.append(page_path)
    return rendered


def _write_diff_images(reference_png: Path, candidate_png: Path, out: Path) -> None:
    reference = Image.open(reference_png).convert("RGB")
    candidate = Image.open(candidate_png).convert("RGB")
    if reference.size != candidate.size:
        candidate = candidate.resize(reference.size)
    diff = ImageChops.difference(reference, candidate)
    overlay = Image.blend(reference, candidate, 0.5)
    diff.save(out / "page_001_diff.png")
    overlay.save(out / "page_001_overlay.png")


def _write_named_diff_images(reference_pages: list[Path], candidate_pages: list[Path], out: Path, pages: list[str]) -> None:
    for page in pages:
        index = PAGE_TO_INDEX.get(page)
        if index is None or index >= len(reference_pages) or index >= len(candidate_pages):
            continue
        reference = Image.open(reference_pages[index]).convert("RGB")
        candidate = Image.open(candidate_pages[index]).convert("RGB")
        if reference.size != candidate.size:
            candidate = candidate.resize(reference.size)
        ImageChops.difference(reference, candidate).save(out / f"{page}_diff.png")


def _write_anchor_report(out: Path, reference_pages: list[Path], candidate_pages: list[Path], pages: list[str]) -> None:
    anchors = {
        "pages": pages,
        "reference_pages": [path.name for path in reference_pages],
        "candidate_pages": [path.name for path in candidate_pages],
        "page_to_index": PAGE_TO_INDEX,
    }
    (out / "page_001_anchors.json").write_text(json.dumps(anchors, ensure_ascii=False, indent=2), encoding="utf-8")


def _inspect_candidate_pdf(
    pdf: Path,
    report: dict[str, Any],
    cfg: RenderValidationConfig,
    selected_pages: list[str],
) -> None:
    document = fitz.open(pdf)
    page_texts = [document.load_page(index).get_text("text") for index in range(min(document.page_count, 12))]
    compact = "\n".join(page_texts)
    cover_text = page_texts[0] if page_texts else ""
    report["cover"] = {
        "classification_missing": "分类号" not in cover_text,
        "unit_code_missing": "单位代码" not in cover_text,
        "student_id_missing": "学" not in cover_text or "号" not in cover_text,
        "metadata_duplicate": _cover_metadata_duplicate(cover_text),
        "title_line2_single_char": any(line.strip() == "究" for line in cover_text.splitlines()),
    }
    report["spine"] = {
        "vertical_text_evidence": _looks_like_vertical_spine(page_texts[1] if len(page_texts) > 1 else ""),
    }
    report["task_book"] = {
        "has_i_to_iv": all(marker in compact for marker in ("Ⅰ、", "Ⅱ、", "Ⅲ、", "Ⅳ、")),
        "has_reference_section": "主要参考资料" in compact,
        "has_time_or_grade_field": any(marker in compact for marker in ("毕业设计（论文）时间", "答辩时间", "成绩")),
    }
    report["declaration"] = {
        "wrong_declaration_text": "本人郑重声明" in compact,
        "extra_advisor_signature": "指导教师签名" in compact,
        "has_reference_text": "我声明，本论文及其研究工作是由本人在导师指导下独立完成的" in compact,
        "has_author_signature_time": all(marker in compact for marker in ("作者", "签字", "时间")),
    }
    report["abstracts"] = {
        "cn_contains_english_front_matter": _cn_page_contains_english(page_texts),
        "en_has_required_markers": all(marker in compact for marker in ("Author:", "Tutor:", "Abstract", "Key Words")),
    }
    report["toc"] = {
        "has_toc_field_render": _has_toc_render(compact),
        "body_page_one_evidence": "第 1 页" in compact,
    }
    report["forbidden_text"] = {
        "found": [marker for marker in FORBIDDEN_RENDER_TEXT_MARKERS if marker in compact],
    }
    blocking = report["blocking_items"]
    selected = set(selected_pages)
    if "cover" in selected and report["cover"]["classification_missing"]:
        blocking.append("cover_classification_missing")
    if "cover" in selected and report["cover"]["metadata_duplicate"]:
        blocking.append("cover_metadata_duplicate")
    if "cover" in selected and report["cover"]["title_line2_single_char"]:
        blocking.append("cover_title_line2_single_char")
    if "spine" in selected and not report["spine"]["vertical_text_evidence"]:
        blocking.append("spine_not_vertical_render")
    if "taskbook" in selected and not report["task_book"]["has_i_to_iv"]:
        blocking.append("task_book_missing_i_ii_iii_iv")
    if "declaration" in selected and report["declaration"]["wrong_declaration_text"]:
        blocking.append("declaration_uses_wrong_text")
    if "declaration" in selected and report["declaration"]["extra_advisor_signature"]:
        blocking.append("declaration_extra_advisor_signature")
    if "abstract_cn" in selected and report["abstracts"]["cn_contains_english_front_matter"]:
        blocking.append("cn_abstract_contains_english_front_matter")
    for marker in report["forbidden_text"]["found"]:
        blocking.append(f"forbidden_render_text: {marker}")
    _set_page_status(report, selected_pages)


def _looks_like_vertical_spine(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    one_char_lines = sum(1 for line in lines if len(line) == 1)
    return one_char_lines >= 8 or "BUAA_VERTICAL_SPINE" in text


def _cn_page_contains_english(page_texts: list[str]) -> bool:
    cn_page = next((text for text in page_texts if "摘" in text and "要" in text), "")
    if not cn_page:
        return False
    return any(marker in cn_page for marker in ("Research on", "Author:", "Tutor:"))


def _cover_metadata_duplicate(cover_text: str) -> bool:
    return any(cover_text.count(marker) > 1 for marker in ("单位代码", "学号", "分类号"))


def _has_toc_render(text: str) -> bool:
    if "目录" not in re.sub(r"\s+", "", text):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return any(re.match(r"^\d+(?:\.\d+)*\s+[\u4e00-\u9fffA-Za-z]", line) for line in lines)


def _aggregate_status(report: dict[str, Any], selected_pages: list[str]) -> str:
    checks: list[bool] = []
    selected = set(selected_pages)
    if "taskbook" in selected:
        checks.append(bool(report["task_book"].get("has_i_to_iv")))
    if "declaration" in selected:
        checks.append(bool(report["declaration"].get("has_reference_text")))
    if "abstract_en" in selected:
        checks.append(bool(report["abstracts"].get("en_has_required_markers")))
    if "toc" in selected:
        checks.append(bool(report["toc"].get("has_toc_field_render")))
    return "needs_review" if not all(checks) else "pass"


def _set_page_status(report: dict[str, Any], pages: list[str]) -> None:
    blocking = "\n".join(report["blocking_items"])
    status: dict[str, str] = {}
    for page in pages:
        if page == "cover":
            status[page] = "failed" if "cover_" in blocking else "pass"
        elif page == "spine":
            status[page] = "failed" if "spine_" in blocking else "pass"
        elif page == "taskbook":
            status[page] = "failed" if "task_book_" in blocking else "pass"
        elif page == "declaration":
            status[page] = "failed" if "declaration_" in blocking else "pass"
        elif page == "abstract_cn":
            status[page] = "failed" if "cn_abstract_" in blocking else "pass"
        elif page == "abstract_en":
            status[page] = "pass" if report["abstracts"].get("en_has_required_markers") else "needs_review"
        elif page == "toc":
            status[page] = "pass" if report["toc"].get("has_toc_field_render") else "needs_review"
        else:
            status[page] = "needs_review"
    report["page_status"] = status


def _write_report(out: Path, report: dict[str, Any]) -> None:
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
