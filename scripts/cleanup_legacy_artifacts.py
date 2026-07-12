from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


KEEP_OUTPUT_NAMES = {
    "latex_pipeline",
    "latex_pipeline_pdf",
    "image",
    "goal_acceptance.md",
    "goal_acceptance.json",
    "cleanup_report.json",
}


def plan_cleanup(
    *,
    output_root: str | Path = "output",
    include_latex: bool = False,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    output = _absolute(Path(output_root))
    workspace = _absolute(Path(workspace_root)) if workspace_root is not None else output
    keep = set(KEEP_OUTPUT_NAMES)
    if include_latex:
        keep.discard("latex_pipeline")
        keep.discard("latex_pipeline_pdf")

    planned: list[dict[str, Any]] = []
    retained_roots: list[Path] = []
    if output.exists():
        for child in sorted(output.iterdir(), key=lambda item: item.name):
            if child.name in keep:
                retained_roots.append(child)
                continue
            planned.append(_plan_item(child, "obsolete_output_artifact"))

    if workspace_root is not None:
        alias = workspace / "templates" / "external" / "BUAAthesis"
        if _path_exists(alias):
            planned.append(_plan_item(alias, "external_template_alias"))
        for name, reason in (
            ("generated", "generated_process_artifacts"),
            ("tmp", "temporary_process_artifacts"),
        ):
            path = workspace / name
            if _path_exists(path):
                planned.append(_plan_item(path, reason))

    retained = _retained_manifest(retained_roots)
    return {
        "workspace_root": str(workspace),
        "output_root": str(output),
        "include_latex": include_latex,
        "keep_output_names": sorted(keep),
        "planned": planned,
        "planned_bytes": sum(int(item.get("bytes") or 0) for item in planned),
        "retained": retained,
        "retained_bytes": sum(int(item.get("size") or 0) for item in retained),
    }


def apply_cleanup(report: dict[str, Any]) -> dict[str, Any]:
    workspace = _absolute(Path(report.get("workspace_root") or report["output_root"]))
    removed: list[str] = []
    skipped_unsafe: list[str] = []
    removed_bytes = 0
    for item in report.get("planned") or []:
        lexical = _absolute(Path(item["path"]))
        if not _is_within(lexical, workspace):
            skipped_unsafe.append(str(lexical))
            continue
        if not _path_exists(lexical):
            continue
        resolved = lexical.resolve(strict=False)
        if not _is_within(resolved, workspace):
            skipped_unsafe.append(str(lexical))
            continue
        if _is_link_or_junction(lexical):
            if lexical.is_dir():
                os.rmdir(lexical)
            else:
                lexical.unlink()
        elif lexical.is_dir():
            shutil.rmtree(lexical)
        else:
            lexical.unlink()
        removed.append(str(lexical))
        removed_bytes += int(item.get("bytes") or 0)
    applied = dict(report)
    applied["removed"] = removed
    applied["removed_bytes"] = removed_bytes
    applied["skipped_unsafe"] = skipped_unsafe
    return applied


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely remove obsolete BUAA thesis process artifacts.")
    parser.add_argument("--workspace-root", default=ROOT, type=Path)
    parser.add_argument("--output-root", default=ROOT / "output", type=Path)
    parser.add_argument("--include-latex", action="store_true", help="Also remove the two retained final LaTeX runs.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    namespace = parser.parse_args(args)

    report = plan_cleanup(
        output_root=namespace.output_root,
        include_latex=namespace.include_latex,
        workspace_root=namespace.workspace_root,
    )
    report["mode"] = "apply" if namespace.apply else "dry-run"
    if namespace.apply:
        report = apply_cleanup(report)
    namespace.output_root.mkdir(parents=True, exist_ok=True)
    report_path = namespace.output_root / "cleanup_report.json"
    report["cleanup_report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _plan_item(path: Path, reason: str) -> dict[str, Any]:
    kind = "junction" if _is_junction(path) else "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file"
    return {"path": str(_absolute(path)), "type": kind, "reason": reason, "bytes": _tree_size(path)}


def _retained_manifest(roots: list[Path]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for root in roots:
        if root.is_file():
            files = [root]
        elif _is_link_or_junction(root):
            files = []
        else:
            files = sorted((path for path in root.rglob("*") if path.is_file() and not _is_link_or_junction(path)), key=str)
        for path in files:
            manifest.append({"path": str(_absolute(path)), "size": path.stat().st_size, "sha256": _sha256(path)})
    return manifest


def _tree_size(path: Path) -> int:
    if _is_link_or_junction(path):
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not _is_link_or_junction(child):
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker and checker())


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or _is_junction(path)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink() or _is_junction(path)


if __name__ == "__main__":
    raise SystemExit(main())
