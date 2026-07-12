from __future__ import annotations

from copy import deepcopy
from typing import Any


BUAA_STYLES: dict[str, dict[str, Any]] = {
    "CoverTitle": {
        "font": "SimHei",
        "size_pt": 28,
        "alignment": "center",
    },
    "CoverThesisTitle": {
        "font": "SimHei",
        "size_pt": 18,
        "bold": True,
        "alignment": "center",
    },
    "CoverFieldLabel": {
        "font": "SimSun",
        "size_pt": 14,
        "character_spacing": "expanded",
        "alignment": "distributed",
    },
    "CoverFieldValue": {
        "font": "SimSun",
        "size_pt": 14,
        "alignment": "center",
    },
    "TaskBookTitle": {
        "font": "SimHei",
        "size_pt": 16,
        "alignment": "center",
        "space_after_pt": 12,
    },
    "TaskBookHeading": {
        "font": "SimHei",
        "size_pt": 12,
        "bold": True,
        "space_before_pt": 8,
        "space_after_pt": 4,
    },
    "TaskBookBody": {
        "font": "SimSun",
        "font_en": "Times New Roman",
        "size_pt": 12,
        "line_spacing_pt": 20,
        "first_line_indent_chars": 2,
    },
    "TaskBookReference": {
        "font": "SimSun",
        "font_en": "Times New Roman",
        "size_pt": 12,
        "line_spacing_pt": 20,
        "hanging_indent_chars": 2,
    },
    "DeclarationTitle": {
        "font": "SimHei",
        "size_pt": 16,
        "alignment": "center",
        "space_after_pt": 36,
    },
    "DeclarationBody": {
        "font": "SimSun",
        "size_pt": 12,
        "line_spacing_pt": 24,
        "first_line_indent_chars": 2,
    },
    "DeclarationSignature": {
        "font": "SimSun",
        "size_pt": 12,
        "line_spacing_pt": 24,
        "tab_stops": "right",
    },
    "AbstractTitleCN": {
        "font": "SimHei",
        "size_pt": 16,
        "alignment": "center",
    },
    "AbstractBodyCN": {
        "font": "SimSun",
        "size_pt": 12,
        "line_spacing_pt": 24,
        "first_line_indent_chars": 2,
    },
    "AbstractTitleEN": {
        "font": "Times New Roman",
        "size_pt": 16,
        "bold": True,
        "alignment": "center",
    },
    "AbstractBodyEN": {
        "font": "Times New Roman",
        "size_pt": 12,
        "line_spacing_pt": 24,
    },
    "TOCTitle": {
        "font": "SimHei",
        "size_pt": 18,
        "alignment": "center",
        "space_after_pt": 24,
    },
    "TOC1": {
        "font": "SimSun",
        "size_pt": 12,
        "left_indent_chars": 0,
        "right_tab_with_dot_leader": True,
    },
    "TOC2": {
        "font": "SimSun",
        "size_pt": 12,
        "left_indent_chars": 2,
        "right_tab_with_dot_leader": True,
    },
    "TOC3": {
        "font": "SimSun",
        "size_pt": 12,
        "left_indent_chars": 4,
        "right_tab_with_dot_leader": True,
    },
    "BodyHeading1": {
        "font": "SimHei",
        "size_pt": 16,
        "bold": True,
        "alignment": "center",
        "page_break_before": True,
    },
    "BodyHeading2": {
        "font": "SimHei",
        "size_pt": 12,
        "bold": True,
        "alignment": "left",
        "page_break_before": False,
    },
    "BodyNormal": {
        "font": "SimSun",
        "font_en": "Times New Roman",
        "size_pt": 12,
        "line_spacing_pt": 20,
        "first_line_indent_chars": 2,
    },
}


def get_style(name: str) -> dict[str, Any]:
    return deepcopy(BUAA_STYLES[name])


def style_size_pt(name: str) -> float:
    return float(BUAA_STYLES[name]["size_pt"])
