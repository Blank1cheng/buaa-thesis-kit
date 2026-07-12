from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


REQUIRED_UNDERGRADUATE_METADATA = ("title_cn", "student_name", "advisor", "college", "major", "date")
RECOMMENDED_METADATA = ("unit_code", "student_id", "classification")

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "unit_code": ("单位代码", "单位代号", "学校代码", "Unit Code", "Institution Code"),
    "student_id": ("学生学号", "学号", "Student ID", "Student No", "Student Number"),
    "classification": ("中图分类号", "分类号", "分 类 号", "Classification"),
    "college": ("院（系）名称", "院(系)名称", "学院名称", "学院", "院系", "College", "School"),
    "major": ("专业名称", "专业/班级", "专业", "Major"),
    "student_name": ("学生姓名", "学生", "作者"),
    "advisor": ("指导教师姓名", "指导教师", "指导老师", "导师"),
    "title_cn": ("毕业设计（论文）题目", "毕业设计(论文)题目", "论文题目", "题目"),
    "title_en": ("English Title", "Title in English"),
    "date": ("完成日期", "提交日期", "日期", "时间", "Date"),
}

REGION_PRIORITY = {
    "cover": 6,
    "task_book": 5,
    "abstract_cn": 4,
    "declaration": 3,
    "doc_props": 2,
    "body": 1,
    "filename": 0,
}

OFFICIAL_SAMPLE_VALUES = {
    "王小二",
    "黄欢",
    "李兴华",
    "Mao Xia",
    "刘国钧",
    "沧水电迁移",
}


def resolve_metadata_from_texts(
    items: list[str | dict[str, Any]],
    *,
    source_file: str,
    source_type: str,
    confidence_threshold: float = 0.75,
) -> dict[str, Any]:
    normalized_items = [_coerce_item(item, index, source_file, source_type) for index, item in enumerate(items)]
    candidates = _label_candidates(normalized_items)
    candidates.extend(_cover_position_candidates(normalized_items))
    candidates = [candidate for candidate in candidates if not _is_template_sample(candidate["value"])]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["field"]].append(candidate)

    resolved: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for field, field_candidates in grouped.items():
        ordered = sorted(
            field_candidates,
            key=lambda item: (
                float(item["confidence"]),
                REGION_PRIORITY.get(str(item.get("source_region") or ""), 0),
                -int(item.get("paragraph_index") or 0),
            ),
            reverse=True,
        )
        winner = ordered[0]
        if float(winner["confidence"]) >= confidence_threshold:
            resolved[field] = _public_candidate(winner)
        high_conflicts = [
            item
            for item in ordered[1:]
            if float(item["confidence"]) >= 0.8 and _value_key(item["value"]) != _value_key(winner["value"])
        ]
        if high_conflicts:
            conflicts.append(
                {
                    "field": field,
                    "chosen": winner["value"],
                    "candidates": [_public_candidate(item) for item in [winner, *high_conflicts]],
                }
            )

    expected = [*REQUIRED_UNDERGRADUATE_METADATA, *RECOMMENDED_METADATA]
    missing = [field for field in expected if field not in resolved]
    warnings = []
    for candidate in candidates:
        if candidate["field"] not in resolved:
            warnings.append(f"low confidence candidate ignored: {candidate['field']}")

    return {
        "resolved": resolved,
        "missing": missing,
        "conflicts": conflicts,
        "warnings": warnings,
        "candidates": [_public_candidate(candidate) for candidate in candidates],
    }


