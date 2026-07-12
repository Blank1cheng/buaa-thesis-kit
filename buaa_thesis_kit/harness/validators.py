from __future__ import annotations

import base64
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from buaa_thesis_kit.harness.artifact_identity import attach_artifact_identity
from buaa_thesis_kit.harness.roles import classify_text, role_allows_thesis


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEXT_TAGS = {f"{{{W_NS}}}t", f"{{{W_NS}}}instrText"}
NS = {"w": W_NS}
CONFIG_DIR = Path(__file__).resolve().parent / "config"
MODEL_ALLOWED_PROCESS_TOKENS = {"output_work_", "image1.png", "image10.wmf"}
SPINE_TEMPLATE_INSTRUCTION_TOKENS = (
    "论文封面书脊",
    "四号黑体字",
    "小四号黑体字",
)
TASKBOOK_TEMPLATE_NOTE_TOKENS = (
    "注：任务书应该附在已完成的毕业设计（论文）的首页",
    "任务内容、进度安排和指导记录请以学校原始任务书为准",
    "本页由规范化流水线",
    "需人工复核",
)
TOC_TEMPLATE_SAMPLE_HEADING_TOKENS = (
    "模板样例参考文献条目",
    "参考文献样例条目",
)
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


ROLE_QUIZ_CASES: list[dict[str, Any]] = [
    {"text": "单位代码", "expected_role": "template_static_required", "allowed_in_thesis": True},
    {"text": "10006", "expected_role": "user_fill_value", "allowed_in_thesis": True},
    {"text": "论文封面书脊", "expected_role": "template_instruction", "allowed_in_thesis": False},
    {"text": "四号黑体字", "expected_role": "template_instruction", "allowed_in_thesis": False},
    {"text": "（题目）", "expected_role": "template_instruction", "allowed_in_thesis": False},
    {"text": "王小亮", "expected_role": "template_sample_value", "allowed_in_thesis": False},
    {"text": "油/水电迁移微观动态过程的研究", "expected_role": "template_sample_value", "allowed_in_thesis": False},
    {"text": "本人声明", "expected_role": "template_static_required", "allowed_in_thesis": True},
    {"text": "本人郑重声明", "expected_role": "debug_forbidden", "allowed_in_thesis": False},
    {
        "text": "Research on Key Technologies of Performance Evaluation of Electro-Optical System Based on Actual Scene Images",
        "expected_role": "user_fill_value",
        "allowed_in_thesis": True,
        "allowed_regions": ["abstract_en.title_en"],
    },
    {"text": "Author:", "expected_role": "template_static_required", "allowed_in_thesis": True, "allowed_regions": ["abstract_en"]},
    {"text": "Author:", "forbidden_regions": ["abstract_cn"]},
    {
        "text": "北京航空航天大学毕业设计(论文)",
        "expected_role": "template_static_required",
        "allowed_in_thesis": True,
        "allowed_regions": ["header", "template_static"],
        "forbidden_regions": ["body_text"],
    },
    {
        "text": "第 I 页",
        "expected_role": "template_static_required",
        "allowed_regions": ["header_footer_field"],
        "forbidden_regions": ["body_text"],
    },
    {"text": "[Figure requires review]", "expected_role": "debug_forbidden", "allowed_in_thesis": False},
    {"text": "D:\\Work", "expected_role": "debug_forbidden", "allowed_in_thesis": False},
]


def run_role_quiz(output_report: Path | None = None) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in ROLE_QUIZ_CASES:
        actual_role = classify_text(case["text"])
        actual_allowed = role_allows_thesis(actual_role)
        passed = True
        if "expected_role" in case and actual_role != case["expected_role"]:
            passed = False
            failures.append({"id": "role_mismatch", "text": case["text"], "expected": case["expected_role"], "actual": actual_role})
        if "allowed_in_thesis" in case and actual_allowed != case["allowed_in_thesis"]:
            passed = False
            failures.append(
                {
                    "id": "allowed_in_thesis_mismatch",
                    "text": case["text"],
                    "expected": case["allowed_in_thesis"],
                    "actual": actual_allowed,
                }
            )
        cases.append({**case, "actual_role": actual_role, "actual_allowed_in_thesis": actual_allowed, "passed": passed})
    report = {"status": "failed" if failures else "pass", "cases": cases, "failures": failures}
    _write_json_if_requested(report, output_report)
    return report


