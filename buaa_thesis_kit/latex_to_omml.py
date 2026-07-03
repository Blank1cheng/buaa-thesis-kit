from __future__ import annotations

import re
from xml.sax.saxutils import escape


MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9_{}\\\s+\-*/=().,<>^]+$")
GREEK_MACROS = {
    "alpha": 0x03B1,
    "beta": 0x03B2,
    "gamma": 0x03B3,
    "delta": 0x03B4,
    "epsilon": 0x03B5,
    "theta": 0x03B8,
    "lambda": 0x03BB,
    "mu": 0x03BC,
    "pi": 0x03C0,
    "rho": 0x03C1,
    "sigma": 0x03C3,
    "tau": 0x03C4,
    "phi": 0x03C6,
    "omega": 0x03C9,
}
NARY_MACROS = {
    "sum": 0x2211,
    "int": 0x222B,
}


def latex_to_omml(latex: str) -> str:
    """Convert a small, safe subset of linear LaTeX-like math to editable OMML.

    This intentionally rejects macro-based or structurally ambiguous LaTeX. The
    caller can then keep those equations in the review ledger instead of silently
    producing incorrect editable math.
    """
    source = str(latex or "").strip()
    if not source or not SAFE_TEXT_RE.fullmatch(source):
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
        return self._parse_sequence()

    def _parse_sequence(self, stop_char: str = "") -> str:
        parts: list[str] = []
        while self.index < len(self.source):
            char = self.source[self.index]
            if stop_char and char == stop_char:
                break
            if char.isspace():
                self.index += 1
                continue
            if char == "\\":
                atom = self._parse_macro()
                if not atom:
                    return ""
                parts.append(atom)
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

    def _parse_macro(self) -> str:
        self.index += 1
        start = self.index
        while self.index < len(self.source) and self.source[self.index].isalpha():
            self.index += 1
        name = self.source[start : self.index]
        if name == "frac":
            numerator = self._parse_required_group()
            denominator = self._parse_required_group()
            if not numerator or not denominator:
                return ""
            return _fraction(numerator, denominator)
        if name == "sqrt":
            radicand = self._parse_required_group()
            if not radicand:
                return ""
            return _radical(radicand)
        if name in GREEK_MACROS:
            return self._apply_scripts(_run(chr(GREEK_MACROS[name])))
        if name in NARY_MACROS:
            scripts = self._consume_scripts()
            if scripts is None:
                return ""
            subscript, superscript = scripts
            return _nary(chr(NARY_MACROS[name]), subscript, superscript)
        return ""

    def _parse_required_group(self) -> str:
        if self._peek() != "{":
            return ""
        self.index += 1
        body = self._parse_sequence(stop_char="}")
        if not body or self._peek() != "}":
            return ""
        self.index += 1
        return body

    def _parse_identifier(self) -> str:
        base = self._consume_identifier()
        if not base:
            return ""
        return self._apply_scripts(_run(base))

    def _apply_scripts(self, base_run: str) -> str:
        scripts = self._consume_scripts()
        if scripts is None:
            return ""
        subscript, superscript = scripts
        if subscript and superscript:
            return _subscript_superscript(base_run, subscript, superscript)
        if subscript:
            return _subscript(base_run, subscript)
        if superscript:
            return _superscript(base_run, superscript)
        return base_run

    def _consume_scripts(self) -> tuple[str, str] | None:
        subscript = ""
        superscript = ""
        while self._peek() in {"_", "^"}:
            marker = self._peek()
            self.index += 1
            value = self._consume_script_omml()
            if not value:
                return None
            if marker == "_":
                if subscript:
                    return None
                subscript = value
            else:
                if superscript:
                    return None
                superscript = value
        return subscript, superscript

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

    def _consume_script_omml(self) -> str:
        if self._peek() == "{":
            end = _find_simple_group_end(self.source, self.index)
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
        return _run(value)

    def _peek(self) -> str:
        if self.index >= len(self.source):
            return ""
        return self.source[self.index]


def _run(text: str) -> str:
    return f"<m:r><m:t>{escape(text)}</m:t></m:r>"


def _subscript(base: str, subscript: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{subscript}</m:sub></m:sSub>"


def _fraction(numerator: str, denominator: str) -> str:
    return f"<m:f><m:num>{numerator}</m:num><m:den>{denominator}</m:den></m:f>"


def _radical(radicand: str) -> str:
    return f"<m:rad><m:deg/><m:e>{radicand}</m:e></m:rad>"


def _nary(symbol: str, subscript: str, superscript: str) -> str:
    return (
        f'<m:nary><m:naryPr><m:chr m:val="{escape(symbol)}"/>'
        '<m:limLoc m:val="undOvr"/></m:naryPr>'
        f"<m:sub>{subscript}</m:sub><m:sup>{superscript}</m:sup><m:e/></m:nary>"
    )


def _superscript(base: str, superscript: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{superscript}</m:sup></m:sSup>"


def _subscript_superscript(base: str, subscript: str, superscript: str) -> str:
    return (
        f"<m:sSubSup><m:e>{base}</m:e>"
        f"<m:sub>{subscript}</m:sub><m:sup>{superscript}</m:sup></m:sSubSup>"
    )


def _is_operator_char(char: str) -> bool:
    return char in "+-*/=(),<>"


def _find_simple_group_end(source: str, start: int) -> int:
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


__all__ = ["latex_to_omml"]
