from __future__ import annotations

import re
from typing import Any

from .metadata_normalize import normalized_metadata_values
from .reference_extract import merge_reference_entries


SECTION_PATTERNS = {
    "title": re.compile(r"^\s*(?:I|Ⅰ|一)[、.．]\s*毕业设计（论文）题目", re.IGNORECASE),
    "raw_materials": re.compile(r"^\s*(?:II|Ⅱ|二)[、.．]\s*毕业设计（论文）使用的原始资料", re.IGNORECASE),
    "work_content": re.compile(r"^\s*(?:III|Ⅲ|三)[、.．]\s*毕业设计（论文）工作内容", re.IGNORECASE),
    "references": re.compile(r"^\s*(?:IV|Ⅳ|四)[、.．]\s*主要参考资料", re.IGNORECASE),
}


def extract_task_book_from_blocks(blocks: list[Any], metadata: dict[str, Any]) -> dict[str, Any]:
    task_blocks = _task_book_blocks(blocks)
    metadata_values = normalized_metadata_values(metadata)
    sections: dict[str, list[str]] = {"title": [], "raw_materials": [], "work_content": [], "references": []}
    bottom: dict[str, str] = {}
    current: str | None = None
    block_records: list[dict[str, Any]] = []

    for block in task_blocks:
        text = _text(block)
        if not text:
            continue
        block_records.append({"index": getattr(block, "index", None), "text": text})
        section = _section_for_heading(text)
        if section:
            current = section
            inline = _inline_heading_value(text)
            if inline:
                sections[current].append(inline)
            continue
        if _capture_bottom_field(bottom, text):
            current = None if current == "references" else current
            continue
        if current in sections:
            sections[current].append(text)

    merged_references = merge_reference_entries(sections["references"], stop_predicate=_is_task_bottom_line)
    merged_references = [
        cleaned
        for item in merged_references
        if (cleaned := _trim_taskbook_footer_residue(item, metadata_values))
    ]
    references = [
        {
            "index": index + 1,
            "raw": item,
            "merged": item,
            "raw_lines": [item],
            "source": "task_book",
            "source_region": "task_book.references",
            "confidence": 0.92,
        }
        for index, item in enumerate(merged_references)
    ]
    bottom_major = bottom.get("major") or str(metadata_values.get("major_raw") or metadata_values.get("major") or "")
    bottom_class = bottom.get("class_name") or str(metadata_values.get("class_name") or "")
    bottom_normalized = normalized_metadata_values({**metadata_values, "major": bottom_major, "class_name": bottom_class})
    major_normalized = str(bottom_normalized.get("major_normalized") or bottom_normalized.get("major") or "")
    major_class_display = (
        f"{major_normalized} 专业类"
        if bottom.get("major") and major_normalized
        else str(bottom_normalized.get("major_class_display") or (f"{major_normalized} 专业类" if major_normalized else ""))
    )
    task = {
        "title": _join_lines(sections["title"]) or str(metadata_values.get("title_cn") or ""),
        "raw_materials": _join_lines(sections["raw_materials"]),
        "work_content": _join_lines(sections["work_content"]),
        "references": references,
        "college": bottom.get("college") or str(metadata_values.get("college") or ""),
        "major": major_normalized,
        "major_raw": bottom_major,
        "major_normalized": major_normalized,
        "major_class": major_normalized,
        "major_class_display": major_class_display,
        "class_name": bottom_class,
        "student_name": bottom.get("student_name") or str(metadata_values.get("student_name") or ""),
        "date_range": bottom.get("date_range", ""),
        "defense_date": bottom.get("defense_date", ""),
        "grade": bottom.get("grade", ""),
        "advisor": bottom.get("advisor") or str(metadata_values.get("advisor") or ""),
        "department_director": bottom.get("department_director", ""),
        "blocks": block_records,
    }
    task["bottom_fields"] = {
        "college": task["college"],
        "major": task["major"],
        "major_class": task["major_class_display"],
        "class_name": task["class_name"],
        "student_name": task["student_name"],
        "date_range": task["date_range"],
        "defense_date": task["defense_date"],
        "grade": task["grade"],
        "advisor": task["advisor"],
        "department_director": task["department_director"],
    }
    fallback_fields = []
    for field in ("college", "major", "major_class", "student_name", "advisor"):
        if not bottom.get("major" if field in {"major", "major_class"} else field) and task.get(field):
            fallback_fields.append(field)
    task["fallback_fields"] = fallback_fields
    task["missing_fields"] = [field for field in ("raw_materials", "work_content") if not task.get(field)]
    return task


