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
    "DeclarationTitle": {
        "font": "SimHei",
        "size_pt": 16,
        "alignment": "center",
    },
    "DeclarationBody": {
        "font": "SimSun",
        "size_pt": 12,
        "line_spacing_pt": 24,
        "first_line_indent_chars": 2,
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
    },
}


def get_style(name: str) -> dict[str, Any]:
    return deepcopy(BUAA_STYLES[name])


def style_size_pt(name: str) -> float:
    return float(BUAA_STYLES[name]["size_pt"])