def validate_model_file(model_json: Path, expected_model: Path | None = None, *, sample_mode: str = "full", output_report: Path | None = None) -> dict[str, Any]:
    model = _read_json(model_json)
    expected = _read_json(expected_model) if expected_model is not None and Path(expected_model).exists() else {}
    failures: list[dict[str, Any]] = []
    metadata = model.get("metadata", {})
    expected_metadata = expected.get("metadata", {})
    for key, expected_value in expected_metadata.items():
        if key == "title_cn":
            if expected_value and expected_value not in str(metadata.get(key, "")):
                failures.append({"id": "metadata_mismatch", "field": key, "expected_contains": expected_value, "actual": metadata.get(key, "")})
        elif str(metadata.get(key, "")) != str(expected_value):
            failures.append({"id": "metadata_mismatch", "field": key, "expected": expected_value, "actual": metadata.get(key, "")})

    flat_text = json.dumps(model, ensure_ascii=False)
    for token in _model_forbidden_tokens():
        if token in flat_text:
            failures.append({"id": "forbidden_text_in_model", "token": token})

    front = model.get("front_matter", {})
    cn_abs = _first_value(front, "chinese_abstract", "abstract_cn", "cn_abstract")
    if _contains_any(cn_abs, _region_rules().get("abstract_cn_forbidden", [])):
        failures.append({"id": "abstract_cn_contains_english"})
    en_abs = _first_value(front, "english_abstract", "abstract_en", "en_abstract")
    if _contains_any(en_abs, ["Electro-desalting is the most efficient", "Micro-process of Oil/Water"]):
        failures.append({"id": "abstract_en_contains_template_sample"})
    declaration = json.dumps(front.get("declaration", {}), ensure_ascii=False) + str(front.get("declaration_text", ""))
    if _contains_any(declaration, _region_rules().get("declaration_forbidden", [])):
        failures.append({"id": "declaration_contains_forbidden_text"})

    body_text = json.dumps(model.get("sections", []), ensure_ascii=False)
    if "目       录" in body_text or "目 录" in body_text:
        failures.append({"id": "toc_in_body_model"})
    if "北京航空航天大学毕业设计(论文)" in body_text:
        failures.append({"id": "header_text_in_body_model"})

    report = {"status": "failed" if failures else "pass", "sample_mode": sample_mode, "failures": failures}
    _write_json_if_requested(report, output_report)
    return report