def _coerce_item(item: str | dict[str, Any], index: int, source_file: str, source_type: str) -> dict[str, Any]:
    if isinstance(item, dict):
        text = str(item.get("text") or "")
        return {
            "text": _clean_text(text),
            "source_file": str(item.get("source_file") or source_file),
            "source_type": str(item.get("source_type") or source_type),
            "source_page": item.get("source_page") or item.get("page") or item.get("page_hint") or 1,
            "source_region": str(item.get("source_region") or _region_for_index(index)),
            "paragraph_index": item.get("paragraph_index", index),
            "block_index": item.get("block_index", index),
            "method": str(item.get("method") or item.get("extractor_rule") or ""),
            "evidence_text": str(item.get("evidence_text") or text),
        }
    return {
        "text": _clean_text(str(item)),
        "source_file": source_file,
        "source_type": source_type,
        "source_page": 1,
        "source_region": _region_for_index(index),
        "paragraph_index": index,
        "block_index": index,
        "method": "",
        "evidence_text": _clean_text(str(item)),
    }


def _label_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        text = item["text"]
        if not text:
            continue
        for field, labels in FIELD_LABELS.items():
            if field in {"college", "major"} and _is_taskbook_college_major_class_line(text):
                continue
            if field == "date" and _is_taskbook_date_range_line(text):
                continue
            value = _extract_labeled_value(field, text, labels)
            if not value:
                continue
            candidates.append(_candidate(field, value, item, "label_value", _label_confidence(item)))
    return candidates


def _extract_labeled_value(field: str, text: str, labels: tuple[str, ...]) -> str:
    for label in sorted(labels, key=len, reverse=True):
        pattern = _flexible_label_pattern(label)
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if not _has_label_boundary(text, match):
            continue
        tail = text[match.end() :]
        tail = re.sub(r"^[\s:：\-—_/／（）()]+", "", tail)
        if not tail:
            continue
        tail = _truncate_at_next_label(tail)
        value = _clean_metadata_value(field, tail)
        if value:
            return value
    return ""


def _flexible_label_pattern(label: str) -> str:
    pieces = []
    for char in label:
        if char.isspace():
            pieces.append(r"\s*")
        else:
            pieces.append(re.escape(char) + r"\s*")
    return "".join(pieces).rstrip(r"\s*")


def _truncate_at_next_label(value: str) -> str:
    starts = []
    for labels in FIELD_LABELS.values():
        for label in labels:
            match = re.search(_flexible_label_pattern(label), value, flags=re.IGNORECASE)
            if match and match.start() > 0 and _has_label_boundary(value, match):
                starts.append(match.start())
    if starts:
        return value[: min(starts)]
    return value


def _cover_position_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_items = items[:30]
    title_index = _title_index(first_items)
    if title_index is None:
        return []
    title_item = first_items[title_index]
    title_value, title_span = _cover_title_value(first_items, title_index)
    candidates = [_candidate("title_cn", title_value, title_item, "cover_position", 0.86)]

    following = [
        item
        for item in first_items[title_index + title_span : title_index + title_span + 8]
        if item["text"] and not _contains_label(item["text"]) and not _is_structural_stop(item["text"])
    ]
    fields = ("college", "major", "student_name", "advisor")
    confidences = {"college": 0.88, "major": 0.86, "student_name": 0.84, "advisor": 0.84}
    for field, item in zip(fields, following):
        value = _clean_metadata_value(field, item["text"])
        if value:
            candidates.append(_candidate(field, value, item, "cover_position", confidences[field]))

    for item in first_items:
        date = _clean_metadata_value("date", item["text"])
        if date and not _contains_label(item["text"]):
            candidates.append(_candidate("date", date, item, "cover_position", 0.82))
            break
    return candidates


def _cover_title_value(items: list[dict[str, Any]], title_index: int) -> tuple[str, int]:
    title_parts = [items[title_index]["text"]]
    cursor = title_index + 1
    while cursor < min(len(items), title_index + 4):
        text = items[cursor]["text"]
        if not text or _contains_label(text) or _is_structural_stop(text) or _clean_metadata_value("date", text):
            break
        if text.endswith("学院") or text in {"自动化", "计算机科学与技术"}:
            break
        if 2 <= len(text) <= 30 and re.search(r"[\u4e00-\u9fff]", text):
            title_parts.append(text)
            cursor += 1
            continue
        break
    return "".join(title_parts), len(title_parts)


