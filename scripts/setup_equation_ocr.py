from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_BASE = "https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0"
MODEL_ASSETS = {
    "image_resizer.onnx": {
        "size": 38_967_751,
        "sha256": "e0b075c39700f64d50400f39c8fc186bbb3b5d84d31864008313f376603aca9d",
    },
    "encoder.onnx": {
        "size": 89_008_136,
        "sha256": "01bf5dc25539ca0cd5b1bd29296ea495977a6ba5f629dc4178277809d26e5e7d",
    },
    "decoder.onnx": {
        "size": 50_952_726,
        "sha256": "bd695497bf1b22279b7626f5916c79226e1e244c84355f8da7edfd2d921d0072",
    },
    "tokenizer.json": {
        "size": 24_174,
        "sha256": "1dc27b18d6a518d0d5ff3f4bb7bd98521fe80ad39e5b2a246d4109f1bb9d5019",
    },
}


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a repository-local RapidLaTeXOCR environment with pinned models.")
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv-equation-ocr")
    parser.add_argument("--skip-install", action="store_true")
    namespace = parser.parse_args(args)

    venv_dir = namespace.venv.resolve()
    try:
        venv_dir.relative_to(ROOT.resolve())
    except ValueError:
        parser.error(f"OCR environment must stay inside the repository: {venv_dir}")
    python = _venv_python(venv_dir)
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    if not namespace.skip_install:
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-cache-dir", "-r", str(ROOT / "requirements-equation-ocr.txt")],
            cwd=ROOT,
            check=True,
        )
    package_dir = _rapid_package_dir(python)
    model_dir = package_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, object]] = {}
    for name, expected in MODEL_ASSETS.items():
        target = model_dir / name
        if not _matches(target, expected):
            _download_verified(f"{RELEASE_BASE}/{name}", target, expected)
        manifest[name] = {
            "path": str(target),
            "size": target.stat().st_size,
            "sha256": _sha256(target),
            "source": f"{RELEASE_BASE}/{name}",
        }
    (model_dir / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "status": "pass",
        "venv": str(venv_dir),
        "python": str(python),
        "package_dir": str(package_dir),
        "models": manifest,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _rapid_package_dir(python: Path) -> Path:
    completed = subprocess.run(
        [
            str(python),
            "-c",
            "import json; from pathlib import Path; import rapid_latex_ocr; "
            "print(json.dumps(str(Path(rapid_latex_ocr.__file__).resolve().parent)))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )
    return Path(json.loads(completed.stdout.strip().splitlines()[-1]))


def _download_verified(url: str, target: Path, expected: dict[str, object]) -> None:
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.unlink(missing_ok=True)
    print(f"Downloading {url}", file=sys.stderr)
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(url, timeout=300) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != int(expected["size"]) or digest.hexdigest() != str(expected["sha256"]):
            raise ValueError(
                f"model identity mismatch for {target.name}: size={size}, sha256={digest.hexdigest()}"
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _matches(path: Path, expected: dict[str, object]) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(expected["size"])
        and _sha256(path) == str(expected["sha256"])
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
