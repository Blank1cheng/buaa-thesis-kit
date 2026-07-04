from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def export_pdf_from_docx(docx_path: Path, pdf_path: Path) -> tuple[bool, str]:
    """Export a PDF from a DOCX, preferring Word COM and falling back to LibreOffice."""
    source = Path(docx_path)
    target = Path(pdf_path)

    if not source.exists():
        return False, f"Source DOCX missing: {source}"
    if not source.is_file():
        return False, f"Source DOCX is not a file: {source}"
    if source.suffix.lower() != ".docx":
        return False, f"PDF export source must be a .docx file: {source}"
    if target.exists() and target.is_dir():
        return False, f"PDF output path is a directory, expected a file path: {target}"

    target.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[str] = []

    if os.name == "nt":
        ok, message = _export_with_word_com(source, target)
        if ok:
            verified, reason = _verify_pdf_file(target)
            if verified:
                return True, f"PDF exported from Word COM. {reason}"
            _remove_file_if_exists(target)
            attempts.append(f"Word COM produced an invalid PDF: {reason}")
        else:
            _remove_file_if_exists(target)
            attempts.append(message)
    else:
        attempts.append("Word COM skipped: available only on Windows with Microsoft Word and pywin32.")

    ok, message = _export_with_libreoffice(source, target)
    if ok:
        verified, reason = _verify_pdf_file(target)
        if verified:
            return True, f"PDF exported from LibreOffice. {reason}"
        _remove_file_if_exists(target)
        attempts.append(f"LibreOffice produced an invalid PDF: {reason}")
    else:
        _remove_file_if_exists(target)
        attempts.append(message)

    detail = " ".join(attempts)
    action = "Install Microsoft Word with pywin32 on Windows, or install LibreOffice/soffice and add it to PATH."
    return False, f"PDF export failed. {detail} {action}"


def _verify_pdf_file(pdf_path: Path) -> tuple[bool, str]:
    pdf = Path(pdf_path)
    if not pdf.exists():
        return False, f"PDF output missing: {pdf}"
    if not pdf.is_file():
        return False, f"PDF output is not a file: {pdf}"
    if pdf.stat().st_size == 0:
        return False, f"PDF output is empty: {pdf}"

    try:
        with pdf.open("rb") as handle:
            header = handle.read(4)
    except OSError as exc:
        return False, f"PDF output could not be read for header verification: {exc}"

    if header != b"%PDF":
        return False, f"PDF output does not begin with %PDF: {pdf}"

    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            with pdf.open("rb") as handle:
                tail = handle.read()[-2048:]
        except OSError as exc:
            return False, f"PDF output could not be read for trailer verification: {exc}"
        if b"%%EOF" not in tail:
            return False, f"PDF output is invalid or truncated: missing %%EOF trailer in {pdf}"
        return True, "PDF export verified"

    try:
        reader = PdfReader(str(pdf), strict=True)
        if reader.is_encrypted:
            return False, f"PDF output is encrypted and cannot be verified: {pdf}"
        page_count = len(reader.pages)
        if page_count == 0:
            return False, f"PDF output is invalid: no readable pages in {pdf}"
        for page in reader.pages:
            page.get_object()
    except Exception as exc:
        return False, f"PDF output is invalid or truncated: {exc}"

    return True, "PDF export verified"


def _export_with_word_com(docx_path: Path, pdf_path: Path) -> tuple[bool, str]:
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
            str(docx_path.resolve()),
            ReadOnly=False,
            AddToRecentFiles=False,
        )
        _update_word_fields(document)
        document.Save()
        document.ExportAsFixedFormat(
            OutputFileName=str(pdf_path.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
        )
        return True, "Word COM export completed"
    except Exception as exc:  # pragma: no cover - depends on local Office installation.
        return False, f"Word COM export failed: {exc}"
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


def _update_word_fields(document) -> None:
    try:
        document.Fields.Update()
    except Exception:
        pass
    try:
        for index in range(1, document.TablesOfContents.Count + 1):
            document.TablesOfContents(index).Update()
    except Exception:
        pass


def _export_with_libreoffice(docx_path: Path, pdf_path: Path) -> tuple[bool, str]:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        return False, "LibreOffice/soffice not found on PATH."
    if pdf_path.exists() and pdf_path.is_dir():
        return False, f"LibreOffice PDF output path is a directory, expected a file path: {pdf_path}"

    with tempfile.TemporaryDirectory(prefix="buaa_pdf_") as temp_dir:
        temp_output_dir = Path(temp_dir)
        command = [
            executable,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(temp_output_dir),
            str(docx_path.resolve()),
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
            return False, f"LibreOffice export failed to run: {exc}"

        if result.returncode != 0:
            output = _truncate_process_output(result.stdout, result.stderr)
            return False, f"LibreOffice export failed with exit code {result.returncode}.{output}"

        generated = temp_output_dir / f"{docx_path.stem}.pdf"
        if not generated.exists():
            pdfs = sorted(temp_output_dir.glob("*.pdf"))
            if len(pdfs) == 1:
                generated = pdfs[0]
            else:
                output = _truncate_process_output(result.stdout, result.stderr)
                return False, f"LibreOffice export did not create a PDF.{output}"

        if pdf_path.exists() and pdf_path.is_dir():
            return False, f"LibreOffice PDF output path is a directory, expected a file path: {pdf_path}"

        _remove_file_if_exists(pdf_path)
        try:
            shutil.move(str(generated), str(pdf_path))
        except (OSError, shutil.Error) as exc:
            return False, f"LibreOffice export failed while moving PDF into place: {exc}"
        return True, "LibreOffice export completed"


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
