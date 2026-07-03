from __future__ import annotations

import re
from xml.sax.saxutils import escape


MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9_{}\s+\-*/=().,<>^]+$")


def latex_to_omml(latex: str) -> str:
    """Convert a small, safe subset of linear LaTeX-like math to editable OMML.

    This intentionally rejects macro-based or structurally ambiguous LaTeX. The
    caller can then keep those equations in the review ledger instead of silently
    producing incorrect editable math.
    """
    source = str(latex or "").strip()
    if not source or "\\" in source or not SAFE_TEXT_RE.fullmatch(source):
        return ""

    parser = _LinearMathParser(source)
    body = parser.parse()
    if not body:
        return ""
    return f'<m:oMathPara xmlns:m="{MATH_NS}"><m:oMath>{body}</m:oMath></m:oMathPara>'


class _LinearMathParser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.index = 0

    def parse(self) -> str:
        parts: list[str] = []
        while self.index < len(self.source):
            char = self.source[self.index]
            if char.isspace():
                self.index += 1
                continue
            if _is_operator_char(char):
                parts.append(_run(char))
                self.index += 1
                continue
            if char.isalpha():
                atom = self._parse_identifier()
                if not atom:
                    return ""
                parts.append(atom)
                continue
            if char.isdigit():
                parts.append(_run(self._consume_number()))
                continue
            return ""
        return "".join(parts)

    def _parse_identifier(self) -> str:
        base = self._consume_identifier()
        if not base:
            return ""
        subscript = ""
        superscript = ""
        while self._peek() in {"_", "^"}:
            marker = self._peek()
            self.index += 1
            value = self._consume_script_value()
            if not value:
                return ""
            if marker == "_":
                if subscript:
                    return ""
                subscript = value
            else:
                if superscript:
                    return ""
                superscript = value
        base_run = _run(base)
        if subscript and superscript:
            return _subscript_superscript(base_run, _run(subscript), _run(superscript))
        if subscript:
            return _subscript(base_run, _run(subscript))
        if superscript:
            return _superscript(base_run, _run(superscript))
        return base_run

    def _consume_identifier(self) -> str:
        start = self.index
        self.index += 1
        while self.index < len(self.source) and self.source[self.index].isalnum():
            self.index += 1
        return self.source[start : self.index]

    def _consume_number(self) -> str:
        start = self.index
        while self.index < len(self.source) and (
            self.source[self.index].isdigit() or self.source[self.index] == "."
        ):
            self.index += 1
        return self.source[start : self.index]

    def _consume_script_value(self) -> str:
        if self._peek() == "{":
            end = self.source.find("}", self.index + 1)
            if end < 0:
                return ""
            value = self.source[self.index + 1 : end].strip()
            self.index = end + 1
        else:
            start = self.index
            while self.index < len(self.source) and (
                self.source[self.index].isalnum() or self.source[self.index] in "-+."
            ):
                self.index += 1
            value = self.source[start : self.index].strip()
        if not value or "{" in value or "}" in value or "_" in value or "^" in value:
            return ""
        return value

    def _peek(self) -> str:
        if self.index >= len(self.source):
            return ""
        return self.source[self.index]


def _run(text: str) -> str:
    return f"<m:r><m:t>{escape(text)}</m:t></m:r>"


def _subscript(base: str, subscript: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{subscript}</m:sub></m:sSub>"


def _superscript(base: str, superscript: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{superscript}</m:sup></m:sSup>"


def _subscript_superscript(base: str, subscript: str, superscript: str) -> str:
    return (
        f"<m:sSubSup><m:e>{base}</m:e>"
        f"<m:sub>{subscript}</m:sub><m:sup>{superscript}</m:sup></m:sSubSup>"
    )


def _is_operator_char(char: str) -> bool:
    return char in "+-*/=(),<>"


__all__ = ["latex_to_omml"]