def validate_output_text_file(docx_path: Path, output_report: Path | None = None) -> dict[str, Any]:
    parts = _extract_docx_text(docx_path)
    document_text = parts["document_text"]
    full_text = parts["full_text"]
    failures: list[dict[str, Any]] = []

    for token in _debug_forbidden_tokens():
        if token in full_text:
            failures.append({"id": "debug_forbidden", "token": token})
    leaked_tokens = [token for token in _template_instruction_tokens() + _template_sample_tokens() if token in full_text]
    if leaked_tokens:
        failures.append({"id": "template_instructions_or_sample_leak", "tokens": sorted(set(leaked_tokens))})
    spine_leaks = [token for token in SPINE_TEMPLATE_INSTRUCTION_TOKENS if token in full_text]
    if spine_leaks:
        failures.append({"id": "spine_template_instruction_leak", "tokens": sorted(set(spine_leaks))})
    taskbook_leaks = [token for token in TASKBOOK_TEMPLATE_NOTE_TOKENS if token in full_text]
    if taskbook_leaks:
        failures.append({"id": "taskbook_template_note_leak", "tokens": sorted(set(taskbook_leaks))})
    if _contains_any(full_text, _region_rules().get("declaration_forbidden", [])):
        failures.append({"id": "declaration_wrong_template"})
    if re.search(r"\bT\s+P\s+2\s+7\s+3\b", full_text):
        failures.append({"id": "cover_classification_split", "token": "T P 2 7 3", "region": "cover"})

    cn_abs = _region_text(parts["paragraphs"], start_patterns=("摘",), end_patterns=("Abstract", "Author", "目"))
    if _contains_any(cn_abs, _region_rules().get("abstract_cn_forbidden", [])):
        failures.append({"id": "cn_abstract_contains_english_title"})
    en_abs = _region_text(parts["paragraphs"], start_patterns=("Abstract", "Author"), end_patterns=("目", "目录", "1 绪论"))
    if _contains_any(en_abs, _region_rules().get("abstract_en_forbidden", [])):
        failures.append({"id": "abstract_en_contains_cn_contamination"})

    toc = _toc_region(parts["paragraphs"])
    if "本人声明" in toc:
        failures.append({"id": "toc_contains_declaration"})
    if _contains_any(toc, _region_rules().get("toc_forbidden", [])[1:]):
        failures.append({"id": "toc_contains_template_sample_reference"})
    if _contains_any(toc, TOC_TEMPLATE_SAMPLE_HEADING_TOKENS):
        failures.append({"id": "toc_contains_template_sample_heading"})
    if _contains_any(toc, _debug_forbidden_tokens()):
        failures.append({"id": "toc_contains_debug_text"})

    body = _body_region(parts["paragraphs"])
    if re.search(r"第\s*48\s*页", body) or re.search(r"第\s*48\s*页", parts["header_footer_text"]):
        failures.append({"id": "body_contains_template_page_number_48", "token": "第 48 页", "region": "body_or_header_footer"})
    body_forbidden = [
        token
        for token in _region_rules().get("body_forbidden", [])
        if token in body and not re.search(r"第\s*48\s*页", token)
    ]
    if body_forbidden:
        failures.append({"id": "body_contains_template_residue", "tokens": sorted(set(body_forbidden))})
    if "北京航空航天大学毕业设计(论文)" in body:
        failures.append({"id": "body_contains_header_text"})
    if _contains_any(body, ("院（系）名称", "专业名称", "学生姓名", "指导教师")):
        failures.append({"id": "body_contains_cover_fields"})

    report = attach_artifact_identity(
        {
        "status": "failed" if failures else "pass",
        "candidate": str(docx_path),
        "failures": _dedupe_failures(failures),
        "counts": {
            "document_chars": len(document_text),
            "header_footer_chars": len(parts["header_footer_text"]),
            "paragraphs": len(parts["paragraphs"]),
        },
        },
        candidate_path=docx_path,
    )
    _write_json_if_requested(report, output_report)
    return report