def _task_book_blocks(blocks: list[Any]) -> list[Any]:
    start = None
    end = len(blocks)
    for index, block in enumerate(blocks):
        text = _text(block)
        compact = re.sub(r"\s+", "", text)
        if start is None and "任务书" in compact:
            start = index
            continue
        if start is not None and ("本人声明" in compact or compact == "摘要"):
            end = index
            break
    if start is None:
        return []
    return blocks[start:end]


def _section_for_heading(text: str) -> str | None:
    for name, pattern in SECTION_PATTERNS.items():
        if pattern.search(text):
            return name
    return None


def _inline_heading_value(text: str) -> str:
    parts = re.split(r"[:：]", text, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 and parts[1].strip() else ""


def _capture_bottom_field(bottom: dict[str, str], text: str) -> bool:
    if _is_task_bottom_line(text):
        if "学院" in text and "专业类" in text and "班" in text:
            _capture_college_major_class(bottom, text)
        elif text.startswith("学生"):
            bottom["student_name"] = _strip_label(text, "学生")
        elif text.startswith("毕业设计"):
            bottom["date_range"] = _strip_label(text, "毕业设计（论文）时间")
        elif text.startswith("答辩时间"):
            bottom["defense_date"] = _strip_label(text, "答辩时间")
        elif text.startswith("成绩") or text.startswith("成 绩"):
            bottom["grade"] = _strip_label(text, "成绩")
        elif text.startswith("指导教师"):
            bottom["advisor"] = _strip_label(text, "指导教师")
        elif "主任" in text:
            bottom["department_director"] = _strip_label(text, "系（教研室）主任（签字）")
        return True
    return False


def _capture_college_major_class(bottom: dict[str, str], text: str) -> None:
    match = re.search(r"(?P<college>.+?)\s*学院\s*(?P<major>.+?)\s*专业类\s*(?P<class>.*?)\s*班", text)
    if match:
        college = re.sub(r"\s+", "", match.group("college")) + "学院"
        major = re.sub(r"\s+", "", match.group("major"))
        bottom["college"] = college
        bottom["major"] = major
        bottom["class_name"] = re.sub(r"\s+", "", match.group("class"))


def _is_task_bottom_line(text: str) -> bool:
    return any(
        token in text
        for token in ("学院", "学生", "毕业设计（论文）时间", "答辩时间", "成绩", "成 绩", "指导教师", "主任（签字）")
    )


def _strip_label(text: str, label: str) -> str:
    value = text
    for token in (label, label.replace("（", "(").replace("）", ")")):
        value = value.replace(token, "")
    value = re.sub(r"^[：:\s]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line.strip() for line in lines if line.strip()).strip()


def _trim_taskbook_footer_residue(value: str, metadata: dict[str, Any]) -> str:
    text = str(value or "").strip()
    college = str(metadata.get("college") or "").strip()
    stems = {college}
    for suffix in ("学院", "学校", "系"):
        if college.endswith(suffix):
            stems.add(college[: -len(suffix)])
    for stem in sorted((item for item in stems if item), key=len, reverse=True):
        text = re.sub(rf"\s*{re.escape(stem)}\s*$", "", text).strip()
    return text


def _text(block: Any) -> str:
    return re.sub(r"\s+", " ", str(getattr(block, "text", block) or "")).strip()
