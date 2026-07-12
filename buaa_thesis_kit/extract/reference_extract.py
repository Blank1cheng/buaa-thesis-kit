from __future__ import annotations

import re
from collections.abc import Callable, Iterable


REFERENCE_START_RE = re.compile(r"^\s*(?:\[\d+\]|（\d+）(?=\s)|\(\d+\)(?=\s))")
REFERENCE_START_TOKEN_RE = re.compile(r"(?:\[\d+\]|（\d+）(?=\s)|\(\d+\)(?=\s))")


def merge_reference_entries(
    lines: Iterable[str],
    *,
    stop_predicate: Callable[[str], bool] | None = None,
) -> list[str]:
    entries: list[str] = []
    current = ""
    for raw_line in lines:
        for split_line in _split_joined_reference_line(raw_line):
            line = _clean_reference_line(split_line)
            if not line:
                continue
            if stop_predicate and stop_predicate(line):
                if current:
                    entries.append(current)
                return entries
            if REFERENCE_START_RE.match(line):
                if current:
                    entries.append(current)
                current = line
                continue
            if current:
                current = _join_reference_lines(current, line)
    if current:
        entries.append(current)
    return entries


def _legacy_merge_reference_entries(
    lines: Iterable[str],
    *,
    stop_predicate: Callable[[str], bool] | None = None,
) -> list[str]:
    entries: list[str] = []
    current = ""
    for raw_line in lines:
        line = _clean_reference_line(raw_line)
        if not line:
            continue
        if stop_predicate and stop_predicate(line):
            break
        if REFERENCE_START_RE.match(line):
            if current:
                entries.append(current)
            current = line
            continue
        if current:
            current = _join_reference_lines(current, line)
    if current:
        entries.append(current)
    return entries


def _split_joined_reference_line(value: object) -> list[str]:
    line = str(value or "")
    matches = list(REFERENCE_START_TOKEN_RE.finditer(line))
    if len(matches) <= 1:
        return [line]
    parts = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        parts.append(line[match.start() : end].strip())
    return [part for part in parts if part]


def numbered_reference(raw: str, ordinal: int) -> str:
    value = _clean_reference_line(raw)
    if REFERENCE_START_RE.match(value):
        return value
    return f"[{ordinal}] {value}" if value else ""


def normalize_reference_items(items: Iterable[dict | str]) -> list[dict[str, str]]:
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(str(item.get("raw") or item.get("text") or item.get("title") or ""))
        else:
            lines.append(str(item or ""))
    entries = merge_reference_entries(lines)
    if not entries:
        entries = [_clean_reference_line(line) for line in lines if _clean_reference_line(line)]
    return [
        {
            "index": index + 1,
            "raw": numbered_reference(entry, index + 1),
            "merged": numbered_reference(entry, index + 1),
            "raw_lines": [numbered_reference(entry, index + 1)],
        }
        for index, entry in enumerate(entries)
    ]


def _join_reference_lines(left: str, right: str) -> str:
    if left.endswith("-") and right and right[0].islower():
        return left[:-1] + right
    if re.match(r"^[（(]\d+[）)][：:]", right):
        return left + right
    if not left:
        return right
    if not right:
        return left
    return f"{left} {right}"


def _clean_reference_line(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r",(?=[A-Za-z])", ", ", text)
    text = re.sub(r"([a-z])([A-Z])(?=[\s.,;:\]])", r"\1 \2", text)
    text = re.sub(r"\]\s+\.", "].", text)
    text = re.sub(r"\[\s*([MJDCP])\s*\]", r"[\1]", text)
    text = re.sub(r"(?<=\d)\s+(?=[（(]\d+[）)])", "", text)
    return re.sub(r"\s+", " ", text).strip()
