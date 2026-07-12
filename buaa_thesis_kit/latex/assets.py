from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SUPPORTED_LATEX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
CONVERTIBLE_PREVIEW_EXTENSIONS = {".wmf", ".emf"}


def stage_latex_image_asset(source: Path, target_dir: Path, used_names: set[str]) -> Path | None:
    suffix = source.suffix.lower()
    if suffix in SUPPORTED_LATEX_IMAGE_EXTENSIONS:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _unique_asset_name(source.name, used_names)
        shutil.copy2(source, target)
        return target
    if suffix in CONVERTIBLE_PREVIEW_EXTENSIONS:
        return _convert_vector_preview_to_png(source, target_dir, used_names)
    return None


def _convert_vector_preview_to_png(source: Path, target_dir: Path, used_names: set[str]) -> Path | None:
    converted = _convert_vector_preview_with_system_drawing(source, target_dir, used_names)
    if converted is not None:
        return converted
    return _convert_vector_preview_with_pillow(source, target_dir, used_names)


def _convert_vector_preview_with_system_drawing(source: Path, target_dir: Path, used_names: set[str]) -> Path | None:
    if source.suffix.lower() not in CONVERTIBLE_PREVIEW_EXTENSIONS:
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _unique_asset_name(f"{source.stem}.png", used_names)
    script = r"""
param($srcArg, $dstArg)
$ErrorActionPreference = 'Stop'
$src = [System.IO.Path]::GetFullPath($srcArg)
$dst = [System.IO.Path]::GetFullPath($dstArg)
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($src)
try {
  $maxWidth = 2200
  $maxHeight = 420
  $ratio = [double]$img.Width / [double]$img.Height
  $targetWidth = [int][Math]::Min($maxWidth, [Math]::Max(80, $maxHeight * $ratio))
  $targetHeight = [int][Math]::Max(40, $targetWidth / $ratio)
  if ($targetHeight -gt $maxHeight) {
    $targetHeight = $maxHeight
    $targetWidth = [int][Math]::Max(80, $targetHeight * $ratio)
  }
  $bmp = New-Object System.Drawing.Bitmap $targetWidth, $targetHeight
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  try {
    $g.Clear([System.Drawing.Color]::White)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.DrawImage($img, 0, 0, $bmp.Width, $bmp.Height)
    $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $g.Dispose()
    $bmp.Dispose()
  }
} finally {
  $img.Dispose()
}
"""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
            handle.write(script)
            script_path = Path(handle.name)
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    str(source),
                    str(target),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )
        finally:
            try:
                script_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        return None
    if result.returncode != 0 or not target.exists() or target.stat().st_size <= 0:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    _optimize_png(target)
    return target


def _convert_vector_preview_with_pillow(source: Path, target_dir: Path, used_names: set[str]) -> Path | None:
    try:
        from PIL import Image
    except Exception:
        return None

    try:
        with Image.open(source) as image:
            image.load()
            width, height = image.size
            if width <= 0 or height <= 0:
                return None
            scale = 6
            image = image.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
            if image.mode == "RGBA":
                background = Image.new("RGBA", image.size, "WHITE")
                background.alpha_composite(image)
                image = background.convert("RGB")
            elif image.mode != "RGB":
                image = image.convert("RGB")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / _unique_asset_name(f"{source.stem}.png", used_names)
            image.save(target)
            return target
    except Exception:
        return None


def _optimize_png(path: Path) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    try:
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as image:
            image.save(path, optimize=True)
    except Exception:
        return
    finally:
        try:
            Image.MAX_IMAGE_PIXELS = previous_limit
        except UnboundLocalError:
            pass


def _unique_asset_name(name: str, used_names: set[str]) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name).strip("._") or "asset.png"
    candidate = safe
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate
