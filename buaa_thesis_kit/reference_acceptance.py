from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from buaa_thesis_kit.models import ContentBlock, ThesisModel
from buaa_thesis_kit.rules import load_rule_file


@dataclass
class ReferenceInspection:
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


REFERENCE_NUMBER_RE = re.compile(r"^\s*\[(\d+)\]")
CITATION_RE = re.compile(r"\[(\d+(?:\s*[-,\uFF0C\u3001]\s*\d+)*)\]")


def inspect_references(model: ThesisModel) -> ReferenceInspection:
    """Check citation/reference consistency without rewriting source content."""
    result = ReferenceInspection()
    rules = load_rule_file("reference-rules.yaml").get("references", {})
    require_terminal_period = bool(rules.get("require_terminal_period", True))

    cited_numbers = _cited_reference_numbers(_iter_body_blocks(model))
    reference_entries = _reference_entries(model.references)
    reference_numbers = _reference_numbers(reference_entries)
    known_numbers = set(reference_numbers)

    duplicates = sorted(_duplicate_numbers(reference_numbers))
    for number in duplicates:
        result.blocking_items.append(f"duplicate_reference_number: [{number}]")

    if cited_numbers and not model.references:
        result.blocking_items.append("missing_references_section: body citations exist but no references were extracted.")
    else:
        missing = sorted(cited_numbers - known_numbers)
        if missing:
            missing_text = ", ".join(f"[{number}]" for number in missing)
            result.blocking_items.append(f"citation_without_reference: {missing_text}")

    for index, text in enumerate(reference_entries, start=1):
        if not REFERENCE_NUMBER_RE.match(text):
            result.manual_review.append(f"non_gbt_7714_entry: reference {index} is missing a leading [n] number.")
        elif require_terminal_period and not text.rstrip().endswith((".", "\u3002")):
            number = REFERENCE_NUMBER_RE.match(text).group(1)
            result.manual_review.append(f"non_gbt_7714_entry: [{number}] does not end with a period.")

    if not result.blocking_items and not result.manual_review and (cited_numbers or reference_numbers):
        result.notes.append(
            "reference validation passed: "
            f"{len(cited_numbers)} cited number(s), {len(reference_numbers)} reference item(s)."
        )
    return result


def _iter_body_blocks(model: ThesisModel) -> Iterable[ContentBlock]:
    yield from model.sections
    yield from model.tables
    yield from model.appendices


def _cited_reference_numbers(blocks: Iterable[ContentBlock]) -> set[int]:
    cited: set[int] = set()
    for block in blocks:
        for match in CITATION_RE.finditer(_block_text(block)):
            cited.update(_expand_citation_numbers(match.group(1)))
    return cited


def _expand_citation_numbers(text: str) -> set[int]:
    numbers: set[int] = set()
    for part in re.split(r"\s*[,\uFF0C\u3001]\s*", text):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = [item.strip() for item in part.split("-", 1)]
            if start_text.isdigit() and end_text.isdigit():
                start, end = int(start_text), int(end_text)
                if start <= 0 or end <= 0:
                    return set()
                if start <= end:
                    numbers.update(range(start, end + 1))
                continue
        if part.strip().isdigit():
            number = int(part.strip())
            if number <= 0:
                return set()
            numbers.add(number)
    return numbers


def _reference_entries(references: Iterable[ContentBlock]) -> list[str]:
    entries: list[str] = []
    current = ""
    for reference in references:
        text = _block_text(reference)
        if not text:
            continue
        if REFERENCE_NUMBER_RE.match(text):
            if current:
                entries.append(current)
            current = text
        elif current:
            current = f"{current}\n{text}"
        else:
            entries.append(text)
    if current:
        entries.append(current)
    return entries


def _reference_numbers(references: Iterable[str]) -> list[int]:
    numbers: list[int] = []
    for reference in references:
        match = REFERENCE_NUMBER_RE.match(reference)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def _duplicate_numbers(numbers: Iterable[int]) -> set[int]:
    seen: set[int] = set()
    duplicates: set[int] = set()
    for number in numbers:
        if number in seen:
            duplicates.add(number)
        seen.add(number)
    return duplicates


def _block_text(block: ContentBlock) -> str:
    return "\n".join(part for part in [block.title, block.text] if part).strip()


__all__ = ["ReferenceInspection", "inspect_references"]
