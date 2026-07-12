from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def compile_latex(workdir: str | Path, entry: str = "thesis.tex") -> dict[str, Any]:
    workdir = Path(workdir)
    log_path = workdir / "compile.log"
    if not shutil.which("xelatex"):
        log_path.write_text("xelatex not found on PATH\n", encoding="utf-8")
        return {
            "status": "skipped_missing_xelatex",
            "engine": "xelatex",
            "log_path": str(log_path),
            "pdf_exists": False,
        }

    commands: list[list[str]]
    latexmk = shutil.which("latexmk")
    if latexmk:
        commands = [[latexmk, "-xelatex", "-interaction=nonstopmode", "-halt-on-error", entry]]
    else:
        xelatex = shutil.which("xelatex") or "xelatex"
        commands = [[xelatex, "-interaction=nonstopmode", "-halt-on-error", entry] for _ in range(3)]

    logs: list[str] = []
    runs: list[dict[str, Any]] = []
    status = "success"
    for index, command in enumerate(commands, start=1):
        completed = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        logs.append("$ " + " ".join(command))
        logs.append(completed.stdout or "")
        logs.append(completed.stderr or "")
        runs.append({"pass": index, "returncode": completed.returncode, "command": command})
        if completed.returncode != 0:
            status = "failed"
            if latexmk:
                break
    log_path.write_text("\n".join(logs), encoding="utf-8", errors="replace")
    pdf_path = workdir / Path(entry).with_suffix(".pdf").name
    return {
        "status": status if pdf_path.exists() or status == "failed" else "failed",
        "engine": "latexmk-xelatex" if latexmk else "xelatex",
        "runs": runs,
        "log_path": str(log_path),
        "pdf_exists": pdf_path.exists(),
        "pdf_path": str(pdf_path) if pdf_path.exists() else "",
    }
