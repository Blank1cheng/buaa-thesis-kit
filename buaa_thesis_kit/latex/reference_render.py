from __future__ import annotations

import re
from typing import Any

from .escape import tex_escape, tex_escape_with_cjk_breaks


def main_references_tex(references: list[Any]) -> str:
    if not references:
        return '% !Mode:: "TeX:UTF-8"\n\\cleardoublepage\n'
    lines = [
        '% !Mode:: "TeX:UTF-8"',
        r"\cleardoublepage",
        r"\phantomsection",
        r"\addcontentsline{toc}{chapter}{参考文献}",
        r"\chapter*{参考文献}",
        r"\newcommand{\buaaMainReferenceEntry}[1]{%",
        r"  \par\noindent\hangindent=2em\hangafter=1 #1\par%",
        r"}",
    ]
    for ref in references:
        raw = ref.get("raw") if isinstance(ref, dict) else str(ref)
        lines.append(rf"\buaaMainReferenceEntry{{{tex_escape(raw)}}}")
    lines.append(r"\cleardoublepage")
    return "\n".join(lines) + "\n"


def assignment_reference_lines(references: list[str], count: int) -> list[str]:
    lines = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    return [_assignment_reference_tex(line) for line in (lines + [""] * count)[:count]]


def assignment_reference_block_macro(name: str, references: list[str]) -> str:
    lines = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    body = "\n".join(rf"  \buaaAssignRefParagraph{{{tex_escape_with_cjk_breaks(line)}}}" for line in lines)
    if not body:
        body = "  "
    return "\n".join([rf"\newcommand{{\{name}}}{{%", body, "}"])


def bad_reference_wrapping_detected(items: list[Any]) -> bool:
    for item in items:
        text = str(item.get("raw") if isinstance(item, dict) else item)
        if len(re.findall(r"\[\d+\]", text)) > 1:
            return True
        if re.search(r"[A-Z],(?=[A-Z][a-z])", text):
            return True
        if re.search(r"[a-z][A-Z](?=[\s.,;:])", text):
            return True
    return False


def _assignment_reference_tex(line: str) -> str:
    if not line:
        return ""
    return tex_escape(line)
