from __future__ import annotations

import unicodedata
from typing import Any


_TEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(value: Any) -> str:
    return "".join(_TEX_ESCAPE_MAP.get(char, char) for char in str(value or ""))


def tex_value(value: Any, empty: str = r"\mbox{}") -> str:
    text = str(value or "").strip()
    return tex_escape(text) if text else empty


def tex_escape_with_cjk_breaks(value: Any) -> str:
    text = str(value or "")
    rendered: list[str] = []
    for index, char in enumerate(text):
        rendered.append(_TEX_ESCAPE_MAP.get(char, char))
        if index + 1 < len(text) and (
            unicodedata.east_asian_width(char) in {"W", "F"} or char in {" ", "-", "/"}
        ):
            rendered.append(r"\allowbreak{}")
    return "".join(rendered)
