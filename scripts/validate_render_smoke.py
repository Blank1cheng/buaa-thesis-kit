from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.artifact_identity import attach_artifact_identity
from buaa_thesis_kit.pdf_export import export_pdf_from_docx


PAGE_NAMES = (
    "cover",
    "spine",
    "taskbook",
    "declaration",
    "abstract_cn",
    "abstract_en",
    "toc",
    "body",
)
FORBIDDEN_ANY = (
    "\u8bba\u6587\u5c01\u9762\u4e66\u810a",
    "\u56db\u53f7\u9ed1\u4f53\u5b57",
    "\u5c0f\u56db\u53f7\u9ed1\u4f53\u5b57",
    "\u672c\u9875\u7531\u89c4\u8303\u5316\u6d41\u6c34\u7ebf",
    "\u9700\u4eba\u5de5\u590d\u6838",
    "\u672c\u4eba\u90d1\u91cd\u58f0\u660e",
    "\u6307\u5bfc\u6559\u5e08\u7b7e\u540d",
    "Mao Xia",
    "\u5218\u56fd\u94a7",
    "T P 2 7 3",
    "\u7b2c 48 \u9875",
)


def validate_render_smoke(
    *,
    candidate: Path,
    out_dir: Path,
    existing_pdf: Path | None = None,
    sample_mode: str = "full",
    max_pages: int = 10,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    source = Path(candidate)
    pdf_path = _prepare_pdf(source, out, existing_pdf)
    failures: list[dict[str, Any]] = []
    page_images: list[str] = []
    page_texts: list[str] = []

    if pdf_path is None:
        failures.append(
            {
                "id": "render_smoke_pdf_export_failed",
                "region": "render_smoke",
                "message": "No usable PDF was available for render smoke validation.",
            }
        )
        report = _report(source, out, None, sample_mode, failures, page_images)
        _write_report(out, report)
        return report

    try:
        import fitz  # type: ignore[import-not-found]

        with fitz.open(str(pdf_path)) as document:
            if document.page_count == 0:
                failures.append({"id": "render_smoke_pdf_has_no_pages", "region": "render_smoke"})
            for page_index in range(min(max_pages, document.page_count)):
                page = document.load_page(page_index)
                page_texts.append(page.get_text("text"))
                page_role = PAGE_NAMES[page_index] if page_index < len(PAGE_NAMES) else f"page_{page_index + 1:03d}"
                image_path = out / f"page_{page_index + 1:03d}_{page_role}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                pixmap.save(str(image_path))
                page_images.append(str(image_path))
    except Exception as exc:
        failures.append({"id": "render_smoke_render_exception", "region": "render_smoke", "message": str(exc)})

    failures.extend(_page_rule_failures(page_texts))
    report = _report(source, out, pdf_path, sample_mode, _dedupe_failures(failures), page_images)
    _write_report(out, report)
    return report


def _prepare_pdf(candidate: Path, out: Path, existing_pdf: Path | None) -> Path | None:
    if existing_pdf is not None and Path(existing_pdf).exists():
        return Path(existing_pdf)
    if candidate.suffix.lower() == ".pdf" and candidate.exists():
        return candidate
    if candidate.suffix.lower() != ".docx":
        return None
    render_source = out / "render_source.docx"
    shutil.copy2(candidate, render_source)
    generated = out / "candidate.pdf"
    ok, _message = export_pdf_from_docx(render_source, generated)
    return generated if ok and generated.exists() else None


def _page_rule_failures(page_texts: list[str]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    all_text = "\n".join(page_texts)
    for token in FORBIDDEN_ANY:
        if token and token in all_text:
            failures.append({"id": _forbidden_reason(token), "region": _forbidden_region(token), "token": token})

    cover = page_texts[0] if page_texts else ""
    cover_missing = _missing_tokens(
        cover,
        {
            "unit_code": ("\u5355\u4f4d\u4ee3\u7801",),
            "student_id": ("\u5b66\u53f7",),
            "classification_label": ("\u5206\u7c7b\u53f7",),
            "classification_value": ("TP273",),
            "college": ("\u5b66\u9662", "\u9662"),
            "major": ("\u4e13\u4e1a",),
            "student_name": ("\u5b66\u751f\u59d3\u540d",),
            "advisor": ("\u6307\u5bfc\u6559\u5e08",),
        },
    )
    if cover_missing:
        failures.append({"id": "cover_missing_required_tokens", "region": "cover", "missing": cover_missing})
    if "T P 2 7 3" in cover:
        failures.append({"id": "cover_classification_split", "region": "cover", "token": "T P 2 7 3"})

    taskbook = _page_text(page_texts, 2)
    if taskbook and not _contains_any(
        taskbook,
        (
            "\u672c\u79d1\u6bd5\u4e1a\u8bbe\u8ba1\uff08\u8bba\u6587\uff09\u4efb\u52a1\u4e66",
            "\u672c\u79d1\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)\u4efb\u52a1\u4e66",
        ),
    ):
        failures.append({"id": "taskbook_title_missing", "region": "task_book"})

    declaration = _page_text(page_texts, 3)
    if declaration and not _contains_any(
        declaration,
        (
            "\u672c\u4eba\u58f0\u660e",
            "\u6211\u58f0\u660e\uff0c\u672c\u8bba\u6587\u53ca\u5176\u7814\u7a76\u5de5\u4f5c\u662f\u7531\u672c\u4eba\u5728\u5bfc\u5e08\u6307\u5bfc\u4e0b\u72ec\u7acb\u5b8c\u6210\u7684",
        ),
    ):
        failures.append({"id": "declaration_required_text_missing", "region": "declaration"})

    abstract_cn = _page_text(page_texts, 4)
    if abstract_cn:
        if not _contains_any(abstract_cn, ("\u6458", "\u8981", "\u5173\u952e\u8bcd")):
            failures.append({"id": "abstract_cn_required_text_missing", "region": "abstract_cn"})
        if _contains_any(abstract_cn, ("Research on", "Author:", "Tutor:")):
            failures.append({"id": "cn_abstract_contains_english_title", "region": "abstract_cn"})

    abstract_en = _page_text(page_texts, 5)
    if abstract_en and not _contains_any(abstract_en, ("Abstract", "Author", "Tutor", "Key Words", "Key words")):
        failures.append({"id": "abstract_en_required_text_missing", "region": "abstract_en"})

    toc = _page_text(page_texts, 6)
    if toc:
        if not _contains_any(toc, ("\u76ee\u5f55",)):
            failures.append({"id": "toc_title_missing", "region": "toc"})
        if _contains_any(
            toc,
            (
                "\u672c\u4eba\u58f0\u660e",
                "Mao Xia",
                "\u5218\u56fd\u94a7",
                "I\u7ea7\u53f6/\u76d8",
                "\u6a21\u677f\u53c2\u8003\u6587\u732e",
            ),
        ):
            failures.append({"id": "toc_contains_template_or_frontmatter_text", "region": "toc"})

    body = "\n".join(page_texts[7:])
    if body and _contains_any(body, ("\u7b2c 48 \u9875",)):
        failures.append({"id": "body_contains_template_page_number_48", "region": "body"})
    failures.extend(_semantic_smoke_failures(page_texts, failures))
    return failures


def _semantic_smoke_failures(page_texts: list[str], existing_failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    all_text = "\n".join(page_texts)
    failures: list[dict[str, Any]] = []
    existing_ids = {str(item.get("id", "")) for item in existing_failures}

    if "T P 2 7 3" in all_text or "cover_missing_required_tokens" in existing_ids:
        failures.append(
            {
                "id": "cover_metadata_misaligned",
                "region": "cover",
                "evidence_text": _first_matching_line(all_text, ("T P 2 7 3", "\u5b66    \u53f7", "\u5206\u7c7b\u53f7")),
            }
        )

    cover_text = "\n".join(page_texts[:2])
    if _cover_metadata_anchor_misaligned(cover_text, existing_ids):
        failures.append(
            {
                "id": "cover_metadata_anchor_misaligned",
                "region": "cover",
                "evidence_text": _first_matching_line(cover_text, ("\u5355 ", "\u5b66    \u53f7", "\u5206\u7c7b\u53f7")),
            }
        )
    if _cover_thesis_type_and_title_merged(cover_text):
        failures.append(
            {
                "id": "cover_thesis_type_and_title_merged",
                "region": "cover",
                "evidence_text": _first_matching_line(cover_text, ("\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)",)),
            }
        )
    if _cover_title_wrap_bad(cover_text):
        failures.append(
            {
                "id": "cover_title_orphan_or_bad_wrap",
                "region": "cover",
                "evidence_text": _title_wrap_evidence(cover_text),
            }
        )
        failures.append(
            {
                "id": "cover_title_layout_bad",
                "region": "cover",
                "evidence_text": _title_wrap_evidence(cover_text),
            }
        )
    if _cover_bottom_fields_missing(cover_text, existing_ids):
        failures.append(
            {
                "id": "cover_bottom_fields_missing_values",
                "region": "cover",
                "evidence_text": "cover bottom college/major/student/advisor fields are blank or not anchored to underline regions",
            }
        )
    if _cover_date_merged_into_advisor(cover_text):
        failures.append(
            {
                "id": "cover_date_merged_into_advisor",
                "region": "cover",
                "evidence_text": _first_matching_line(cover_text, ("\u6307\u5bfc\u6559\u5e08",)),
            }
        )

    declaration = _declaration_contamination_page(page_texts)
    if declaration:
        failures.append(
            {
                "id": "declaration_contamination",
                "region": "declaration",
                "evidence_text": _compact_after(declaration, "\u65f6\u95f4\uff1a", 80),
            }
        )

    if _frontmatter_has_blank_fields(all_text):
        failures.append(
            {
                "id": "frontmatter_blank_or_placeholder_fields",
                "region": "frontmatter",
                "evidence_text": "blank task/declaration/abstract metadata fields detected",
            }
        )

    if "taskbook_title_missing" in existing_ids or _taskbook_blank_or_placeholder_like(page_texts):
        failures.append(
            {
                "id": "taskbook_blank_or_placeholder_fields",
                "region": "task_book",
                "evidence_text": _taskbook_evidence(page_texts),
            }
        )

    abstract_failures = {
        "abstract_cn_required_text_missing",
        "abstract_en_required_text_missing",
        "cn_abstract_contains_english_title",
    }
    if abstract_failures.intersection(existing_ids) or _abstract_metadata_blank(all_text):
        failures.append(
            {
                "id": "abstract_render_smoke_failed",
                "region": "abstract",
                "evidence_text": "abstract page partition or author/tutor fields failed render smoke",
            }
        )
        failures.append(
            {
                "id": "abstract_region_issue",
                "region": "abstract",
                "evidence_text": "Chinese and English abstract regions are not separated or contain blank/template sample metadata.",
            }
        )
    if "toc_contains_template_or_frontmatter_text" in existing_ids or "toc_title_missing" in existing_ids:
        failures.append(
            {
                "id": "toc_template_sample_leak",
                "region": "toc",
                "evidence_text": _toc_evidence(page_texts),
            }
        )
    if _body_has_template_residue(page_texts):
        failures.append(
            {
                "id": "body_template_page_residue",
                "region": "body",
                "evidence_text": _body_residue_evidence(page_texts),
            }
        )
    return failures


def _page_text(page_texts: list[str], index: int) -> str:
    return page_texts[index] if len(page_texts) > index else ""


def _missing_tokens(text: str, required: dict[str, tuple[str, ...]]) -> list[str]:
    return [key for key, tokens in required.items() if not _contains_any(text, tokens)]


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token and token in text for token in tokens)


def _page_with_any(page_texts: list[str], tokens: tuple[str, ...]) -> str:
    for text in page_texts:
        if _contains_any(text, tokens):
            return text
    return ""


def _declaration_contamination_page(page_texts: list[str]) -> str:
    for text in page_texts:
        if "\u65f6\u95f4\uff1a" in text and "\u57fa\u4e8e\u5b9e\u62cd\u56fe" in text:
            return text
    return ""


def _first_matching_line(text: str, tokens: tuple[str, ...]) -> str:
    for line in text.splitlines():
        if _contains_any(line, tokens):
            return line.strip()
    return ""


def _cover_title_wrap_bad(text: str) -> bool:
    if "\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)\u57fa\u4e8e" in text:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) == 1 and "\u4e00" <= stripped <= "\u9fff":
            return True
    return False


def _cover_metadata_anchor_misaligned(text: str, existing_ids: set[str]) -> bool:
    if "cover_missing_required_tokens" in existing_ids:
        return True
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return "\u5355 10006" in compact or "\u5355\n" in compact or "10006\n\u5b66" not in compact


def _cover_thesis_type_and_title_merged(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if "\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)" in stripped and len(stripped) > len("\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)") + 2:
            return True
    return False


def _cover_bottom_fields_missing(text: str, existing_ids: set[str]) -> bool:
    if "cover_missing_required_tokens" in existing_ids:
        return True
    labels = ("\u5b66\u9662", "\u4e13\u4e1a", "\u5b66\u751f\u59d3\u540d", "\u6307\u5bfc\u6559\u5e08")
    return any(label in text for label in labels) and not _contains_any(text, ("\u5d14\u6da6\u660a", "\u5510\u837b\u97f3", "\u81ea\u52a8\u5316"))


def _cover_date_merged_into_advisor(text: str) -> bool:
    compact = "".join(text.split())
    return "\u6307\u5bfc\u6559\u5e082021" in compact or "\u6307\u5bfc\u6559\u5e082021\u5e74" in compact


def _title_wrap_evidence(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if "\u6bd5\u4e1a\u8bbe\u8ba1" in stripped or len(stripped) == 1:
            return stripped
    return "cover title wrapping is abnormal"


def _compact_after(text: str, token: str, limit: int) -> str:
    index = text.find(token)
    if index < 0:
        return ""
    return " ".join(text[index : index + limit].split())


def _frontmatter_has_blank_fields(text: str) -> bool:
    blank_patterns = (
        "\u5b66\u9662\uff08\u7cfb\uff09 \n\u5b66\u751f ",
        "\u5b66    \u751f\uff1a \n\u6307\u5bfc\u6559\u5e08\uff1a",
        "\u4f5c\u8005\uff1a  \n",
        "\u7b7e\u5b57\uff1a \n",
    )
    return _contains_any(text, blank_patterns)


def _abstract_metadata_blank(text: str) -> bool:
    return "\u5b66    \u751f\uff1a \n\u6307\u5bfc\u6559\u5e08\uff1a" in text


def _taskbook_blank_or_placeholder_like(page_texts: list[str]) -> bool:
    taskbook_region = "\n".join(page_texts[2:6])
    return _contains_any(
        taskbook_region,
        (
            "\u5b66\u9662\uff08\u7cfb\uff09 \n\u5b66\u751f ",
            "\u6bd5\u4e1a\u8bbe\u8ba1\uff08\u8bba\u6587\uff09\u65f6\u95f4\uff1a \n\u7b54\u8fa9\u65f6\u95f4\uff1a",
            "\u6307\u5bfc\u6559\u5e08\uff1a \n\u517c\u804c\u6559\u5e08\u6216\u7b54\u7591\u6559\u5e08",
        ),
    )


def _taskbook_evidence(page_texts: list[str]) -> str:
    taskbook_region = "\n".join(page_texts[2:6])
    return _first_matching_line(
        taskbook_region,
        (
            "\u5b66\u9662\uff08\u7cfb\uff09",
            "\u6bd5\u4e1a\u8bbe\u8ba1\uff08\u8bba\u6587\uff09\u65f6\u95f4",
            "\u6307\u5bfc\u6559\u5e08\uff1a",
        ),
    ) or "task book title/fields are blank, shifted, or placeholder-like"


def _toc_evidence(page_texts: list[str]) -> str:
    toc_region = "\n".join(page_texts[6:10])
    return _first_matching_line(
        toc_region,
        (
            "\u672c\u4eba\u58f0\u660e",
            "\u6a21\u677f\u53c2\u8003\u6587\u732e",
            "\u76ee       \u5f55",
            "\u53c2\u8003\u6587\u732e",
        ),
    ) or "TOC contains front-matter/template residue or is not isolated from current body headings"


def _body_has_template_residue(page_texts: list[str]) -> bool:
    body_region = "\n".join(page_texts[7:])
    return _contains_any(
        body_region,
        (
            "\u76ee       \u5f55",
            "\u7b2c 48 \u9875",
            "\u672c\u4eba\u58f0\u660e",
            "Author :",
            "Tutor :",
            "The transferring of water droplets",
            "\u53c2\u8003\u6587\u732e",
        ),
    )


def _body_residue_evidence(page_texts: list[str]) -> str:
    body_region = "\n".join(page_texts[7:])
    return _first_matching_line(
        body_region,
        (
            "\u76ee       \u5f55",
            "\u7b2c 48 \u9875",
            "\u672c\u4eba\u58f0\u660e",
            "Author :",
            "The transferring of water droplets",
            "\u53c2\u8003\u6587\u732e",
        ),
    ) or "body section contains page/template/front-matter residue"


def _forbidden_reason(token: str) -> str:
    if token in {"T P 2 7 3"}:
        return "cover_classification_split"
    if "48" in token:
        return "body_contains_template_page_number_48"
    if "\u4e66\u810a" in token:
        return "spine_template_instruction_leak"
    if "\u4eba\u5de5\u590d\u6838" in token or "\u6d41\u6c34\u7ebf" in token:
        return "taskbook_template_note_leak"
    return "render_smoke_forbidden_text"


def _forbidden_region(token: str) -> str:
    if token in {"T P 2 7 3"}:
        return "cover"
    if "48" in token:
        return "body"
    if "\u4e66\u810a" in token or "\u9ed1\u4f53" in token:
        return "spine"
    if "\u58f0\u660e" in token or "\u7b7e\u540d" in token:
        return "declaration"
    if "Mao Xia" in token or "\u5218\u56fd\u94a7" in token:
        return "toc"
    return "render_smoke"


def _dedupe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for failure in failures:
        key = (str(failure.get("id", "")), str(failure.get("region", "")), str(failure.get("token", failure.get("missing", ""))))
        if key in seen:
            continue
        seen.add(key)
        result.append(failure)
    return result


def _report(
    candidate: Path,
    out: Path,
    pdf_path: Path | None,
    sample_mode: str,
    failures: list[dict[str, Any]],
    page_images: list[str],
) -> dict[str, Any]:
    report = {
        "status": "failed" if failures else "pass",
        "candidate": str(candidate),
        "pdf": str(pdf_path) if pdf_path is not None else None,
        "sample_mode": sample_mode,
        "failures": failures,
        "artifacts": {
            "page_images": page_images,
            "out_dir": str(out),
        },
    }
    if candidate.exists() and candidate.is_file():
        report = attach_artifact_identity(report, candidate_path=candidate)
    return report


def _write_report(out: Path, report: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render and smoke-check the first pages of a BUAA thesis artifact.")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--existing-pdf", type=Path)
    parser.add_argument("--sample-mode", choices=("full", "truncated"), default="full")
    args = parser.parse_args(argv)
    report = validate_render_smoke(
        candidate=args.candidate,
        out_dir=args.out,
        existing_pdf=args.existing_pdf,
        sample_mode=args.sample_mode,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
