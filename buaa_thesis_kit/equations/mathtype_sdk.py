from __future__ import annotations

import ctypes
import os
import re
import struct
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MT_OK = 0
MT_TRANSLATOR_ERROR = -14
MTXFM_LOCAL = -3
MTXFM_MTEF = 4
MTXFM_TEXT = 7
MTXFM_TRANSL_INC_MTDEFAULT = 4
MTXFM_STAT_TRANSL = -2
MTXFM_STAT_ACTUAL_LEN = -1

_SDK_LOCK = threading.Lock()


@dataclass(frozen=True)
class MathTypeConversion:
    status: str
    latex: str = ""
    return_code: int | None = None
    translator_status: int | None = None
    actual_length: int = 0
    translator: str = "AMS LaTeX.tdl"
    dll_path: str = ""
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_mtef_payload(native_stream: bytes) -> bytes:
    """Return MTEF bytes from an Equation Native stream or raw MTEF payload."""
    if len(native_stream) >= 5 and native_stream[0] in {3, 4, 5}:
        return native_stream
    if len(native_stream) >= 33:
        header_size = struct.unpack_from("<I", native_stream, 0)[0]
        if 4 <= header_size < len(native_stream):
            payload = native_stream[header_size:]
            if len(payload) >= 5 and payload[0] in {3, 4, 5}:
                return payload
    raise ValueError("Equation Native stream does not contain a recognizable MTEF payload")


def clean_mathtype_translation(value: str) -> str:
    lines = [line for line in str(value or "").splitlines() if not line.lstrip().startswith("%")]
    text = "\n".join(lines).strip().strip("\x00").strip()
    wrappers = ((r"\[", r"\]"), ("$$", "$$"), ("$", "$"))
    for left, right in wrappers:
        if text.startswith(left) and text.endswith(right) and len(text) >= len(left) + len(right):
            text = text[len(left) : len(text) - len(right)].strip()
            break
    text = re.sub(r"\{\\(?:text|rm)\{\s*=\s*}\}", "=", text)
    text = re.sub(r"\\(?:text|rm)\{\s*=\s*}", "=", text)
    text = re.sub(r"\{\\cal\s+([A-Za-z])}", r"\\mathcal{\1}", text)
    return text.strip()


class MathTypeSdkConverter:
    def __init__(
        self,
        dll_path: str | Path | None = None,
        *,
        translator: str = "AMS LaTeX.tdl",
        timeout_seconds: int = 30,
        output_buffer_size: int = 256 * 1024,
    ) -> None:
        self.dll_path = Path(dll_path) if dll_path else discover_mathtype_dll()
        self.translator = translator
        self.timeout_seconds = timeout_seconds
        self.output_buffer_size = output_buffer_size

    @property
    def available(self) -> bool:
        return bool(sys.platform == "win32" and self.dll_path and self.dll_path.is_file())

    def convert(self, native_stream: bytes) -> MathTypeConversion:
        if not self.available:
            return MathTypeConversion(
                status="unsupported",
                translator=self.translator,
                dll_path=str(self.dll_path or ""),
                warning="MathType SDK DLL is not available",
            )
        try:
            payload = extract_mtef_payload(native_stream)
        except ValueError as exc:
            return MathTypeConversion(
                status="failed",
                translator=self.translator,
                dll_path=str(self.dll_path),
                warning=str(exc),
            )
        with _SDK_LOCK:
            return self._convert_payload(payload)

    def _convert_payload(self, payload: bytes) -> MathTypeConversion:
        dll = _load_sdk(self.dll_path)
        connected = False
        try:
            connect_status = int(dll.MTAPIConnect(0, self.timeout_seconds))
            if connect_status != MT_OK:
                return MathTypeConversion(
                    status="failed",
                    return_code=connect_status,
                    translator=self.translator,
                    dll_path=str(self.dll_path),
                    warning="MTAPIConnect failed",
                )
            connected = True
            dll.MTXFormReset()
            translator_status = int(
                dll.MTXFormSetTranslator(MTXFM_TRANSL_INC_MTDEFAULT, self.translator.encode("ascii"))
            )
            if translator_status != MT_OK:
                return MathTypeConversion(
                    status="failed",
                    return_code=translator_status,
                    translator_status=translator_status,
                    translator=self.translator,
                    dll_path=str(self.dll_path),
                    warning="MathType translator setup failed",
                )
            source = ctypes.create_string_buffer(payload)
            destination = ctypes.create_string_buffer(self.output_buffer_size)
            return_code = int(
                dll.MTXFormEqn(
                    MTXFM_LOCAL,
                    MTXFM_MTEF,
                    source,
                    len(payload),
                    MTXFM_LOCAL,
                    MTXFM_TEXT,
                    destination,
                    len(destination),
                    b"",
                    None,
                )
            )
            actual_length = int(dll.MTXFormGetStatus(MTXFM_STAT_ACTUAL_LEN))
            translation_status = int(dll.MTXFormGetStatus(MTXFM_STAT_TRANSL))
            translated = destination.value.decode("cp1252", errors="replace")
            latex = clean_mathtype_translation(translated)
            if return_code == MT_OK and latex:
                status = "converted"
                warning = ""
            elif return_code == MT_TRANSLATOR_ERROR and latex:
                status = "candidate_needs_review"
                warning = "MathType returned translator_error but emitted a LaTeX candidate"
            else:
                status = "failed"
                warning = "MathType did not emit a usable LaTeX candidate"
            return MathTypeConversion(
                status=status,
                latex=latex,
                return_code=return_code,
                translator_status=translation_status,
                actual_length=max(0, actual_length),
                translator=self.translator,
                dll_path=str(self.dll_path),
                warning=warning,
            )
        except (OSError, ValueError, ctypes.ArgumentError) as exc:
            return MathTypeConversion(
                status="failed",
                translator=self.translator,
                dll_path=str(self.dll_path),
                warning=f"MathType SDK call failed: {exc}",
            )
        finally:
            if connected:
                try:
                    dll.MTAPIDisconnect()
                except Exception:
                    pass


def discover_mathtype_dll() -> Path | None:
    configured = os.environ.get("MATHTYPE_SDK_DLL")
    if configured:
        return Path(configured)
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    bitness = "64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "32"
    candidates = [
        program_files_x86 / "MathType" / "System" / bitness / "MT6.dll",
        program_files_x86 / "MathType" / "System" / "MT6.dll",
    ]
    return next((path for path in candidates if path.is_file()), None)


def _load_sdk(path: Path):
    dll = ctypes.WinDLL(str(path))
    short = ctypes.c_short
    long = ctypes.c_long
    void_p = ctypes.c_void_p
    char_p = ctypes.c_char_p
    dll.MTAPIConnect.argtypes = [short, short]
    dll.MTAPIConnect.restype = long
    dll.MTAPIDisconnect.restype = long
    dll.MTXFormReset.restype = long
    dll.MTXFormSetTranslator.argtypes = [short, char_p]
    dll.MTXFormSetTranslator.restype = long
    dll.MTXFormEqn.argtypes = [short, short, void_p, long, short, short, void_p, long, char_p, void_p]
    dll.MTXFormEqn.restype = long
    dll.MTXFormGetStatus.argtypes = [long]
    dll.MTXFormGetStatus.restype = long
    return dll
