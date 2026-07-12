from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


FORBIDDEN_COMMANDS = (
    "input",
    "include",
    "includegraphics",
    "usepackage",
    "documentclass",
    "begin{document}",
    "end{document}",
    "write",
    "openout",
    "read",
    "catcode",
    "csname",
    "newcommand",
    "renewcommand",
)


def validate_latex_candidate(latex: str) -> list[str]:
    value = str(latex or "").strip()
    failures: list[str] = []
    if not value:
        failures.append("empty_latex")
        return failures
    if len(value) > 20_000:
        failures.append("latex_too_long")
    lower = value.lower()
    for command in FORBIDDEN_COMMANDS:
        token = "\\" + command
        if token in lower:
            failures.append(f"forbidden_command:{command.split('{', 1)[0]}")
    if not _balanced_groups(value):
        failures.append("unbalanced_braces")
    return failures


def compile_latex_candidate(latex: str, out_dir: str | Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / "candidate.tex"
    standalone = out_dir / "standalone.tex"
    candidate.write_text(str(latex).strip(), encoding="utf-8")
    standalone.write_text(_standalone_document(latex), encoding="utf-8")
    latexmk = shutil.which("latexmk")
    xelatex = shutil.which("xelatex")
    if latexmk:
        command = [latexmk, "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "standalone.tex"]
        engine = "latexmk-xelatex"
    elif xelatex:
        command = [xelatex, "-interaction=nonstopmode", "-halt-on-error", "standalone.tex"]
        engine = "xelatex"
    else:
        return {"status": "skipped_missing_xelatex", "engine": "", "pdf": "", "rendered_png": ""}
    try:
        completed = subprocess.run(
            command,
            cwd=out_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        (out_dir / "compile.log").write_text(str(exc), encoding="utf-8")
        return {"status": "failed", "engine": engine, "returncode": None, "reason": "compile_timeout", "pdf": "", "rendered_png": ""}
    compile_log = "\n".join([completed.stdout, completed.stderr]).strip()
    (out_dir / "compile.log").write_text(compile_log, encoding="utf-8")
    pdf = out_dir / "standalone.pdf"
    status = "success" if completed.returncode == 0 and pdf.is_file() and pdf.stat().st_size > 0 else "failed"
    rendered_png = ""
    render_warning = ""
    if status == "success":
        rendered_png, render_warning = _render_pdf(pdf, out_dir / "rendered")
    _remove_compile_intermediates(out_dir)
    return {
        "status": status,
        "engine": engine,
        "returncode": completed.returncode,
        "pdf": str(pdf) if pdf.exists() else "",
        "rendered_png": rendered_png,
        "render_warning": render_warning,
        "log": str(out_dir / "compile.log"),
    }


def compare_formula_images(source: str | Path, rendered: str | Path, *, threshold: float = 0.72) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"status": "needs_review", "score": None, "threshold": threshold, "reason": "opencv_unavailable"}
    source_image = _read_gray_image(source, cv2, np)
    rendered_image = _read_gray_image(rendered, cv2, np)
    if source_image is None or rendered_image is None:
        return {"status": "needs_review", "score": None, "threshold": threshold, "reason": "image_unreadable"}
    source_crop = _ink_crop(source_image, cv2)
    rendered_crop = _ink_crop(rendered_image, cv2)
    if source_crop is None or rendered_crop is None:
        return {"status": "needs_review", "score": None, "threshold": threshold, "reason": "formula_ink_missing"}
    source_norm = _normalise_formula(source_crop, cv2, np)
    rendered_norm = _normalise_formula(rendered_crop, cv2, np)
    source_mask = source_norm < 220
    rendered_mask = rendered_norm < 220
    kernel = np.ones((3, 3), dtype=np.uint8)
    source_dilated = cv2.dilate(source_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
    rendered_dilated = cv2.dilate(rendered_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
    intersection = float((source_dilated & rendered_dilated).sum())
    union = float((source_dilated | rendered_dilated).sum()) or 1.0
    ink_iou = intersection / union
    source_aspect = source_crop.shape[1] / max(1, source_crop.shape[0])
    rendered_aspect = rendered_crop.shape[1] / max(1, rendered_crop.shape[0])
    aspect_score = math.exp(-abs(math.log(max(source_aspect, 1e-6) / max(rendered_aspect, 1e-6))))
    source_density = float((source_crop < 220).mean())
    rendered_density = float((rendered_crop < 220).mean())
    density_score = math.exp(
        -abs(math.log(max(source_density, 1e-6) / max(rendered_density, 1e-6)))
    )
    source_grid = cv2.resize(source_mask.astype("float32"), (64, 16), interpolation=cv2.INTER_AREA).reshape(-1)
    rendered_grid = cv2.resize(rendered_mask.astype("float32"), (64, 16), interpolation=cv2.INTER_AREA).reshape(-1)
    coarse_grid_score = _cosine_similarity(source_grid, rendered_grid, np)
    source_columns = cv2.GaussianBlur(source_mask.astype("float32"), (0, 0), sigmaX=8).sum(axis=0)
    rendered_columns = cv2.GaussianBlur(rendered_mask.astype("float32"), (0, 0), sigmaX=8).sum(axis=0)
    source_rows = cv2.GaussianBlur(source_mask.astype("float32"), (0, 0), sigmaX=4).sum(axis=1)
    rendered_rows = cv2.GaussianBlur(rendered_mask.astype("float32"), (0, 0), sigmaX=4).sum(axis=1)
    projection_score = 0.65 * _cosine_similarity(source_columns, rendered_columns, np) + 0.35 * _cosine_similarity(
        source_rows, rendered_rows, np
    )
    gray_similarity = 1.0 - float(abs(source_norm.astype("float32") - rendered_norm.astype("float32")).mean()) / 255.0
    # This is a layout smoke test, not a semantic OCR check. Native-source
    # conversion and isolated compilation provide the semantic/grammar gates.
    score = round(
        0.40 * aspect_score
        + 0.30 * density_score
        + 0.10 * coarse_grid_score
        + 0.20 * projection_score,
        4,
    )
    return {
        "status": "pass" if score >= threshold else "needs_review",
        "score": score,
        "threshold": threshold,
        "ink_iou": round(ink_iou, 4),
        "aspect_score": round(aspect_score, 4),
        "ink_density_score": round(density_score, 4),
        "coarse_grid_score": round(coarse_grid_score, 4),
        "projection_score": round(projection_score, 4),
        "gray_similarity": round(gray_similarity, 4),
        "source_size": [int(source_crop.shape[1]), int(source_crop.shape[0])],
        "rendered_size": [int(rendered_crop.shape[1]), int(rendered_crop.shape[0])],
    }


def _balanced_groups(value: str) -> bool:
    depth = 0
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _read_gray_image(path: str | Path, cv2, np):
    try:
        encoded = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)


def _cosine_similarity(left, right, np) -> float:
    left = left.astype("float64")
    right = right.astype("float64")
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 0:
        return 0.0
    return float(np.dot(left, right) / denominator)


def _standalone_document(latex: str) -> str:
    return "\n".join(
        [
            r"\documentclass[preview,border=8pt]{standalone}",
            r"\usepackage{amsmath,mathtools,bm}",
            r"\usepackage{unicode-math}",
            r"\setmathfont{XITS Math}",
            r"\begin{document}",
            r"\[",
            str(latex).strip(),
            r"\]",
            r"\end{document}",
            "",
        ]
    )


def _render_pdf(pdf: Path, prefix: Path) -> tuple[str, str]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return "", "pdftoppm not found"
    completed = subprocess.run(
        [pdftoppm, "-png", "-r", "220", "-singlefile", str(pdf), str(prefix)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    png = prefix.with_suffix(".png")
    if completed.returncode != 0 or not png.exists():
        return "", completed.stderr.strip() or "pdftoppm failed"
    return str(png), ""


def _remove_compile_intermediates(out_dir: Path) -> None:
    for suffix in (".aux", ".fdb_latexmk", ".fls", ".out", ".xdv"):
        (out_dir / f"standalone{suffix}").unlink(missing_ok=True)


def _ink_crop(image, cv2):
    mask = image < 245
    points = cv2.findNonZero(mask.astype("uint8"))
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    pad = 4
    return image[max(0, y - pad) : min(image.shape[0], y + height + pad), max(0, x - pad) : min(image.shape[1], x + width + pad)]


def _normalise_formula(image, cv2, np, *, width: int = 1024, height: int = 256):
    scale = min((width - 16) / max(1, image.shape[1]), (height - 16) / max(1, image.shape[0]))
    resized = cv2.resize(
        image,
        (max(1, int(round(image.shape[1] * scale))), max(1, int(round(image.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    canvas = np.full((height, width), 255, dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas
