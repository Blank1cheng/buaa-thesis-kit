from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).resolve().parent / "config"
ROLE_ORDER = (
    "debug_forbidden",
    "system_report_content",
    "template_instruction",
    "template_sample_value",
    "template_static_required",
    "user_fill_value",
    "source_frontmatter_content",
    "source_body_content",
)


def classify_text(text: str) -> str:
    value = _normalize(text)
    if not value:
        return "source_body_content"
    token_map = _token_map()
    for role in ROLE_ORDER:
        for token in token_map.get(role, []):
            if _normalize(token) and _normalize(token) in value:
                return role
    if value.startswith(("1绪论", "1.1", "第1章", "第一章")):
        return "source_body_content"
    return "source_body_content"


def role_allows_thesis(role: str) -> bool:
    schema = _load_yaml("role_schema.yaml").get("roles", {})
    return bool(schema.get(role, {}).get("allowed_in_thesis", False))


def _token_map() -> dict[str, list[str]]:
    sample_tokens = _load_yaml("template_sample_tokens.yaml")
    forbidden_tokens = _load_yaml("forbidden_tokens.yaml")
    result: dict[str, list[str]] = {}
    for source in (sample_tokens, forbidden_tokens):
        for role, tokens in source.items():
            result.setdefault(role, []).extend(str(token) for token in tokens)
    return result


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _normalize(text: str) -> str:
    return "".join(str(text or "").split()).lower()


__all__ = ["classify_text", "role_allows_thesis"]
