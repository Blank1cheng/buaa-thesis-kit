from __future__ import annotations

from buaa_thesis_kit.models import Metadata


UNIVERSITY_NAME = "北京航空航天大学"


def spine_placeholders(metadata: Metadata) -> dict[str, str]:
    return {
        "TITLE_CN": metadata.title_cn or metadata.title_en,
        "STUDENT_NAME": metadata.student_name,
        "UNIVERSITY": UNIVERSITY_NAME,
        "DATE_YEAR_MONTH": metadata.date,
    }

