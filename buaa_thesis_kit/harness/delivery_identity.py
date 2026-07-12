from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .delivery_failures import make_failure


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError:
        return True


def artifact_manifest_sha256(output: Path) -> str:
    files: list[Path] = []
    for path in output.iterdir():
        if path.name == "report.md" or not path.is_file():
            continue
        if is_link_or_junction(path):
            raise ValueError(f"linked artifact cannot enter manifest: {path}")
        files.append(path)

    image_dir = output / "image"
    if is_link_or_junction(image_dir):
        raise ValueError(f"linked image directory cannot enter manifest: {image_dir}")
    if image_dir.is_dir():
        for path in image_dir.iterdir():
            if not path.is_file():
                continue
            if is_link_or_junction(path):
                raise ValueError(f"linked image cannot enter manifest: {path}")
            files.append(path)

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(output).as_posix()):
        relative = path.relative_to(output).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_path_matches(recorded: object, candidate: Path) -> bool:
    if not isinstance(recorded, str) or not recorded:
        return False
    try:
        return Path(recorded).resolve() == candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def parse_report_identity(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    try:
        start = lines.index("## Artifact identity") + 1
    except ValueError:
        return None
    values: dict[str, str] = {}
    for line in lines[start:]:
        if line.startswith("## "):
            break
        match = re.fullmatch(r"- ([a-z0-9_]+): (.+)", line)
        if match is None:
            if line.strip():
                return None
            continue
        key, value = match.groups()
        if key in values:
            return None
        values[key] = value
    required = {
        "source_candidate_path",
        "source_sha256",
        "source_size",
        "artifact_manifest_sha256",
    }
    return values if set(values) == required else None


def validate_report_identity(
    output: Path, source_identity: Mapping[str, Any]
) -> list[dict[str, Any]]:
    report_path = output / "report.md"
    recorded: dict[str, str] | None = None
    error: str | None = None
    if (
        not report_path.is_file()
        or is_link_or_junction(report_path)
    ):
        error = "report.md is missing, unreadable, or linked"
    else:
        try:
            recorded = parse_report_identity(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        if recorded is None and error is None:
            error = "Artifact identity section is missing or malformed"

    try:
        manifest_sha = artifact_manifest_sha256(output)
    except (OSError, RuntimeError, ValueError) as exc:
        manifest_sha = None
        error = error or f"{type(exc).__name__}: {exc}"
    actual = {
        "source_candidate_path": source_identity.get("candidate_path"),
        "source_sha256": source_identity.get("source_sha256"),
        "source_size": source_identity.get("source_size"),
        "artifact_manifest_sha256": manifest_sha,
    }
    matches = False
    if recorded is not None and error is None:
        try:
            recorded_size = int(recorded["source_size"])
        except (KeyError, TypeError, ValueError):
            recorded_size = None
        matches = (
            recorded.get("source_candidate_path") == actual["source_candidate_path"]
            and recorded.get("source_sha256") == actual["source_sha256"]
            and recorded_size == actual["source_size"]
            and recorded.get("artifact_manifest_sha256")
            == actual["artifact_manifest_sha256"]
        )
    if matches:
        return []
    return [
        make_failure(
            "REPORT-IDENTITY",
            gate="DELIVERY",
            status="failed",
            reason="report_identity_mismatch",
            region="report.md",
            evidence={
                "paths": [str(report_path)],
                "details": {"recorded": recorded, "actual": actual, "error": error},
            },
            evidence_text="report.md Artifact identity does not match the delivery bundle.",
            expected="All Artifact identity values match source and public artifacts.",
            suggested_fix="Regenerate report.md after finalizing all public artifacts.",
            can_fix_now=True,
        )
    ]


def strip_latex_comments(text: str) -> str:
    stripped: list[str] = []
    for line in text.splitlines():
        comment_at = len(line)
        for index, character in enumerate(line):
            if character != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                comment_at = index
                break
        stripped.append(line[:comment_at])
    return "\n".join(stripped)


def referenced_pdf_names(thesis_tex: str) -> set[str]:
    clean_tex = strip_latex_comments(thesis_tex)
    return {
        match.group(1).lower()
        for match in re.finditer(
            r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{\s*image/([^/{}\s]+\.pdf)\s*\}",
            clean_tex,
            flags=re.IGNORECASE,
        )
    }