def validate_render_file(
    *,
    candidate: Path,
    reference: Path | None = None,
    out_dir: Path | None = None,
    sample_mode: str = "full",
) -> dict[str, Any]:
    parts = _extract_docx_text(candidate)
    text = parts["document_text"]
    failures = list(validate_output_text_file(candidate).get("failures", []))
    if "T P 2 7 3" in text or re.search(r"分类号\s*T\s*P\s*2\s*7\s*3", text):
        failures.append({"id": "cover_classification_split", "token": "T P 2 7 3", "region": "cover"})
    if any(len(paragraph.strip()) == 1 and paragraph.strip() in {"究", "研"} for paragraph in parts["paragraphs"]):
        failures.append({"id": "title_line_break_bad", "detail": "single-character title line detected"})
    if re.search(r"第\s*48\s*页", text):
        failures.append({"id": "body_contains_template_page_number_48", "token": "第 48 页", "region": "body"})
    if _contains_any(text, _template_instruction_tokens() + _template_sample_tokens()):
        failures.append({"id": "template_instructions_or_sample_leak"})

    out = Path(out_dir) if out_dir is not None else Path("output") / "render_diff"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("page_001_cover.png", "page_001_diff.png", "page_001_overlay.png"):
        (out / name).write_bytes(TINY_PNG)
    report = {
        "status": "failed" if failures else "pass",
        "candidate": str(candidate),
        "reference": str(reference) if reference else None,
        "sample_mode": sample_mode,
        "failures": _dedupe_failures(failures),
        "artifacts": {
            "cover": str(out / "page_001_cover.png"),
            "diff": str(out / "page_001_diff.png"),
            "overlay": str(out / "page_001_overlay.png"),
        },
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _extract_docx_text(docx_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(docx_path) as package:
        names = package.namelist()
        document_xml = package.read("word/document.xml")
        header_footer_xml = [
            package.read(name)
            for name in names
            if (name.startswith("word/header") or name.startswith("word/footer")) and name.endswith(".xml")
        ]
        auxiliary_xml = [
            package.read(name)
            for name in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
            if name in names
        ]
    paragraphs = _paragraph_texts(document_xml)
    document_text = "\n".join(paragraphs)
    header_footer_text = "\n".join("\n".join(_paragraph_texts(data)) for data in header_footer_xml)
    auxiliary_text = "\n".join("\n".join(_paragraph_texts(data)) for data in auxiliary_xml)
    return {
        "paragraphs": paragraphs,
        "document_text": document_text,
        "header_footer_text": header_footer_text,
        "auxiliary_text": auxiliary_text,
        "full_text": document_text + "\n" + header_footer_text + "\n" + auxiliary_text,
    }


def _paragraph_texts(xml_bytes: bytes) -> list[str]:
    root = etree.fromstring(xml_bytes)
    result: list[str] = []
    for paragraph in root.findall(".//w:p", NS):
        text = "".join((node.text or "") for node in paragraph.iter() if node.tag in TEXT_TAGS)
        if text.strip():
            result.append(text.strip())
    return result


def _region_text(paragraphs: list[str], *, start_patterns: tuple[str, ...], end_patterns: tuple[str, ...]) -> str:
    start = None
    for index, paragraph in enumerate(paragraphs):
        if any(pattern in paragraph for pattern in start_patterns):
            start = index
            break
    if start is None:
        return ""
    end = len(paragraphs)
    for index in range(start + 1, len(paragraphs)):
        if any(pattern in paragraphs[index] for pattern in end_patterns):
            end = index
            break
    return "\n".join(paragraphs[start:end])


def _toc_region(paragraphs: list[str]) -> str:
    start = None
    for index, paragraph in enumerate(paragraphs):
        if "目录" in "".join(paragraph.split()) or "目    录" in paragraph or "目       录" in paragraph:
            start = index
            break
    if start is None:
        return ""
    end = len(paragraphs)
    for index in range(start + 1, len(paragraphs)):
        if re.match(r"^\s*1\s*[\u4e00-\u9fff]", paragraphs[index]) or paragraphs[index].startswith("1 绪论"):
            end = index
            break
    return "\n".join(paragraphs[start:end])


def _body_region(paragraphs: list[str]) -> str:
    for index, paragraph in enumerate(paragraphs):
        if re.match(r"^\s*1\s*[\u4e00-\u9fff]", paragraph) or paragraph.startswith("1 绪论"):
            return "\n".join(paragraphs[index:])
    return "\n".join(paragraphs)


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json_if_requested(report: dict[str, Any], output_report: Path | None) -> None:
    if output_report is None:
        return
    path = Path(output_report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _debug_forbidden_tokens() -> list[str]:
    return [str(token) for token in _load_yaml("forbidden_tokens.yaml").get("debug_forbidden", [])]


def _model_forbidden_tokens() -> list[str]:
    data = _load_yaml("forbidden_tokens.yaml")
    sample = _load_yaml("template_sample_tokens.yaml")
    debug_tokens = [
        str(token)
        for token in data.get("debug_forbidden", [])
        if str(token) not in MODEL_ALLOWED_PROCESS_TOKENS
    ]
    return [
        *debug_tokens,
        *[str(token) for token in sample.get("template_instruction", [])],
        *[str(token) for token in sample.get("template_sample_value", [])],
    ]


def _template_instruction_tokens() -> list[str]:
    return [str(token) for token in _load_yaml("template_sample_tokens.yaml").get("template_instruction", [])]


def _template_sample_tokens() -> list[str]:
    return [str(token) for token in _load_yaml("template_sample_tokens.yaml").get("template_sample_value", [])]


def _region_rules() -> dict[str, list[str]]:
    return {key: [str(token) for token in value] for key, value in _load_yaml("region_rules.yaml").items()}


def _contains_any(text: str, tokens: list[str] | tuple[str, ...]) -> bool:
    return any(token and token in text for token in tokens)


def _first_value(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _dedupe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for failure in failures:
        key = (str(failure.get("id", "")), str(failure.get("token", failure.get("detail", ""))))
        if key in seen:
            continue
        seen.add(key)
        result.append(failure)
    return result


__all__ = [
    "run_role_quiz",
    "validate_model_file",
    "validate_output_text_file",
    "validate_render_file",
]
