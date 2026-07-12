from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class RecognitionResult:
    status: str
    latex: str = ""
    confidence: float | None = None
    engine: str = ""
    reason: str = ""
    warning: str = ""
    audit: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommandImageRecognizer:
    """Run an explicit argv-based image-to-LaTeX command.

    The command must print one JSON object to stdout. ``{image}`` in an argv
    item is replaced with the absolute preview path; when absent, the path is
    appended. A recognizer result is always review-only, regardless of its
    confidence value.
    """

    def __init__(self, argv: Sequence[str], *, timeout_seconds: float = 60.0) -> None:
        self.argv = [str(item) for item in argv]
        self.timeout_seconds = float(timeout_seconds)
        if not self.argv or not self.argv[0].strip():
            raise ValueError("recognizer argv must contain an executable")
        if self.timeout_seconds <= 0:
            raise ValueError("recognizer timeout must be positive")

    def recognize(self, image_path: str | Path) -> RecognitionResult:
        image = Path(image_path).resolve()
        if not image.is_file():
            return RecognitionResult(status="failed", reason="recognizer_input_missing")
        resolved_argv = [item.replace("{image}", str(image)) for item in self.argv]
        if not any("{image}" in item for item in self.argv):
            resolved_argv.append(str(image))
        started = time.monotonic()
        audit: dict[str, Any] = {
            "shell": False,
            "argv_template": self.argv,
            "resolved_argv": resolved_argv,
            "timeout_seconds": self.timeout_seconds,
        }
        try:
            completed = subprocess.run(
                resolved_argv,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            audit["duration_seconds"] = round(time.monotonic() - started, 3)
            return RecognitionResult(status="failed", reason="recognizer_timeout", audit=audit)
        except OSError as exc:
            audit["duration_seconds"] = round(time.monotonic() - started, 3)
            audit["os_error"] = str(exc)
            return RecognitionResult(status="failed", reason="recognizer_launch_failed", audit=audit)
        audit.update(
            {
                "duration_seconds": round(time.monotonic() - started, 3),
                "returncode": completed.returncode,
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            return RecognitionResult(
                status="failed",
                reason="recognizer_nonzero_exit",
                warning=completed.stderr.strip(),
                audit=audit,
            )
        try:
            payload = json.loads(completed.stdout.strip())
        except (json.JSONDecodeError, TypeError):
            audit["stdout"] = completed.stdout.strip()
            return RecognitionResult(status="failed", reason="recognizer_invalid_json", audit=audit)
        if not isinstance(payload, dict):
            return RecognitionResult(status="failed", reason="recognizer_invalid_payload", audit=audit)
        latex = str(payload.get("latex") or "").strip()
        if not latex:
            return RecognitionResult(status="failed", reason="recognizer_empty_latex", audit=audit)
        confidence = _optional_float(payload.get("confidence"))
        metadata = {
            str(key): value
            for key, value in payload.items()
            if key not in {"latex", "confidence", "engine", "warning"}
        }
        return RecognitionResult(
            status="candidate_needs_review",
            latex=latex,
            confidence=confidence,
            engine=str(payload.get("engine") or Path(self.argv[0]).name),
            warning=str(payload.get("warning") or "Image recognition candidates require review."),
            audit=audit,
            metadata=metadata,
        )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_recognizer_argv(value: str) -> list[str]:
    try:
        payload = json.loads(str(value or ""))
    except json.JSONDecodeError as exc:
        raise ValueError("recognizer command must be a JSON array of argv strings") from exc
    if not isinstance(payload, list) or not payload or not all(isinstance(item, str) and item for item in payload):
        raise ValueError("recognizer command must be a non-empty JSON array of argv strings")
    return payload
