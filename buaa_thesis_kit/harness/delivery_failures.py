from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .profiles import evaluate_profile, normalize_gate_board


FAILURE_FIELDS = {
    "id",
    "gate",
    "status",
    "reason",
    "region",
    "evidence",
    "evidence_text",
    "expected",
    "suggested_fix",
    "can_fix_now",
}
FAILURE_ID_PATTERN = re.compile(
    r"^H-([A-Z][A-Z0-9]*)-([A-Z0-9]+(?:-[A-Z0-9]+)*)$"
)
EVIDENCE_FIELDS = {"paths", "page", "bbox", "sha256"}


def _token(value: object, fallback: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "-", str(value).upper()).strip("-")
    return token or fallback


def normalize_failure_id(semantic_id: object, gate: object) -> tuple[str, str]:
    gate_token = _token(gate, "DELIVERY").replace("-", "")
    if not gate_token[0].isalpha():
        gate_token = f"G{gate_token}"
    encoded = base64.b32encode(str(semantic_id).encode("utf-8")).decode("ascii")
    return f"H-{gate_token}-K{encoded.rstrip('=')}", gate_token


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value or bool(Path(value).suffix)


def _sha256_if_file(path: str) -> str | None:
    candidate = Path(path)
    try:
        if not candidate.is_file() or candidate.is_symlink():
            return None
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def normalize_evidence(evidence: Any) -> dict[str, Any]:
    paths: list[str] = []
    page: int | None = None
    bbox: list[int | float] | None = None
    sha256: str | None = None
    details = _json_safe(evidence)

    if isinstance(evidence, Mapping):
        raw_paths = evidence.get("paths")
        if isinstance(raw_paths, list) and all(
            isinstance(path, str) for path in raw_paths
        ):
            paths = list(raw_paths)
        elif isinstance(evidence.get("path"), (str, Path)):
            paths = [str(evidence["path"])]
        raw_page = evidence.get("page")
        if isinstance(raw_page, int) and not isinstance(raw_page, bool):
            page = raw_page
        raw_bbox = evidence.get("bbox")
        if _valid_bbox(raw_bbox):
            bbox = list(raw_bbox)
        raw_sha = evidence.get("sha256")
        if isinstance(raw_sha, str) and re.fullmatch(r"[0-9a-fA-F]{64}", raw_sha):
            sha256 = raw_sha.lower()
        if "details" in evidence:
            details = _json_safe(evidence["details"])
    elif isinstance(evidence, (str, Path)):
        value = str(evidence)
        if _looks_like_path(value):
            paths = [value]
    elif isinstance(evidence, list) and all(
        isinstance(item, str) and _looks_like_path(item) for item in evidence
    ):
        paths = list(evidence)

    if sha256 is None and len(paths) == 1:
        sha256 = _sha256_if_file(paths[0])
    return {
        "paths": paths,
        "page": page,
        "bbox": bbox,
        "sha256": sha256,
        "details": details,
    }


def _valid_bbox(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        )
    )


