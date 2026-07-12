from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(
    *,
    candidate_path: Path,
    source_model_path: Path | None = None,
    template_path: Path | None = None,
) -> dict[str, Any]:
    candidate = Path(candidate_path)
    identity: dict[str, Any] = {
        "candidate_path": str(candidate),
        "candidate_sha256": sha256_file(candidate),
        "candidate_size": candidate.stat().st_size,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_model_path": str(source_model_path) if source_model_path is not None else None,
        "source_model_sha256": _optional_sha256(source_model_path),
        "template_path": str(template_path) if template_path is not None else None,
        "template_sha256": _optional_sha256(template_path),
    }
    return identity


def attach_artifact_identity(
    report: dict[str, Any],
    *,
    candidate_path: Path,
    source_model_path: Path | None = None,
    template_path: Path | None = None,
) -> dict[str, Any]:
    return {
        **report,
        **artifact_identity(
            candidate_path=candidate_path,
            source_model_path=source_model_path,
            template_path=template_path,
        ),
    }


def validate_report_artifact_identity(report: dict[str, Any], *, candidate_path: Path) -> dict[str, Any]:
    current = artifact_identity(candidate_path=candidate_path)
    expected_sha = report.get("candidate_sha256")
    expected_size = report.get("candidate_size")
    if expected_sha == current["candidate_sha256"] and expected_size == current["candidate_size"]:
        return {"status": "pass", "failures": [], **current}
    return {"status": "failed", "failures": [{"id": "artifact_identity_mismatch"}], **current}


def _optional_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return sha256_file(candidate)


__all__ = [
    "artifact_identity",
    "attach_artifact_identity",
    "sha256_file",
    "validate_report_artifact_identity",
]
