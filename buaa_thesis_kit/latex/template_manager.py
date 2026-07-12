from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VENDORED_TEMPLATE = ROOT / "templates" / "latex" / "buaa" / "bhosc"
DEFAULT_EXTERNAL_TEMPLATE = ROOT / "templates" / "external" / "BUAAthesis"
LOCAL_REFERENCE_TEMPLATE = ROOT / "tmp" / "latex_refs" / "BHOSC_BUAAthesis"
CLONE_URL = "https://github.com/BHOSC/BUAAthesis"
DEGREE_ALIASES = {
    "undergraduate": "undergraduate",
    "bachelor": "undergraduate",
    "本科": "undergraduate",
    "master": "master",
    "硕士": "master",
    "doctor": "doctor",
    "博士": "doctor",
}
ENTRY_BY_DEGREE = {
    "undergraduate": "sample-bachelor.tex",
    "master": "sample-master.tex",
    "doctor": "sample-doctor.tex",
}


def resolve_buaa_template(path: str | Path | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser().resolve(strict=False)
        if not candidate.exists():
            raise FileNotFoundError(f"BUAAthesis template path does not exist: {candidate}")
        return candidate
    if VENDORED_TEMPLATE.exists():
        return VENDORED_TEMPLATE.resolve(strict=False)
    if DEFAULT_EXTERNAL_TEMPLATE.exists():
        return DEFAULT_EXTERNAL_TEMPLATE.resolve(strict=False)
    raise FileNotFoundError(
        "BUAAthesis runtime is missing from templates/latex/buaa/bhosc. "
        f"An external clone can be supplied from {CLONE_URL}."
    )


def inspect_buaa_template(
    template_path: str | Path | None = None,
    *,
    degree_type: str = "undergraduate",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_buaa_template(template_path)
    degree = normalize_degree_type(degree_type)
    class_path = root / "buaathesis.cls"
    class_text = class_path.read_text(encoding="utf-8") if class_path.exists() else ""
    entry_path = _entry_path(root, degree)
    entry_text = entry_path.read_text(encoding="utf-8") if entry_path.exists() else ""
    reference_path = root / "data" / "reference.tex"
    reference_text = reference_path.read_text(encoding="utf-8") if reference_path.exists() else ""

    inspection = {
        "template_path": str(root),
        "clone_url": CLONE_URL,
        "degree_type": degree,
        "entry": {
            "path": str(entry_path),
            "exists": entry_path.exists(),
            "documentclass_options": _documentclass_options(entry_text),
            "includes": _includes(entry_text),
        },
        "metadata_api": _metadata_api(class_text),
        "abstract_structure": {
            "environments": _environments(class_text, ["cabstract", "eabstract"]),
            "template_file": "data/abstract.tex",
        },
        "chapter_includes": [
            include for include in _includes(entry_text) if include.startswith("data/chapter")
        ],
        "bibliography": _bibliography(reference_text),
        "figure_asset_dir": str(root / "figure") if (root / "figure").exists() else "",
        "build_command": {
            "engine": "xelatex",
            "preferred": "latexmk -xelatex thesis.tex",
            "fallback": "xelatex thesis.tex repeated 2-3 times",
        },
    }
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(inspection, ensure_ascii=False, indent=2), encoding="utf-8")
    return inspection


def normalize_degree_type(value: str) -> str:
    normalized = str(value or "undergraduate").strip().lower()
    if normalized == "auto":
        return "undergraduate"
    if normalized not in DEGREE_ALIASES:
        raise ValueError(f"Unsupported degree_type: {value}")
    return DEGREE_ALIASES[normalized]


def _entry_path(root: Path, degree_type: str) -> Path:
    return root / ENTRY_BY_DEGREE[degree_type]


def _documentclass_options(tex: str) -> list[str]:
    match = re.search(r"\\documentclass(?:\[([^\]]*)\])?\{buaathesis\}", tex)
    if not match:
        return []
    return [item.strip() for item in (match.group(1) or "").split(",") if item.strip()]


def _includes(tex: str) -> list[str]:
    return re.findall(r"\\include\{([^}]+)\}", tex)


def _metadata_api(class_text: str) -> dict[str, dict[str, int]]:
    api: dict[str, dict[str, int]] = {}
    for match in re.finditer(r"\\newcommand\{\\([A-Za-z@]+)\}(?:\[(\d+)\])?", class_text):
        api[match.group(1)] = {"args": int(match.group(2) or 0)}
    return api


def _environments(class_text: str, names: list[str]) -> list[str]:
    present = []
    for name in names:
        if re.search(rf"\\newenvironment\{{{re.escape(name)}\}}", class_text):
            present.append(name)
    return present


def _bibliography(reference_text: str) -> dict[str, Any]:
    return {
        "uses_bibtex": bool(re.search(r"\\bibliography\{", reference_text)),
        "bibliography_files": re.findall(r"\\bibliography\{([^}]+)\}", reference_text),
        "supports_manual_raw_references": True,
    }