def valid_evidence(evidence: object) -> bool:
    if type(evidence) is not dict or not EVIDENCE_FIELDS <= set(evidence):
        return False
    paths = evidence["paths"]
    page = evidence["page"]
    bbox = evidence["bbox"]
    sha256 = evidence["sha256"]
    return (
        isinstance(paths, list)
        and all(isinstance(path, str) for path in paths)
        and (
            page is None
            or (isinstance(page, int) and not isinstance(page, bool))
        )
        and (bbox is None or _valid_bbox(bbox))
        and (
            sha256 is None
            or (
                isinstance(sha256, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", sha256) is not None
            )
        )
    )


def make_failure(
    semantic_id: str,
    *,
    gate: str,
    status: str,
    reason: str,
    region: str,
    evidence: Any,
    evidence_text: str,
    expected: str,
    suggested_fix: str,
    can_fix_now: bool,
) -> dict[str, Any]:
    failure_id, gate_token = normalize_failure_id(semantic_id, gate)
    return {
        "id": failure_id,
        "gate": gate_token,
        "status": status,
        "reason": reason,
        "region": region,
        "evidence": normalize_evidence(evidence),
        "evidence_text": evidence_text,
        "expected": expected,
        "suggested_fix": suggested_fix,
        "can_fix_now": can_fix_now,
    }


def valid_failure_item(item: object) -> bool:
    if not isinstance(item, Mapping) or not FAILURE_FIELDS <= set(item):
        return False
    string_fields = FAILURE_FIELDS - {"evidence", "can_fix_now"}
    if any(
        not isinstance(item.get(field), str) or not item[field].strip()
        for field in string_fields
    ):
        return False
    match = FAILURE_ID_PATTERN.fullmatch(item["id"])
    return (
        item["status"] in {"failed", "needs_review"}
        and match is not None
        and match.group(1) == item["gate"]
        and valid_evidence(item["evidence"])
        and isinstance(item["can_fix_now"], bool)
    )


def validate_queue_items(
    items: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    counts: dict[str, int] = {}
    for item in items:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            counts[item["id"]] = counts.get(item["id"], 0) + 1
    duplicates = {item_id for item_id, count in counts.items() if count > 1}

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_id = item.get("id") if isinstance(item, Mapping) else None
        if valid_failure_item(item) and item_id not in duplicates:
            valid.append(dict(item))
            continue
        invalid.append(
            make_failure(
                f"QUEUE-ITEM-{index + 1:03d}",
                gate="DELIVERY",
                status="failed",
                reason="invalid_failure_queue_item",
                region=f"failure_queue.failures[{index}]",
                evidence={"details": {"index": index, "item": _json_safe(item)}},
                evidence_text="Failure item is invalid or duplicates another failure id.",
                expected="A unique semantic H-ID and strongly typed failure/evidence fields.",
                suggested_fix="Repair or remove the invalid failure queue item.",
                can_fix_now=True,
            )
        )
    return valid, invalid, {item["id"] for item in valid}


def status_from_failures(failures: list[dict[str, Any]]) -> str:
    return merge_status(*(item.get("status", "pass") for item in failures))


def merge_status(*statuses: str) -> str:
    if "failed" in statuses:
        return "failed"
    if "needs_review" in statuses:
        return "needs_review"
    return "pass"


def failed_profile_result(profile: str) -> dict[str, Any]:
    return {
        "profile": profile,
        "status": "failed",
        "missing_gates": [],
        "failed_gates": [],
        "review_gates": [],
        "required_gates": [],
        "optional_gates": [],
        "optional_failed_gates": [],
        "optional_review_gates": [],
        "gate_statuses": {},
    }


def evaluate_delivery_profile(
    profile: str, board: object
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        result = evaluate_profile(profile, board)
        records = normalize_gate_board(board)
    except ValueError:
        raise
    failures: list[dict[str, Any]] = []
    groups = (
        ("missing_gates", "failed", "missing_required_gate"),
        ("failed_gates", "failed", "required_gate_failed"),
        ("optional_failed_gates", "failed", "optional_gate_failed"),
        ("review_gates", "needs_review", "required_gate_needs_review"),
        ("optional_review_gates", "needs_review", "optional_gate_needs_review"),
    )
    for field, status, reason in groups:
        for gate_id in result.get(field, []):
            failures.append(
                make_failure(
                    f"PROFILE-{reason}-{gate_id}",
                    gate=str(gate_id),
                    status=status,
                    reason=reason,
                    region="gate_board",
                    evidence={"details": records.get(gate_id, {})},
                    evidence_text=f"Profile gate {gate_id} is not pass.",
                    expected=f"Gate {gate_id} has status pass.",
                    suggested_fix=f"Resolve gate {gate_id} and rerun validation.",
                    can_fix_now=False,
                )
            )
    return result, failures
