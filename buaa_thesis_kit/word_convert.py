from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


REQUIRED_DOCX_PARTS = ("[Content_Types].xml", "_rels/.rels", "word/document.xml")


def convert_doc_to_docx(doc_path: Path, docx_path: Path) -> tuple[bool, str]:
    """Convert a legacy Word .doc file to .docx for extraction."""
    source = Path(doc_path)
    target = Path(docx_path)

    if not source.exists():
        return False, f"Source DOC missing: {source}"
    if not source.is_file():
        return False, f"Source DOC is not a file: {source}"
    if source.suffix.lower() != ".doc":
        return False, f"Word conversion source must be a .doc file: {source}"
    if target.exists() and target.is_dir():
        return False, f"DOCX output path is a directory, expected a file path: {target}"

    target.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[str] = []

    if os.name == "nt":
        ok, message = _convert_with_word_com(source, target)
        if ok and _is_valid_docx(target):
            return True, "DOC to DOCX converted with Word COM"
        _remove_file_if_exists(target)
        attempts.append(message if not ok else "Word COM produced an invalid DOCX.")
    else:
        attempts.append("Word COM skipped: available only on Windows with Microsoft Word and pywin32.")

    ok, message = _convert_with_libreoffice(source, target)
    if ok and _is_valid_docx(target):
        return True, "DOC to DOCX converted with LibreOffice"
    _remove_file_if_exists(target)
    attempts.append(message if not ok else "LibreOffice produced an invalid DOCX.")

    action = "Install Microsoft Word with pywin32 on Windows, or install LibreOffice/soffice and add it to PATH."
    return False, f"DOC conversion failed. {' '.join(attempts)} {action}"


def _convert_with_word_com(doc_path: Path, docx_path: Path) -> tuple[bool, str]:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        return False, f"Word COM unavailable: {exc}. Install pywin32 and Microsoft Word."

    word = None
    document = None
    initialized = False
    try:
        pythoncom.CoInitialize()
        initialized = True
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(
            str(doc_path.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
        )
        document.SaveAs2(str(docx_path.resolve()), FileFormat=16)
        return True, "Word COM DOC conversion completed"
    except Exception as exc:  # pragma: no cover - depends on local Office installation.
        return False, f"Word COM DOC conversion failed: {exc}"
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        if initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _convert_with_libreoffice(doc_path: Path, docx_path: Path) -> tuple[bool, str]:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        return False, "LibreOffice/soffice not found on PATH."

    with tempfile.TemporaryDirectory(prefix="buaa_doc_") as temp_dir:
        temp_output_dir = Path(temp_dir)
        command = [
            executable,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(temp_output_dir),
            str(doc_path.resolve()),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"LibreOffice DOC conversion failed to run: {exc}"

        if result.returncode != 0:
            output = _truncate_process_output(result.stdout, result.stderr)
            return False, f"LibreOffice DOC conversion failed with exit code {result.returncode}.{output}"

        generated = temp_output_dir / f"{doc_path.stem}.docx"
        if not generated.exists():
            docxs = sorted(temp_output_dir.glob("*.docx"))
            if len(docxs) == 1:
                generated = docxs[0]
            else:
                output = _truncate_process_output(result.stdout, result.stderr)
                return False, f"LibreOffice DOC conversion did not create a DOCX.{output}"

        _remove_file_if_exists(docx_path)
        try:
            shutil.move(str(generated), str(docx_path))
        except (OSError, shutil.Error) as exc:
            return False, f"LibreOffice DOC conversion failed while moving DOCX into place: {exc}"
        return True, "LibreOffice DOC conversion completed"


def _is_valid_docx(path: Path) -> bool:
    try:
        if not path.is_file() or not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
        return all(part in names for part in REQUIRED_DOCX_PARTS)
    except (OSError, zipfile.BadZipFile):
        return False


def _truncate_process_output(stdout: str, stderr: str) -> str:
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    if not combined:
        return ""
    if len(combined) > 500:
        combined = f"{combined[:497]}..."
    return f" Output: {combined}"


def _remove_file_if_exists(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


__all__ = ["convert_doc_to_docx"]
