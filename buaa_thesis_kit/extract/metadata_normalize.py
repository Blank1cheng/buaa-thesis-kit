from __future__ import annotations

import re
from typing import Any


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = metadata.get("evidence") if isinstance(metadata.get("evidence"), dict) else {}
    return {
        "college": _field_report(
            "college",
            metadata.get("college"),
            _normalize_college(metadata.get("college")),
            evidence.get("college"),
            extra={"school_stem": _school_stem(metadata.get("college"))},
        ),
        "major": _field_report(
            "major",
            metadata.get("major"),
            _normalize_major(metadata.get("major")),
            evidence.get("major"),
            extra={
                "display_for_cover": _display_major_for_cover(metadata.get("major")),
                "display_for_taskbook": _normalize_major(metadata.get("major")),
                "major_class_display": _major_class_display(metadata.get("major")),
            },
        ),
        "class_name": _field_report(
            "class_name",
            metadata.get("class_name") or metadata.get("major"),
            _normalize_class_name(metadata.get("class_name") or metadata.get("major")),
            evidence.get("class_name") or evidence.get("major"),
            extra={"needs_review": _class_name_needs_review(metadata.get("class_name") or metadata.get("major"))},
        ),
        "advisor": _field_report("advisor", metadata.get("advisor"), _clean(metadata.get("advisor")), evidence.get("advisor")),
        "student_name": _field_report("student_name", metadata.get("student_name"), _clean(metadata.get("student_name")), evidence.get("student_name")),
        "date": _field_report("date", metadata.get("date"), _normalize_date(metadata.get("date")), evidence.get("date")),
    }


def normalized_metadata_values(metadata: dict[str, Any]) -> dict[str, Any]:
    report = normalize_metadata(metadata)
    values = dict(metadata)
    if report["college"]["normalized_value"]:
        values["college"] = report["college"]["normalized_value"]
        values["school_stem"] = report["college"]["school_stem"]
    if report["major"]["normalized_value"]:
        values["major_raw"] = report["major"]["raw_value"]
        values["major_normalized"] = report["major"]["normalized_value"]
        values["major"] = report["major"]["normalized_value"]
        values["major_display_for_cover"] = report["major"]["display_for_cover"]
        values["major_display_for_taskbook"] = report["major"]["display_for_taskbook"]
        values["major_class_display"] = report["major"]["major_class_display"]
    if report["class_name"]["normalized_value"]:
        values["class_name"] = report["class_name"]["normalized_value"]
    if report["date"]["normalized_value"]:
        values["date"] = report["date"]["normalized_value"]
    values["normalization"] = report
    return values


def _field_report(
    field: str,
    raw_value: Any,
    normalized_value: str,
    evidence: Any,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_dict = evidence if isinstance(evidence, dict) else {}
    report = {
        "field": field,
        "raw_value": _clean(raw_value),
        "normalized_value": normalized_value,
        "display_value": normalized_value,
        "source_page": evidence_dict.get("page_hint") or evidence_dict.get("source_page"),
        "source_region": evidence_dict.get("source_region") or "",
        "evidence_text": evidence_dict.get("evidence_text") or evidence_dict.get("evidence") or "",
        "confidence": float(evidence_dict.get("confidence") or 0.0),
    }
    if extra:
        report.update(extra)
    return report


def _normalize_college(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    match = re.search(r"([\u4e00-\u9fffA-Za-z]+学院)", text)
    return match.group(1) if match else text


def _school_stem(value: Any) -> str:
    text = _normalize_college(value)
    return text[:-2] if text.endswith("学院") else text


def _normalize_major(value: Any) -> str:
    text = _clean(value)
    text = re.sub(r"\d+\s*班", "", text)
    text = re.sub(r"(专业类|专业)", "", text)
    return text.strip()


def _display_major_for_cover(value: Any) -> str:
    return _normalize_major(value)


def _major_class_display(value: Any) -> str:
    major = _normalize_major(value)
    if not major:
        return ""
    return f"{major} 专业类" if "专业类" in _clean(value) else major


def _normalize_class_name(value: Any) -> str:
    match = re.search(r"(\d{4,})\s*班", _clean(value))
    return match.group(1) if match else ""


def _class_name_needs_review(value: Any) -> bool:
    text = _clean(value)
    return "班" in text and not _normalize_class_name(text)


def _normalize_date(value: Any) -> str:
    text = _clean(value)
    numbers = re.findall(r"\d+", text)
    if len(numbers) >= 2:
        return f"{numbers[0]} 年 {int(numbers[1])} 月"
    return text


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
