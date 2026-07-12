from __future__ import annotations

import hashlib
import json
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from buaa_thesis_kit.docx_extract import extract_thesis_model
from buaa_thesis_kit.pdf_extract import extract_pdf_model

from .native_pipeline import run_equation_items


@dataclass(frozen=True)
class LoadedEquationInput:
    source_type: str
    equations: list[dict[str, Any]]
    model_root: Path
    identity: dict[str, Any]
    model_path: Path
    model_status: str = ""
    extraction_warnings: list[str] | None = None


def load_equation_input(source: str | Path, out_dir: str | Path) -> LoadedEquationInput:
    source_path = Path(source).resolve()
    out_dir = Path(out_dir).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    identity = {
        "source_candidate_path": str(source_path),
        "candidate_sha256": _sha256(source_path),
        "candidate_size": source_path.stat().st_size,
    }
    suffix = source_path.suffix.lower()
    if suffix == ".json":
        model = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(model, dict):
            raise ValueError("model JSON root must be an object")
        return LoadedEquationInput(
            source_type="model_json",
            equations=_collect_equations(model),
            model_root=source_path.parent,
            identity=identity,
            model_path=source_path,
            model_status=str(model.get("status") or ""),
            extraction_warnings=list(model.get("extraction_warnings") or []),
        )
    if suffix in {".docx", ".pdf"}:
        extraction_dir = _prepare_extraction_dir(out_dir)
        thesis_model = (
            extract_thesis_model(source_path, extraction_dir)
            if suffix == ".docx"
            else extract_pdf_model(source_path, extraction_dir)
        )
        model = thesis_model.to_dict()
        model_path = extraction_dir / "model.json"
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
        return LoadedEquationInput(
            source_type=suffix.lstrip("."),
            equations=_collect_equations(model),
            model_root=extraction_dir,
            identity=identity,
            model_path=model_path,
            model_status=str(model.get("status") or thesis_model.status or ""),
            extraction_warnings=list(model.get("extraction_warnings") or thesis_model.extraction_warnings or []),
        )
    raise ValueError(f"unsupported equation input: {suffix or '<no extension>'}")


def run_equation_pipeline(
    source: str | Path,
    out_dir: str | Path,
    *,
    recognizer: Any | None = None,
) -> dict[str, Any]:
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    loaded = load_equation_input(source, out_path)
    identity = dict(loaded.identity)
    identity["commit"] = _current_commit()
    (out_path / "input_identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = run_equation_items(
        loaded.equations,
        out_path,
        model_root=loaded.model_root,
        recognizer=recognizer,
    )
    report["artifact_identity"] = identity
    report["source_type"] = loaded.source_type
    report["model_path"] = str(loaded.model_path)
    report["model_root"] = str(loaded.model_root)
    report["extraction_status"] = loaded.model_status
    report["extraction_warnings"] = list(loaded.extraction_warnings or [])
    report["recognizer"] = {
        "configured": recognizer is not None,
        "type": type(recognizer).__name__ if recognizer is not None else "",
    }
    (out_path / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _collect_equations(model: dict[str, Any]) -> list[dict[str, Any]]:
    equations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("equations", "equations_need_review"):
        values = model.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            marker = _equation_marker(value, len(equations))
            if marker in seen:
                continue
            seen.add(marker)
            equations.append(dict(value))
    return equations


def _equation_marker(equation: dict[str, Any], ordinal: int) -> str:
    for key in ("id", "native_sha256", "omml_sha256"):
        value = str(equation.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return f"ordinal:{ordinal}:{json.dumps(equation, ensure_ascii=False, sort_keys=True)}"


def _prepare_extraction_dir(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    extraction_dir = (out_dir / "extraction").resolve()
    try:
        extraction_dir.relative_to(out_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"unsafe extraction directory: {extraction_dir}") from exc
    if extraction_dir.exists():
        shutil.rmtree(extraction_dir)
    extraction_dir.mkdir(parents=True)
    return extraction_dir


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_commit() -> str:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"
