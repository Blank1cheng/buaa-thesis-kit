from __future__ import annotations

import contextlib
import importlib.metadata
import io
import time
from pathlib import Path
from typing import Any, Callable


def recognize_formula(
    image_path: str | Path,
    *,
    model_factory: Callable[[], Any] | None = None,
    version_resolver: Callable[[str], str] = importlib.metadata.version,
) -> tuple[dict[str, Any], str]:
    image = Path(image_path).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    logs = io.StringIO()
    started = time.monotonic()
    with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
        if model_factory is None:
            from rapid_latex_ocr import LaTeXOCR

            model_factory = LaTeXOCR
        model = model_factory()
        result = model(image.read_bytes())
    if isinstance(result, tuple):
        latex = str(result[0] or "").strip()
        inference_seconds = _optional_float(result[1] if len(result) > 1 else None)
    else:
        latex = str(result or "").strip()
        inference_seconds = None
    if not latex:
        raise ValueError("RapidLaTeXOCR returned empty LaTeX")
    try:
        version = version_resolver("rapid-latex-ocr")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    payload: dict[str, Any] = {
        "latex": latex,
        "engine": "rapid_latex_ocr",
        "engine_version": version,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    if inference_seconds is not None:
        payload["inference_seconds"] = inference_seconds
    return payload, logs.getvalue().strip()


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