def _title_index(items: list[dict[str, Any]]) -> int | None:
    for index, item in enumerate(items):
        text = item["text"]
        if not (8 <= len(text) <= 120):
            continue
        if _contains_label(text) or _is_structural_stop(text) or _clean_metadata_value("date", text):
            continue
        if re.search(r"[\u4e00-\u9fff]", text) and not re.search(r"\d{8,}", text):
            return index
    return None


def _candidate(field: str, value: str, item: dict[str, Any], rule: str, confidence: float) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "confidence": round(confidence, 4),
        "source": item["source_region"],
        "source_region": item["source_region"],
        "source_page": item["source_page"],
        "source_file": item["source_file"],
        "source_type": item["source_type"],
        "paragraph_index": item["paragraph_index"],
        "block_index": item["block_index"],
        "evidence": item.get("evidence_text") or item["text"],
        "method": item.get("method") or "",
        "rule": rule,
    }


def _public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": candidate["field"],
        "value": candidate["value"],
        "confidence": candidate["confidence"],
        "source": candidate["source"],
        "source_region": candidate["source_region"],
        "source_page": candidate["source_page"],
        "source_file": candidate["source_file"],
        "source_type": candidate["source_type"],
        "paragraph_index": candidate["paragraph_index"],
        "block_index": candidate["block_index"],
        "evidence": candidate["evidence"],
        "method": candidate.get("method") or "",
        "rule": candidate["rule"],
    }


def _label_confidence(item: dict[str, Any]) -> float:
    region = str(item.get("source_region") or "")
    if region in {"cover", "task_book"}:
        return 0.95
    if region == "abstract_cn":
        return 0.84
    return 0.82


def _clean_metadata_value(field: str, value: str) -> str:
    value = _clean_text(value).strip(" :：,，;；-—_（）()[]")
    if not value:
        return ""
    if field == "student_id":
        match = re.search(r"\d{8,10}", value)
        return match.group(0) if match else ""
    if field == "unit_code":
        match = re.search(r"\d{5}", value)
        return match.group(0) if match else ""
    if field == "classification":
        compact = re.sub(r"\s+", "", value).upper()
        match = re.search(r"[A-Z]{1,4}\d{2,6}", compact)
        return match.group(0) if match else ""
    if field == "date":
        match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?", value)
        if match:
            year, month, day = match.groups()
            return f"{year} 年 {int(month)} 月" + (f" {int(day)} 日" if day else "")
        return ""
    if field in {"student_name", "advisor"}:
        value = re.split(r"\s+", value)[0]
        if not (2 <= len(value) <= 8):
            return ""
    if field == "major" and "/" in value:
        value = value.split("/", 1)[0].strip()
    return value


def _contains_label(text: str) -> bool:
    for labels in FIELD_LABELS.values():
        for label in labels:
            match = re.search(_flexible_label_pattern(label), text, flags=re.IGNORECASE)
            if match and _has_label_boundary(text, match):
                return True
    return False


def _has_label_boundary(text: str, match: re.Match[str]) -> bool:
    before = text[match.start() - 1] if match.start() > 0 else ""
    after = text[match.end()] if match.end() < len(text) else ""
    before_ok = not before or before.isspace() or before in ":：;；,，/／-—_（）()[]"
    after_ok = not after or after.isspace() or after in ":：;；,，/／-—_（）()[]"
    return before_ok and after_ok


def _is_structural_stop(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    return compact in {"摘要", "目录", "abstract", "毕业设计(论文)", "毕业设计（论文）"}


def _is_taskbook_college_major_class_line(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return "学院" in compact and "专业类" in compact and "班" in compact


def _is_taskbook_date_range_line(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return "毕业设计" in compact and "时间" in compact and "至" in compact


def _is_template_sample(value: str) -> bool:
    return _value_key(value) in {_value_key(item) for item in OFFICIAL_SAMPLE_VALUES}


def _value_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _region_for_index(index: int) -> str:
    if index < 12:
        return "cover"
    if index < 40:
        return "frontmatter"
    return "body"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\u3000", " ")).strip()
