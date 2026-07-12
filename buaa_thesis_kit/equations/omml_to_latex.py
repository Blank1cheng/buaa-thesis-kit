from __future__ import annotations

import re
from typing import Any

from lxml import etree


class OmmlConversionError(ValueError):
    pass


SYMBOLS = {
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∮": r"\oint",
    "∞": r"\infty",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "×": r"\times",
    "·": r"\cdot",
    "±": r"\pm",
    "∂": r"\partial",
    "∇": r"\nabla",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "η": r"\eta",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "φ": r"\phi",
    "ω": r"\omega",
}


def omml_to_latex(omml: str) -> str:
    try:
        root = etree.fromstring(str(omml or "").encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise OmmlConversionError(f"invalid OMML: {exc}") from exc
    latex = _render(root).strip()
    if not latex:
        raise OmmlConversionError("OMML did not contain a renderable equation")
    return latex


def _render(node: Any) -> str:
    name = _local(node)
    if name.endswith("Pr") or name in {"ctrlPr", "rPr"}:
        return ""
    if name in {"oMathPara", "oMath", "e", "num", "den", "sub", "sup", "deg", "fName", "lim"}:
        return _render_children(node)
    if name in {"r", "t"}:
        text = "".join(node.itertext()) if name == "r" else str(node.text or "")
        return _math_text(text)
    if name == "f":
        return rf"\frac{{{_render(_child(node, 'num'))}}}{{{_render(_child(node, 'den'))}}}"
    if name == "rad":
        body = _render(_child(node, "e"))
        degree_node = _optional_child(node, "deg")
        degree = _render(degree_node) if degree_node is not None else ""
        return rf"\sqrt[{degree}]{{{body}}}" if degree else rf"\sqrt{{{body}}}"
    if name == "sSub":
        return rf"{_render(_child(node, 'e'))}_{{{_render(_child(node, 'sub'))}}}"
    if name == "sSup":
        return rf"{_render(_child(node, 'e'))}^{{{_render(_child(node, 'sup'))}}}"
    if name == "sSubSup":
        return (
            rf"{_render(_child(node, 'e'))}_{{{_render(_child(node, 'sub'))}}}"
            rf"^{{{_render(_child(node, 'sup'))}}}"
        )
    if name == "nary":
        operator = _property_value(node, "naryPr", "chr") or "∑"
        command = SYMBOLS.get(operator, _math_text(operator))
        sub = _render(_optional_child(node, "sub"))
        sup = _render(_optional_child(node, "sup"))
        body = _render(_child(node, "e"))
        return f"{command}" + (rf"_{{{sub}}}" if sub else "") + (rf"^{{{sup}}}" if sup else "") + body
    if name == "d":
        begin = _property_value(node, "dPr", "begChr") or "("
        end = _property_value(node, "dPr", "endChr") or ")"
        expression = _child(node, "e")
        matrix = _optional_descendant(expression, "m")
        if matrix is not None:
            env = {("[", "]"): "bmatrix", ("(", ")"): "pmatrix", ("|", "|"): "vmatrix"}.get((begin, end))
            if env:
                return _matrix(matrix, env)
        return rf"\left{_delimiter(begin)}{_render(expression)}\right{_delimiter(end)}"
    if name == "m":
        return _matrix(node, "matrix")
    if name == "func":
        function_name = _render(_child(node, "fName"))
        function_name = _function_command(function_name)
        return function_name + _render(_child(node, "e"))
    if name == "acc":
        accent = _property_value(node, "accPr", "chr") or "̂"
        command = {"̂": r"\hat", "̄": r"\bar", "⃗": r"\vec", "˜": r"\tilde"}.get(accent, r"\hat")
        return rf"{command}{{{_render(_child(node, 'e'))}}}"
    if name == "bar":
        position = _property_value(node, "barPr", "pos") or "top"
        command = r"\underline" if position == "bot" else r"\overline"
        return rf"{command}{{{_render(_child(node, 'e'))}}}"
    if name in {"limLow", "limUpp"}:
        base = _render(_child(node, "e"))
        limit = _render(_child(node, "lim"))
        marker = "_" if name == "limLow" else "^"
        return rf"{base}{marker}{{{limit}}}"
    if name == "eqArr":
        rows = [_render(child) for child in node if _local(child) == "e"]
        return r"\begin{aligned}" + r" \\ ".join(rows) + r"\end{aligned}"
    if name in {"box", "borderBox", "phant", "groupChr"}:
        expression = _optional_child(node, "e")
        return _render(expression) if expression is not None else _render_children(node)
    if name in {"mr"}:
        return " & ".join(_render(child) for child in node if _local(child) == "e")
    raise OmmlConversionError(f"unsupported OMML node: {name}")


def _matrix(node: Any, environment: str) -> str:
    rows = [_render(row) for row in node if _local(row) == "mr"]
    if not rows:
        raise OmmlConversionError("OMML matrix has no rows")
    return rf"\begin{{{environment}}}" + r" \\ ".join(rows) + rf"\end{{{environment}}}"


def _render_children(node: Any) -> str:
    return "".join(_render(child) for child in node)


def _child(node: Any, name: str):
    child = _optional_child(node, name)
    if child is None:
        raise OmmlConversionError(f"OMML { _local(node) } is missing {name}")
    return child


def _optional_child(node: Any, name: str):
    return next((child for child in node if _local(child) == name), None)


def _optional_descendant(node: Any, name: str):
    return next((child for child in node.iter() if _local(child) == name), None)


def _property_value(node: Any, property_name: str, value_name: str) -> str:
    property_node = _optional_child(node, property_name)
    if property_node is None:
        return ""
    value_node = _optional_child(property_node, value_name)
    if value_node is None:
        return ""
    return str(next((value for key, value in value_node.attrib.items() if key.endswith("}val") or key == "val"), ""))


def _local(node: Any) -> str:
    return etree.QName(node).localname


def _math_text(value: str) -> str:
    output: list[str] = []
    for char in str(value or ""):
        if char in SYMBOLS:
            output.append(SYMBOLS[char])
        elif char in "#%&{}":
            output.append("\\" + char)
        elif char == "_":
            output.append(r"\_")
        elif char == "^":
            output.append(r"\^")
        else:
            output.append(char)
    return "".join(output).strip()


def _delimiter(value: str) -> str:
    return {"{": r"\{", "}": r"\}", "": "."}.get(value, value)


def _function_command(value: str) -> str:
    normalized = re.sub(r"\s+", "", value)
    if normalized in {"sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim"}:
        return "\\" + normalized
    return value
