from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


FAILURE_IDS = {
    "template_depends_on_tmp": "H-G28-001",
    "taskbook_technical_layout_contract_invalid": "H-G28-002",
    "taskbook_reference_layout_contract_invalid": "H-G28-003",
    "frontmatter_spine_missing": "H-G28-004",
    "toc_color_not_black": "H-G28-005",
    "taskbook_date_mismatch": "H-G28-006",
    "taskbook_reference_count_mismatch": "H-G28-007",
    "taskbook_page_sequence_invalid": "H-G28-008",
    "taskbook_page_overflow": "H-G28-009",
    "taskbook_text_overflow": "H-G28-010",
}


def validate_layout(
    out_dir: str | Path,
    model: dict[str, Any],
    render_report: dict[str, Any],
    *,
    pdf_pages: list[str] | None = None,
    text_bounds: dict[int, list[dict[str, Any]]] | None = None,
    render_evidence: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    harness = out_dir / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    degree = str(model.get("degree_type") or render_report.get("degree_type") or "undergraduate")
    undergraduate = degree == "undergraduate"
    failures: list[dict[str, Any]] = []
    warnings: list[str] = []

    thesis_tex = _read(out_dir / "thesis.tex")
    assign_tex = _read(out_dir / "workdir" / "data" / "bachelor" / "assign.tex")
    assign_patch = _read(out_dir / "workdir" / "data" / "bachelor" / "assign_patch.tex")
    reference_tex = _read(out_dir / "workdir" / "data" / "reference.tex")
    spine_tex = _read(out_dir / "workdir" / "data" / "bachelor" / "spine.tex")
    template_used = str(render_report.get("template_used") or render_report.get("template_path") or "")

    def fail(
        reason: str,
        *,
        region: str,
        evidence_text: str,
        expected: str,
        suggested_fix: str,
        can_fix_now: bool = True,
    ) -> None:
        failures.append(
            {
                "id": FAILURE_IDS[reason],
                "gate": "G28",
                "reason": reason,
                "region": region,
                "evidence_text": evidence_text,
                "expected": expected,
                "suggested_fix": suggested_fix,
                "can_fix_now": can_fix_now,
            }
        )

    if _path_has_tmp_component(template_used):
        fail(
            "template_depends_on_tmp",
            region="template.runtime",
            evidence_text=template_used,
            expected="The default BUAAthesis runtime must be vendored under templates/latex/buaa.",
            suggested_fix="Resolve the renderer against the vendored template instead of tmp or a junction into tmp.",
        )

    if undergraduate:
        technical_contract = (
            r"\buaaAssignTextParagraph" in assign_tex
            and r"\allowbreak{}" in assign_tex
            and r"\buaaAssignTextLine" not in assign_tex
            and r"\newcommand{\buaaAssignTextParagraph}" in assign_patch
            and r"\begin{spacing}{1.5}" in assign_patch
        )
        if not technical_contract:
            fail(
                "taskbook_technical_layout_contract_invalid",
                region="taskbook.technical_requirements",
                evidence_text=_contract_evidence(assign_tex, assign_patch),
                expected="Small-four task-book text must wrap naturally at 1.5 line spacing without Python-fixed display lines.",
                suggested_fix="Render source paragraphs through buaaAssignTextParagraph with TeX break opportunities.",
            )

        reference_contract = (
            r"\buaaAssignRefBlock" in assign_tex
            and r"\newcommand{\buaaAssignRefParagraph}" in assign_patch
            and r"\zihao{-4}" in assign_patch
            and r"\begin{spacing}{1.5}" in assign_patch
            and r"\hangindent" not in assign_patch
            and r"\hangindent=2em" in reference_tex
        )
        if not reference_contract:
            fail(
                "taskbook_reference_layout_contract_invalid",
                region="taskbook.references",
                evidence_text=_contract_evidence(assign_tex, assign_patch, reference_tex),
                expected="Task-book references use small-four natural wrapping; only formal references use a 2em hanging indent.",
                suggested_fix="Keep task-book and formal-reference paragraph styles separate.",
            )

        spine_contract = (
            r"\include{data/bachelor/spine}" in thesis_tex
            and r"\buaaSpinePage" in spine_tex
        )
        if not spine_contract:
            fail(
                "frontmatter_spine_missing",
                region="frontmatter.spine",
                evidence_text="spine include or buaaSpinePage command is missing",
                expected="The undergraduate front matter contains a dedicated spine page after the cover.",
                suggested_fix="Load the model-driven spine module before maketitle finalization.",
            )

    if _documentclass_has_color(thesis_tex):
        fail(
            "toc_color_not_black",
            region="frontmatter.toc",
            evidence_text=_documentclass_line(thesis_tex),
            expected="The print PDF uses monochrome TOC text and links.",
            suggested_fix="Remove the BUAAthesis color document-class option.",
        )

    pages = pdf_pages if pdf_pages is not None else _read_pdf_pages(out_dir / "thesis.pdf")
    if undergraduate and pages:
        page_sequence = _frontmatter_sequence(pages, model)
        if not page_sequence["valid"]:
            fail(
                "taskbook_page_sequence_invalid",
                region="frontmatter.sequence",
                evidence_text=json.dumps(page_sequence["observed"], ensure_ascii=False),
                expected="cover, spine, task-book pages 1-2, declaration, CN abstract, EN abstract, TOC, body",
                suggested_fix="Keep each BUAAthesis front-matter component in its fixed template order.",
            )
        if not page_sequence["taskbook_two_pages"]:
            fail(
                "taskbook_page_overflow",
                region="taskbook.pagination",
                evidence_text=json.dumps(page_sequence["observed"], ensure_ascii=False),
                expected="The task book occupies exactly PDF pages 3 and 4; declaration starts on page 5.",
                suggested_fix="Reduce only task-book paragraph spacing or blank ruled lines while preserving the official font size.",
            )

        task = model.get("task_book") if isinstance(model.get("task_book"), dict) else {}
        page4 = _compact(pages[3]) if len(pages) >= 4 else ""
        expected_date = _compact(task.get("date_range"))
        if expected_date and expected_date not in page4:
            fail(
                "taskbook_date_mismatch",
                region="taskbook.date_range",
                evidence_text=_page_excerpt(pages, 4),
                expected=str(task.get("date_range") or ""),
                suggested_fix="Populate the assignment dates from task_book.date_range, not the cover date.",
            )

        expected_references = [item for item in task.get("references") or [] if str(item).strip()]
        observed_reference_numbers = re.findall(r"\[(\d+)\]", page4)
        if expected_references and len(set(observed_reference_numbers)) != len(expected_references):
            fail(
                "taskbook_reference_count_mismatch",
                region="taskbook.references",
                evidence_text=f"expected={len(expected_references)}, observed={observed_reference_numbers}",
                expected=f"All {len(expected_references)} task-book reference entries appear once on task-book page 2.",
                suggested_fix="Merge wrapped source lines into reference entries before LaTeX rendering.",
            )

    bounds = text_bounds if text_bounds is not None else _pdf_text_bounds(out_dir / "thesis.pdf", pages=(3, 4))
    overflow_items = _overflow_items(bounds)
    for page, items in overflow_items.items():
        fail(
            "taskbook_text_overflow",
            region=f"taskbook.page_{page - 2}",
            evidence_text=json.dumps(items[:5], ensure_ascii=False),
            expected="Every task-book text block stays within the printable horizontal bounds.",
            suggested_fix="Add TeX break opportunities and preserve the task-book text width; do not shrink the font.",
        )

    evidence_paths: dict[str, str] = {}
    if render_evidence and (out_dir / "thesis.pdf").exists():
        evidence_paths, evidence_warning = _render_taskbook_evidence(out_dir / "thesis.pdf", harness)
        if evidence_warning:
            warnings.append(evidence_warning)

    taskbook_report = {
        "status": "failed" if failures else "pass",
        "date_range": (model.get("task_book") or {}).get("date_range") if isinstance(model.get("task_book"), dict) else "",
        "expected_reference_count": len((model.get("task_book") or {}).get("references") or []) if isinstance(model.get("task_book"), dict) else 0,
        "page_bounds": bounds,
        "overflow": overflow_items,
        "evidence": evidence_paths,
        "warnings": warnings,
    }
    sequence_report = _frontmatter_sequence(pages, model) if undergraduate and pages else {
        "valid": not undergraduate,
        "taskbook_two_pages": not undergraduate,
        "observed": [],
    }
    (harness / "taskbook_layout_report.json").write_text(
        json.dumps(taskbook_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (harness / "frontmatter_sequence_report.json").write_text(
        json.dumps(sequence_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    status = "failed" if failures else "pass"
    return {
        "status": status,
        "gate": {"name": "latex_layout_contract", "status": status},
        "failures": failures,
        "reports": {
            "taskbook_layout": str(harness / "taskbook_layout_report.json"),
            "frontmatter_sequence": str(harness / "frontmatter_sequence_report.json"),
            **evidence_paths,
        },
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _path_has_tmp_component(value: str) -> bool:
    return any(part.lower() == "tmp" for part in re.split(r"[\\/]", value) if part)


def _documentclass_line(tex: str) -> str:
    match = re.search(r"\\documentclass(?:\[[^]]*])?\{[^}]+}", tex)
    return match.group(0) if match else "missing documentclass"


def _documentclass_has_color(tex: str) -> bool:
    match = re.search(r"\\documentclass\[([^]]*)]", tex)
    return bool(match and "color" in {item.strip() for item in match.group(1).split(",")})


def _contract_evidence(*texts: str) -> str:
    compact = " | ".join(re.sub(r"\s+", " ", text).strip()[:280] for text in texts)
    return compact or "required generated LaTeX file is missing"


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _contains(page: str, value: Any) -> bool:
    expected = _compact(value)
    return bool(expected and expected in _compact(page))


def _frontmatter_sequence(pages: list[str], model: dict[str, Any]) -> dict[str, Any]:
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    observed = [_page_label(page) for page in pages]
    fixed_checks = [
        len(pages) >= 1 and (_contains(pages[0], metadata.get("classification")) or _contains(pages[0], metadata.get("title_cn"))),
        len(pages) >= 2 and _contains(pages[1], metadata.get("student_name")) and _contains(pages[1], "北京航空航天大学"),
        len(pages) >= 3 and _contains(pages[2], "技术要求") and _contains(pages[2], "工作内容"),
        len(pages) >= 4 and _contains(pages[3], "主要参考资料"),
        len(pages) >= 5 and _contains(pages[4], "本人声明"),
    ]
    cn_page = _find_page(pages, lambda page: _contains(page, "摘要"), start=5)
    en_page = _find_page(pages, lambda page: "abstract" in _compact(page).lower(), start=(cn_page or 5) + 1)
    toc_page = _find_page(pages, lambda page: _contains(page, "目录"), start=(en_page or cn_page or 5) + 1)
    body_page = _find_body_page(pages, model, start=(toc_page or en_page or cn_page or 5) + 1)
    ordered_checks = [
        cn_page is not None,
        en_page is not None and cn_page is not None and en_page > cn_page,
        toc_page is not None and en_page is not None and toc_page > en_page,
        body_page is not None and toc_page is not None and body_page > toc_page,
    ]
    checks = fixed_checks + ordered_checks
    taskbook_two_pages = (
        len(pages) >= 5
        and _contains(pages[2], "技术要求")
        and _contains(pages[3], "主要参考资料")
        and _contains(pages[4], "本人声明")
    )
    return {
        "valid": all(checks),
        "checks": checks,
        "taskbook_two_pages": taskbook_two_pages,
        "positions": {
            "abstract_cn": cn_page,
            "abstract_en": en_page,
            "toc": toc_page,
            "body": body_page,
        },
        "observed": observed,
    }


def _find_page(pages: list[str], predicate, *, start: int) -> int | None:
    for index in range(max(0, start - 1), len(pages)):
        if predicate(pages[index]):
            return index + 1
    return None


def _find_body_page(pages: list[str], model: dict[str, Any], *, start: int) -> int | None:
    body = [item for item in model.get("body") or [] if isinstance(item, dict)]
    chapter_titles = [str(item.get("title") or "").strip() for item in body if item.get("type") == "chapter"]
    chapter_titles = [re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", title) for title in chapter_titles if title]
    for index in range(max(0, start - 1), len(pages)):
        compact = _compact(pages[index])
        if re.search(r"第?1章", compact) or any(_contains(pages[index], title) for title in chapter_titles):
            return index + 1
    return None


def _page_label(page: str) -> str:
    compact = _compact(page)
    labels = (
        ("本人声明", "declaration"),
        ("主要参考资料", "taskbook_2"),
        ("技术要求", "taskbook_1"),
        ("目录", "toc"),
        ("摘要", "abstract_cn"),
        ("Abstract", "abstract_en"),
        ("第1章", "body"),
        ("北京航空航天大学", "cover_or_spine"),
    )
    for token, label in labels:
        if _compact(token).lower() in compact.lower():
            return label
    return compact[:80]


def _page_excerpt(pages: list[str], page_number: int) -> str:
    if page_number < 1 or page_number > len(pages):
        return f"page {page_number} missing"
    return re.sub(r"\s+", " ", pages[page_number - 1]).strip()[:500]


def _read_pdf_pages(pdf_path: Path) -> list[str]:
    if not pdf_path.exists():
        return []
    try:
        from pypdf import PdfReader

        return [(page.extract_text() or "") for page in PdfReader(str(pdf_path)).pages]
    except Exception:
        return []


def _pdf_text_bounds(pdf_path: Path, *, pages: tuple[int, ...]) -> dict[int, list[dict[str, Any]]]:
    if not pdf_path.exists():
        return {}
    try:
        import fitz
    except ImportError:
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    document = fitz.open(pdf_path)
    try:
        for page_number in pages:
            if page_number < 1 or page_number > len(document):
                result[page_number] = []
                continue
            page = document[page_number - 1]
            blocks: list[dict[str, Any]] = []
            for block in page.get_text("blocks"):
                text = str(block[4] or "").strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "x0": round(float(block[0]), 2),
                        "x1": round(float(block[2]), 2),
                        "page_width": round(float(page.rect.width), 2),
                        "text": re.sub(r"\s+", " ", text)[:240],
                    }
                )
            result[page_number] = blocks
    finally:
        document.close()
    return result


def _overflow_items(bounds: dict[int, list[dict[str, Any]]], *, margin: float = 35.0) -> dict[int, list[dict[str, Any]]]:
    overflow: dict[int, list[dict[str, Any]]] = {}
    for raw_page, blocks in bounds.items():
        page = int(raw_page)
        for block in blocks:
            x0 = float(block.get("x0") or 0.0)
            x1 = float(block.get("x1") or 0.0)
            width = float(block.get("page_width") or 0.0)
            if width > 0 and (x0 < margin or x1 > width - margin):
                overflow.setdefault(page, []).append(block)
    return overflow


def _render_taskbook_evidence(pdf_path: Path, harness: Path) -> tuple[dict[str, str], str | None]:
    executable = shutil.which("pdftoppm")
    if not executable:
        return {}, "pdftoppm not found; task-book PNG evidence was not rendered"
    paths: dict[str, str] = {}
    for pdf_page, name in ((3, "taskbook_page_1"), (4, "taskbook_page_2")):
        prefix = harness / name
        completed = subprocess.run(
            [executable, "-png", "-f", str(pdf_page), "-l", str(pdf_page), "-singlefile", str(pdf_path), str(prefix)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        png = prefix.with_suffix(".png")
        if completed.returncode != 0 or not png.exists():
            return paths, f"pdftoppm failed for PDF page {pdf_page}: {completed.stderr.strip()}"
        paths[name] = str(png)
    return paths, None
