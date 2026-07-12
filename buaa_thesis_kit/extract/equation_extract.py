from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any


MATHTYPE_NATIVE_STREAM = "Equation Native"


def extract_mathtype_native_stream(ole_payload: bytes, destination: Path | None = None) -> dict[str, Any]:
    if not ole_payload:
        return {}
    try:
        import olefile
    except Exception:
        return {"native_probe_status": "olefile_unavailable"}
    try:
        ole = olefile.OleFileIO(io.BytesIO(ole_payload))
    except Exception:
        return {"native_probe_status": "not_ole_compound_file"}
    try:
        stream_path = _find_stream(ole, MATHTYPE_NATIVE_STREAM)
        if not stream_path:
            return {"native_probe_status": "native_stream_missing"}
        native = ole.openstream(stream_path).read()
    except Exception:
        return {"native_probe_status": "native_stream_unreadable"}
    finally:
        try:
            ole.close()
        except Exception:
            pass
    info: dict[str, Any] = {
        "native_probe_status": "native_stream_found",
        "native_format": "mathtype_mtef",
        "native_stream_name": MATHTYPE_NATIVE_STREAM,
        "native_sha256": hashlib.sha256(native).hexdigest(),
        "native_size": len(native),
    }
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(native)
        info["native_path"] = str(destination.resolve())
    return info


def _find_stream(ole: Any, stream_name: str) -> list[str] | None:
    for stream in ole.listdir():
        if stream and str(stream[-1]) == stream_name:
            return stream
    return None


def equation_review_items(equations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review = []
    for index, equation in enumerate(equations):
        source = equation.get("source") if isinstance(equation.get("source"), dict) else {}
        item = {
            "id": str(equation.get("id") or equation.get("text") or f"eq-{index + 1}"),
            "kind": str(equation.get("kind") or "unknown"),
            "source_text": str(equation.get("text") or equation.get("kind") or equation.get("id") or ""),
            "source_page": source.get("page_hint"),
            "paragraph_index": source.get("paragraph_index"),
            "context_before": "",
            "context_after": "",
            "context": "",
            "status": "needs_review",
            "needs_review": True,
        }
        item.update(_native_review_fields(equation))
        review.append(item)
    return review


def _native_review_fields(equation: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in ("native_path", "native_format", "native_stream_name", "native_sha256", "native_size", "native_asset"):
        value = equation.get(key)
        if value:
            fields[key] = value
    if fields.get("native_format") == "mathtype_mtef":
        fields.setdefault("conversion_tool", "mathtype_mtef_probe")
        fields.setdefault("conversion_status", "mtef_native_available_converter_missing")
        fields.setdefault("workflow_action", "native_stream_extracted_converter_required")
    return fields
