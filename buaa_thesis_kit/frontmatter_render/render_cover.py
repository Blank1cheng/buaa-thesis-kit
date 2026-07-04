from __future__ import annotations

from buaa_thesis_kit.models import ThesisModel


def cover_placeholders(model: ThesisModel, title_lines: list[str]) -> dict[str, str]:
    metadata = model.metadata
    return {
        "UNIT_CODE": metadata.unit_code or "10006",
        "STUDENT_ID": metadata.student_id,
        "CLASSIFICATION": metadata.classification,
        "TITLE_CN": metadata.title_cn or metadata.title_en,
        "TITLE_CN_LINE1": title_lines[0] if title_lines else "",
        "TITLE_CN_LINE2": title_lines[1] if len(title_lines) > 1 else "",
        "COLLEGE": metadata.college,
        "MAJOR": metadata.major,
        "STUDENT_NAME": metadata.student_name,
        "ADVISOR": metadata.advisor,
        "DATE_YEAR_MONTH": metadata.date,
    }

