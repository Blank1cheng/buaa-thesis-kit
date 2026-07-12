from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .delivery_failures import (
    evaluate_delivery_profile,
    failed_profile_result,
    make_failure,
    merge_status,
    status_from_failures,
    validate_queue_items,
)
from .delivery_identity import (
    artifact_identity,
    is_link_or_junction,
    referenced_pdf_names,
    sha256_file,
    source_path_matches,
    validate_report_identity,
)
from .profiles import evaluate_profile
from .visual_manifest import missing_visual_report, validate_visual_manifest


REQUIRED_DELIVERY_ITEMS = (
    "thesis.docx",
    "thesis.pdf",
    "thesis.tex",
    "model.json",
    "report.md",
    "failure_queue.json",
    "image",
)
IDENTITY_ARTIFACTS = REQUIRED_DELIVERY_ITEMS[:-1]
ALLOWED_IMAGE_SUFFIXES = {
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".eps",
    ".tif",
    ".tiff",
    ".webp",
}


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _failure(
    semantic_id: str,
    *,
    reason: str,
    region: str,
    evidence: Any,
    evidence_text: str,
    expected: str,
    gate: str = "DELIVERY",
    status: str = "failed",
    suggested_fix: str = "Repair the delivery bundle and rerun validation.",
    can_fix_now: bool = True,
) -> dict[str, Any]:
    return make_failure(
        semantic_id,
        gate=gate,
        status=status,
        reason=reason,
        region=region,
        evidence=evidence,
        evidence_text=evidence_text,
        expected=expected,
        suggested_fix=suggested_fix,
        can_fix_now=can_fix_now,
    )


def _read_failure(
    semantic_id: str, path: Path, error: str, reason: str
) -> dict[str, Any]:
    return _failure(
        semantic_id,
        reason=reason,
        region=path.name,
        evidence={"paths": [str(path)], "details": error},
        evidence_text=error,
        expected=f"{path.name} is readable and has the required structure.",
        suggested_fix=f"Repair or regenerate {path.name}.",
    )


