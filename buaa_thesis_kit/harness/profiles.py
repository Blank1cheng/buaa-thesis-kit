from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_PROFILE_CONFIG_PATH = Path(__file__).with_name("config") / "profiles.yaml"


def _validate_gate_id(gate_id: object, context: str) -> str:
    if not isinstance(gate_id, str) or not gate_id:
        raise ValueError(f"{context} must be a non-empty string gate ID")
    return gate_id


def _validate_gate_tuple(gates: object, context: str) -> tuple[str, ...]:
    if not isinstance(gates, tuple):
        raise ValueError(f"{context} must be a tuple of gate IDs")

    seen: set[str] = set()
    for gate_id in gates:
        gate_id = _validate_gate_id(gate_id, context)
        if gate_id in seen:
            raise ValueError(f"Duplicate gate ID {gate_id!r} in {context}")
        seen.add(gate_id)
    return gates


@dataclass(frozen=True)
class HarnessProfile:
    name: str
    required_gates: tuple[str, ...]
    optional_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Profile name must be a non-empty string")

        required = _validate_gate_tuple(
            self.required_gates, f"profile {self.name!r} required_gates"
        )
        optional = _validate_gate_tuple(
            self.optional_gates, f"profile {self.name!r} optional_gates"
        )
        overlap = set(required) & set(optional)
        if overlap:
            duplicates = ", ".join(sorted(overlap))
            raise ValueError(
                f"Gate IDs cannot be both required and optional in profile "
                f"{self.name!r}: {duplicates}"
            )


def _gate_list_from_config(
    value: object, profile_name: str, field_name: str
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"Profile {profile_name!r} field {field_name!r} must be a list"
        )
    return tuple(value)


def _load_profiles() -> dict[str, HarnessProfile]:
    try:
        raw_config = yaml.safe_load(_PROFILE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to load profile config: {exc}") from exc

    if not isinstance(raw_config, Mapping):
        raise ValueError("Profile config must be a mapping")
    raw_profiles = raw_config.get("profiles")
    if not isinstance(raw_profiles, Mapping) or not raw_profiles:
        raise ValueError("Profile config must contain a non-empty 'profiles' mapping")

    profiles: dict[str, HarnessProfile] = {}
    for name, raw_profile in raw_profiles.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Profile names must be non-empty strings")
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"Profile {name!r} must be a mapping")

        required = _gate_list_from_config(
            raw_profile.get("required_gates"), name, "required_gates"
        )
        optional = _gate_list_from_config(
            raw_profile.get("optional_gates"), name, "optional_gates"
        )
        profiles[name] = HarnessProfile(
            name=name,
            required_gates=required,
            optional_gates=optional,
        )

    return profiles


def load_profile(name: str) -> HarnessProfile:
    profiles = _load_profiles()
    try:
        return profiles[name]
    except (KeyError, TypeError) as exc:
        available = ", ".join(sorted(profiles))
        raise ValueError(
            f"Unknown harness profile {name!r}. Available profiles: {available}"
        ) from exc


def _copy_gate_record(record: object, context: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError(f"{context} must be a mapping")
    if "status" in record:
        status = record["status"]
        if status is not None and not isinstance(status, str):
            raise ValueError(f"{context} status must be a string or empty")
    return deepcopy(dict(record))


def normalize_gate_board(gate_board: object) -> dict[str, dict[str, Any]]:
    if not isinstance(gate_board, Mapping):
        raise ValueError("Gate board must be a mapping")

    normalized: dict[str, dict[str, Any]] = {}
    if "gates" in gate_board:
        gates = gate_board["gates"]
        if not isinstance(gates, list):
            raise ValueError("Legacy gate board field 'gates' must be a list")

        for index, source_record in enumerate(gates):
            record = _copy_gate_record(source_record, f"Gate record at index {index}")
            gate_id = _validate_gate_id(
                record.get("id"), f"Gate record at index {index} id"
            )
            if gate_id in normalized:
                raise ValueError(f"Duplicate gate ID {gate_id!r} in gate board")
            normalized[gate_id] = record
        return normalized

    for source_gate_id, source_record in gate_board.items():
        gate_id = _validate_gate_id(source_gate_id, "Gate board key")
        if gate_id in normalized:
            raise ValueError(f"Duplicate gate ID {gate_id!r} in gate board")
        normalized[gate_id] = _copy_gate_record(
            source_record, f"Gate record {gate_id!r}"
        )
    return normalized


def evaluate_profile(
    profile: str | HarnessProfile, gate_board: object
) -> dict[str, Any]:
    resolved_profile = load_profile(profile) if isinstance(profile, str) else profile
    if not isinstance(resolved_profile, HarnessProfile):
        raise ValueError("profile must be a profile name or HarnessProfile")

    board = normalize_gate_board(gate_board)
    gate_statuses = {
        gate_id: record.get("status") for gate_id, record in board.items()
    }

    missing_gates: list[str] = []
    failed_gates: list[str] = []
    review_gates: list[str] = []
    for gate_id in resolved_profile.required_gates:
        if gate_id not in board:
            missing_gates.append(gate_id)
            continue

        status = board[gate_id].get("status")
        if status == "failed":
            failed_gates.append(gate_id)
        elif status != "pass":
            review_gates.append(gate_id)

    optional_failed_gates: list[str] = []
    optional_review_gates: list[str] = []
    ignored_optional_statuses = {None, "", "pass", "todo", "skipped"}
    for gate_id in resolved_profile.optional_gates:
        if gate_id not in board:
            continue

        status = board[gate_id].get("status")
        if status in ignored_optional_statuses:
            continue
        if status == "failed":
            optional_failed_gates.append(gate_id)
        else:
            optional_review_gates.append(gate_id)

    if missing_gates or failed_gates or optional_failed_gates:
        status = "failed"
    elif review_gates or optional_review_gates:
        status = "needs_review"
    else:
        status = "pass"

    return {
        "profile": resolved_profile.name,
        "status": status,
        "missing_gates": missing_gates,
        "failed_gates": failed_gates,
        "review_gates": review_gates,
        "required_gates": list(resolved_profile.required_gates),
        "optional_gates": list(resolved_profile.optional_gates),
        "optional_failed_gates": optional_failed_gates,
        "optional_review_gates": optional_review_gates,
        "gate_statuses": gate_statuses,
    }
