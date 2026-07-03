from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


KIT_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = KIT_ROOT / "rules"
RULE_FILES = (
    "format-rules.yaml",
    "metadata-extraction-rules.yaml",
    "section-splitting-rules.yaml",
    "figure-table-rules.yaml",
    "equation-rules.yaml",
    "reference-rules.yaml",
)


def load_rule_file(name: str) -> dict[str, Any]:
    if Path(name).is_absolute() or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"Invalid rule file name: {name!r}")
    if name not in RULE_FILES:
        raise ValueError(f"Invalid rule file name: {name!r}")

    path = RULES_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse rule file {name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Rule file must contain a mapping: {path}")
    return data


def load_all_rules() -> dict[str, dict[str, Any]]:
    return {name: load_rule_file(name) for name in RULE_FILES}