def _evaluate_profile_file(
    profile: str, board_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    board, error = _read_json(board_path)
    if error:
        return failed_profile_result(profile), [
            _read_failure("GATE-BOARD-READ", board_path, error, "invalid_gate_board")
        ]
    try:
        return evaluate_delivery_profile(profile, board)
    except ValueError as exc:
        return failed_profile_result(profile), [
            _read_failure(
                "GATE-BOARD-SCHEMA",
                board_path,
                f"ValueError: {exc}",
                "invalid_gate_board",
            )
        ]


def _linked_failure(path: Path, region: str) -> dict[str, Any]:
    return _failure(
        f"FORBIDDEN-LINK-{region}-{path.name}",
        reason="forbidden_symlink_artifact",
        region=region,
        evidence={"paths": [str(path)]},
        evidence_text=f"Linked artifacts are forbidden: {path}.",
        expected="Every public artifact is a regular local file or directory.",
        suggested_fix="Replace the link or junction with a regular artifact.",
    )


def _linked_output_result(
    output: Path, profile: str, board_path: Path
) -> dict[str, Any]:
    profile_result, profile_failures = _evaluate_profile_file(profile, board_path)
    link_failure = _linked_failure(output, "output")
    visual_report = missing_visual_report(output)
    failures = [link_failure, *profile_failures]
    return {
        "status": "failed",
        "source_identity": {},
        "artifact_identities": {},
        "profile_result": profile_result,
        "visual_manifest_report": visual_report,
        "failures": failures,
    }


def validate_delivery(
    output_dir: Path,
    *,
    profile: str,
    gate_board_path: Path,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(profile, str) or not profile:
        raise ValueError("profile must be a non-empty string")
    try:
        output = Path(output_dir)
        board_path = Path(gate_board_path)
        supplied_candidate = Path(candidate_path) if candidate_path is not None else None
    except TypeError as exc:
        raise ValueError("paths must be path-like values") from exc
    if is_link_or_junction(output):
        return _linked_output_result(output, profile, board_path)

    failures: list[dict[str, Any]] = []
    identities: dict[str, dict[str, Any]] = {}
    source_identity: dict[str, Any] = {}
    root_entries: dict[str, Path] = {}
    if not output.is_dir():
        failures.append(
            _failure(
                "MISSING-OUTPUT-DIRECTORY",
                reason="missing_delivery_artifact",
                region="output",
                evidence={"paths": [str(output)]},
                evidence_text="The delivery output directory is missing.",
                expected="A readable delivery output directory.",
            )
        )
    else:
        try:
            root_entries = {entry.name: entry for entry in output.iterdir()}
        except OSError as exc:
            failures.append(
                _read_failure(
                    "OUTPUT-READ", output, f"{type(exc).__name__}: {exc}",
                    "delivery_artifact_read_error",
                )
            )

    for name in REQUIRED_DELIVERY_ITEMS:
        path = root_entries.get(name)
        expected_dir = name == "image"
        valid = (
            path is not None
            and not is_link_or_junction(path)
            and (path.is_dir() if expected_dir else path.is_file())
        )
        if not valid:
            failures.append(
                _failure(
                    f"MISSING-{name}",
                    reason="missing_delivery_artifact",
                    region="output",
                    evidence={
                        "paths": [name],
                        "details": {"artifact": name, "expected_directory": expected_dir},
                    },
                    evidence_text=f"Required delivery item {name} is missing or invalid.",
                    expected=f"{name} exists as a {'directory' if expected_dir else 'file'}.",
                )
            )

    allowed_root = set(REQUIRED_DELIVERY_ITEMS)
    for name, path in sorted(root_entries.items()):
        if is_link_or_junction(path):
            failures.append(_linked_failure(path, "output"))
        if name not in allowed_root:
            failures.append(
                _failure(
                    f"FORBIDDEN-ROOT-{name}",
                    reason="forbidden_process_artifact",
                    region="output",
                    evidence={"paths": [name]},
                    evidence_text=f"Unexpected item exists at the output root: {name}.",
                    expected="Only public delivery items exist at the output root.",
                    suggested_fix=f"Move or remove {name}.",
                )
            )

    thesis_tex = ""
    tex_path = root_entries.get("thesis.tex")
    if tex_path and tex_path.is_file() and not is_link_or_junction(tex_path):
        try:
            thesis_tex = tex_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(
                _read_failure(
                    "THESIS-TEX-READ", tex_path, f"{type(exc).__name__}: {exc}",
                    "delivery_artifact_read_error",
                )
            )
    referenced_pdfs = referenced_pdf_names(thesis_tex)

    image_dir = root_entries.get("image")
    if image_dir and image_dir.is_dir() and not is_link_or_junction(image_dir):
        try:
            image_entries = list(image_dir.iterdir())
        except OSError as exc:
            image_entries = []
            failures.append(
                _read_failure(
                    "IMAGE-DIRECTORY-READ", image_dir,
                    f"{type(exc).__name__}: {exc}", "delivery_artifact_read_error",
                )
            )
        for path in sorted(image_entries):
            relative = f"image/{path.name}"
            if is_link_or_junction(path):
                failures.append(_linked_failure(path, "image"))
                continue
            suffix = path.suffix.lower()
            allowed = path.is_file() and (
                path.name == "visual_review.json"
                or suffix in ALLOWED_IMAGE_SUFFIXES
                or (suffix == ".pdf" and path.name.lower() in referenced_pdfs)
            )
            if not allowed:
                failures.append(
                    _failure(
                        f"FORBIDDEN-IMAGE-{path.name}",
                        reason="forbidden_process_artifact",
                        region="image",
                        evidence={"paths": [relative]},
                        evidence_text=f"Forbidden item exists in image: {path.name}.",
                        expected="Only final media, visual_review.json, and referenced PDFs.",
                        suggested_fix=f"Remove {relative}.",
                    )
                )
                continue
            try:
                identities[relative] = artifact_identity(path)
            except OSError as exc:
                failures.append(
                    _read_failure(
                        f"IMAGE-IDENTITY-{path.name}", path,
                        f"{type(exc).__name__}: {exc}", "delivery_artifact_read_error",
                    )
                )

    for name in IDENTITY_ARTIFACTS:
        path = root_entries.get(name)
        if not path or not path.is_file() or is_link_or_junction(path):
            continue
        try:
            identities[name] = artifact_identity(path)
        except OSError as exc:
            failures.append(
                _read_failure(
                    f"ROOT-IDENTITY-{name}", path,
                    f"{type(exc).__name__}: {exc}", "delivery_artifact_read_error",
                )
            )

    model: Any = None
    model_path = output / "model.json"
    if model_path.is_file() and not is_link_or_junction(model_path):
        model, error = _read_json(model_path)
        if error:
            failures.append(
                _read_failure("MODEL-JSON", model_path, error, "invalid_delivery_json")
            )
    model_source = model.get("source") if isinstance(model, Mapping) else None
    candidate = supplied_candidate
    if candidate is None and isinstance(model_source, Mapping):
        recorded_path = model_source.get("candidate_path")
        if isinstance(recorded_path, str) and recorded_path:
            candidate = Path(recorded_path)
    if candidate is not None and candidate.is_file():
        try:
            source_identity = {
                "candidate_path": str(candidate.resolve()),
                "source_sha256": sha256_file(candidate),
                "source_size": candidate.stat().st_size,
            }
        except OSError as exc:
            failures.append(
                _read_failure(
                    "SOURCE-READ", candidate, f"{type(exc).__name__}: {exc}",
                    "source_artifact_read_error",
                )
            )
    else:
        failures.append(
            _failure(
                "SOURCE-MISSING",
                reason="source_identity_mismatch",
                region="model.source",
                evidence={"paths": [str(candidate)] if candidate else []},
                evidence_text="The source candidate is missing or unreadable.",
                expected="A readable candidate matching model.json source metadata.",
            )
        )
    if source_identity:
        source_matches = (
            isinstance(model_source, Mapping)
            and candidate is not None
            and source_path_matches(model_source.get("candidate_path"), candidate)
            and model_source.get("source_sha256") == source_identity["source_sha256"]
            and model_source.get("source_size") == source_identity["source_size"]
        )
        if not source_matches:
            failures.append(
                _failure(
                    "SOURCE-IDENTITY",
                    reason="source_identity_mismatch",
                    region="model.source",
                    evidence={"details": {"actual": source_identity, "recorded": model_source}},
                    evidence_text="model.json source identity does not match the candidate.",
                    expected="candidate_path, source_sha256, and source_size all match.",
                )
            )

    queue_items: list[dict[str, Any]] = []
    active_queue_ids: set[str] = set()
    queue_path = output / "failure_queue.json"
    if queue_path.is_file() and not is_link_or_junction(queue_path):
        queue, error = _read_json(queue_path)
        if error:
            failures.append(
                _read_failure(
                    "FAILURE-QUEUE-JSON", queue_path, error,
                    "invalid_failure_queue_item",
                )
            )
        elif not isinstance(queue, Mapping) or not isinstance(queue.get("failures"), list):
            failures.append(
                _failure(
                    "FAILURE-QUEUE-SCHEMA",
                    reason="invalid_failure_queue_item",
                    region="failure_queue",
                    evidence={"paths": [str(queue_path)], "details": queue},
                    evidence_text="failure_queue.json must contain a failures list.",
                    expected='{"failures": [...]}.',
                )
            )
        else:
            queue_items, invalid_items, active_queue_ids = validate_queue_items(
                queue["failures"]
            )
            failures.extend(queue_items)
            failures.extend(invalid_items)

    profile_result, profile_failures = _evaluate_profile_file(profile, board_path)
    failures.extend(profile_failures)
    failures.extend(validate_report_identity(output, source_identity))

    manifest_path = output / "image" / "visual_review.json"
    if (
        manifest_path.is_file()
        and not is_link_or_junction(manifest_path)
        and image_dir is not None
        and not is_link_or_junction(image_dir)
    ):
        visual_report = validate_visual_manifest(output, manifest_path)
    else:
        visual_report = missing_visual_report(output)
    failures.extend(visual_report["failures"])

    referenced_ids = set(visual_report.get("referenced_failure_ids", []))
    for failure_id in sorted(referenced_ids - active_queue_ids):
        failures.append(
            _failure(
                f"VISUAL-FAILURE-CROSSREF-{failure_id}",
                reason="visual_failure_id_not_in_queue",
                region="visual_manifest",
                evidence={
                    "paths": [str(manifest_path), str(queue_path)],
                    "details": {"failure_id": failure_id},
                },
                evidence_text=f"Visual failure ID {failure_id} is absent from failure_queue.json.",
                expected="Every visual failure ID references an active queue item.",
                suggested_fix="Add the referenced failure to the active queue or resolve the review.",
                can_fix_now=False,
            )
        )

    return {
        "status": merge_status(
            profile_result["status"],
            visual_report["status"],
            status_from_failures(failures),
        ),
        "source_identity": source_identity,
        "artifact_identities": identities,
        "profile_result": profile_result,
        "visual_manifest_report": visual_report,
        "failures": failures,
    }


__all__ = ["validate_delivery", "validate_visual_manifest"]
