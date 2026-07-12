from __future__ import annotations

from buaa_thesis_kit.models import ThesisModel


def abstract_placeholders(model: ThesisModel, title_en_lines: list[str] | None = None) -> dict[str, str]:
    front = model.front_matter
    title_lines = title_en_lines or []
    return {
        "ABSTRACT_CN": _front_value(front, "chinese_abstract", "abstract_cn", "cn_abstract"),
        "KEYWORDS_CN": _front_value(front, "keywords_cn", "chinese_keywords", "cn_keywords", "keywords"),
        "TITLE_EN_LINE1": title_lines[0] if title_lines else model.metadata.title_en,
        "TITLE_EN_LINE2": title_lines[1] if len(title_lines) > 1 else "",
        "AUTHOR_EN": _front_value(front, "author_en") or model.metadata.student_name,
        "TUTOR_EN": _front_value(front, "tutor_en") or model.metadata.advisor,
        "ABSTRACT_EN": _front_value(front, "english_abstract", "abstract_en", "en_abstract"),
        "KEYWORDS_EN": _front_value(front, "keywords_en", "english_keywords", "en_keywords"),
    }


def _front_value(front_matter: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = front_matter.get(key)
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value if str(item).strip())
        text = str(value or "").strip()
        if text:
            return text
    return ""

