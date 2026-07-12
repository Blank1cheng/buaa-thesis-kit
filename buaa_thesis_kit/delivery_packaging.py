from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from buaa_thesis_kit.docx_acceptance import _inspect_docx_package
from buaa_thesis_kit.harness.delivery_identity import (
    artifact_manifest_sha256,
    is_link_or_junction,
    sha256_file,
    source_path_matches,
)
from buaa_thesis_kit.latex.compile import compile_latex


_TEX_INCLUDE_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)\\(?P<kind>include|input)\s*"
    r"\{(?P<target>[^{}\r\n]+)\}[ \t]*(?:%[^\r\n]*)?$"
)
_GRAPHICS_RE = re.compile(
    r"\\includegraphics(?P<options>\s*(?:\[[^\]]*\])?\s*)"
    r"\{(?P<target>[^{}]+)\}"
)
_GRAPHIC_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg")
_PUBLIC_ROOT_NAMES = {
    "failure_queue.json",
    "image",
    "model.json",
    "report.md",
    "thesis.docx",
    "thesis.pdf",
    "thesis.tex",
}


@dataclass(frozen=True)
class LatexAsset:
    source: Path
    destination: str


@dataclass(frozen=True)
class FlattenedLatex:
    text: str
    assets: tuple[LatexAsset, ...]


def validate_pipeline_source_identity(
    source_path: Path,
    *,
    model: Mapping[str, Any],
    pipeline_report: Mapping[str, Any],
    extraction_identity: Mapping[str, Any],
) -> dict[str, Any]:
    source = Path(source_path).resolve(strict=True)
    expected = {
        "candidate_path": str(source),
        "source_sha256": sha256_file(source),
        "source_size": source.stat().st_size,
        "source_type": source.suffix.lower().lstrip("."),
    }
    records = (
        ("model.source", model.get("source"), "candidate_path", "source_sha256", "source_size"),
        (
            "report.source_identity",
            pipeline_report.get("source_identity"),
            "candidate_path",
            "source_sha256",
            "source_size",
        ),
        ("harness.source_identity", extraction_identity, "source_path", "sha256", "size"),
    )
    for label, raw, path_key, sha_key, size_key in records:
        if not isinstance(raw, Mapping):
            raise ValueError(f"artifact_identity_mismatch:{label}:missing")
        if not (
            source_path_matches(raw.get(path_key), source)
            and str(raw.get(sha_key) or "").lower() == expected["source_sha256"]
            and raw.get(size_key) == expected["source_size"]
        ):
            raise ValueError(f"artifact_identity_mismatch:{label}")
    return expected


def validate_replace_target(
    output_path: Path,
    *,
    protected_paths: list[Path],
) -> Path:
    raw = Path(output_path).absolute()
    if raw.exists() and is_link_or_junction(raw):
        raise ValueError(f"unsafe_output_replace_target:linked:{raw}")
    output = raw.resolve(strict=False)
    if output.name.casefold() != "output" or output == output.parent:
        raise ValueError(f"unsafe_output_replace_target:name:{output}")
    for protected_path in protected_paths:
        protected = Path(protected_path).resolve(strict=False)
        if protected == output or _inside(protected, output) or _inside(output, protected):
            raise ValueError(
                f"unsafe_output_replace_target:overlaps_protected_path:{output}:{protected}"
            )
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"unsafe_output_replace_target:not_directory:{output}")
        unexpected = {entry.name for entry in output.iterdir()} - _PUBLIC_ROOT_NAMES
        if unexpected:
            names = ",".join(sorted(unexpected))
            raise ValueError(f"unsafe_output_replace_target:unexpected_entries:{names}")
    return output


def validate_semantic_docx(path: Path, *, source_type: str) -> dict[str, Any]:
    candidate = Path(path).resolve(strict=False)
    if (
        not candidate.is_file()
        or candidate.suffix.lower() != ".docx"
        or is_link_or_junction(candidate)
    ):
        raise ValueError(f"invalid_editable_docx:path:{candidate}")
    try:
        package = _inspect_docx_package(candidate)
    except Exception as exc:
        raise ValueError(f"invalid_editable_docx:unreadable:{candidate}") from exc
    editable_characters = len(re.sub(r"\s+", "", str(package.get("document_text") or "")))
    if editable_characters == 0:
        raise ValueError(f"invalid_editable_docx:no_editable_text:{candidate}")
    if source_type.lower() == "pdf":
        if int(package.get("page_screenshot_drawing_count") or 0) > 0:
            raise ValueError(f"invalid_editable_docx:page_screenshot:{candidate}")
        if editable_characters < 20:
            raise ValueError(f"invalid_editable_docx:insufficient_editable_text:{candidate}")
    return {
        "editable_characters": editable_characters,
        "page_screenshot_drawing_count": int(
            package.get("page_screenshot_drawing_count") or 0
        ),
        "drawing_count": int(package.get("drawing_count") or 0),
        "media_count": int(package.get("media_count") or 0),
    }


def verify_flattened_latex_equivalence(
    staging_dir: Path,
    *,
    pipeline_pdf: Path,
    template_dir: Path,
    compiler: Callable[[Path, str], dict[str, Any]] = compile_latex,
) -> dict[str, Any]:
    staging = Path(staging_dir).resolve(strict=True)
    original_pdf = Path(pipeline_pdf).resolve(strict=True)
    template = Path(template_dir).resolve(strict=True)
    verification = staging.parent / f".{staging.name}.latex-verify-{uuid.uuid4().hex}"
    verification.mkdir()
    try:
        _copy_regular_tree(template, verification)
        _copy_regular(staging / "thesis.tex", verification / "thesis.tex")
        _copy_regular_tree(staging / "image", verification / "image")
        compile_report = compiler(verification, "thesis.tex")
        if compile_report.get("status") != "success":
            raise ValueError(
                "flattened_latex_compile_failed:"
                + str(compile_report.get("status") or "unknown")
            )
        rebuilt_value = str(compile_report.get("pdf_path") or "").strip()
        rebuilt_pdf = Path(rebuilt_value) if rebuilt_value else verification / "thesis.pdf"
        if not rebuilt_pdf.is_absolute():
            rebuilt_pdf = verification / rebuilt_pdf
        rebuilt_pdf = rebuilt_pdf.resolve(strict=False)
        if (
            not _inside(rebuilt_pdf, verification)
            or not rebuilt_pdf.is_file()
            or is_link_or_junction(rebuilt_pdf)
        ):
            raise ValueError("flattened_latex_compile_failed:missing_rebuilt_pdf")
        comparison = _compare_pdf_pixels(original_pdf, rebuilt_pdf)
        if comparison["status"] != "pass":
            raise ValueError(
                "flattened_latex_pdf_mismatch:"
                + ",".join(str(page) for page in comparison["mismatch_pages"])
            )
        return {
            "status": "pass",
            "engine": str(compile_report.get("engine") or ""),
            "page_count": comparison["page_count"],
            "pixel_mismatch_pages": [],
        }
    finally:
        if verification.exists():
            shutil.rmtree(verification)


def _copy_regular_tree(source: Path, destination: Path) -> None:
    source_root = Path(source).resolve(strict=True)
    if not source_root.is_dir() or is_link_or_junction(source_root):
        raise ValueError(f"invalid regular tree: {source_root}")
    destination.mkdir(parents=True, exist_ok=True)
    for item in source_root.rglob("*"):
        if is_link_or_junction(item):
            raise ValueError(f"linked artifact cannot enter verification tree: {item}")
        relative = item.relative_to(source_root)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _copy_regular(item, target)


def _compare_pdf_pixels(left_path: Path, right_path: Path) -> dict[str, Any]:
    mismatch_pages: list[int] = []
    with fitz.open(left_path) as left, fitz.open(right_path) as right:
        if left.page_count != right.page_count:
            return {
                "status": "failed",
                "page_count": left.page_count,
                "rebuilt_page_count": right.page_count,
                "mismatch_pages": list(
                    range(1, max(left.page_count, right.page_count) + 1)
                ),
            }
        for page_number in range(1, left.page_count + 1):
            matrix = fitz.Matrix(1.5, 1.5)
            left_pixmap = left[page_number - 1].get_pixmap(matrix=matrix, alpha=False)
            right_pixmap = right[page_number - 1].get_pixmap(matrix=matrix, alpha=False)
            if (
                left_pixmap.width != right_pixmap.width
                or left_pixmap.height != right_pixmap.height
                or left_pixmap.n != right_pixmap.n
                or left_pixmap.samples != right_pixmap.samples
            ):
                mismatch_pages.append(page_number)
        return {
            "status": "failed" if mismatch_pages else "pass",
            "page_count": left.page_count,
            "rebuilt_page_count": right.page_count,
            "mismatch_pages": mismatch_pages,
        }


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_tex_target(target: str, current_file: Path, source_root: Path) -> Path:
    relative = Path(target.strip())
    if relative.is_absolute():
        raise ValueError(f"TeX include is outside source root: {target}")

    candidates = [current_file.parent / relative, source_root / relative]
    for candidate in candidates:
        if not candidate.suffix:
            candidate = candidate.with_suffix(".tex")
        resolved = candidate.resolve()
        if not _inside(resolved, source_root):
            raise ValueError(f"TeX include is outside source root: {target}")
        if resolved.is_file() and not is_link_or_junction(resolved):
            return resolved
    raise FileNotFoundError(f"TeX include does not exist: {target}")


def _expand_tex_file(path: Path, source_root: Path, stack: tuple[Path, ...]) -> str:
    resolved = path.resolve()
    if resolved in stack:
        cycle = " -> ".join(item.as_posix() for item in (*stack, resolved))
        raise ValueError(f"cyclic TeX include: {cycle}")
    if not _inside(resolved, source_root):
        raise ValueError(f"TeX source is outside source root: {resolved}")
    if not resolved.is_file() or is_link_or_junction(resolved):
        raise FileNotFoundError(f"TeX source is missing or linked: {resolved}")

    text = resolved.read_text(encoding="utf-8-sig")

    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        target = match.group("target")
        nested_path = _resolve_tex_target(target, resolved, source_root)
        nested = _expand_tex_file(nested_path, source_root, (*stack, resolved)).rstrip()
        relative = nested_path.relative_to(source_root).as_posix()
        begin = f"% BEGIN inlined {relative}"
        end = f"% END inlined {relative}"
        if kind == "include":
            return f"{begin}\n\\clearpage\n{nested}\n\\clearpage\n{end}"
        return f"{begin}\n{nested}\n{end}"

    return _TEX_INCLUDE_RE.sub(replace, text)


def _resolve_graphic(target: str, source_root: Path) -> Path:
    relative = Path(target.strip().replace("\\", "/"))
    if relative.is_absolute():
        raise ValueError(f"graphic is outside source root: {target}")
    candidates = [source_root / relative]
    if not relative.suffix:
        candidates = [source_root / f"{relative.as_posix()}{suffix}" for suffix in _GRAPHIC_SUFFIXES]
    for candidate in candidates:
        resolved = candidate.resolve()
        if not _inside(resolved, source_root):
            raise ValueError(f"graphic is outside source root: {target}")
        if resolved.is_file() and not is_link_or_junction(resolved):
            return resolved
    raise FileNotFoundError(f"graphic does not exist: {target}")


def flatten_latex_document(entry_tex: Path, source_root: Path) -> FlattenedLatex:
    root = Path(source_root).resolve()
    entry = Path(entry_tex).resolve()
    if not root.is_dir() or is_link_or_junction(root):
        raise ValueError(f"invalid TeX source root: {root}")
    expanded = _expand_tex_file(entry, root, ())

    assets: list[LatexAsset] = []
    destinations: dict[str, Path] = {}

    def replace_graphic(match: re.Match[str]) -> str:
        source = _resolve_graphic(match.group("target"), root)
        destination = source.name
        existing = destinations.get(destination.casefold())
        if existing is not None and existing != source:
            if sha256_file(existing) != sha256_file(source):
                destination = f"{sha256_file(source)[:8]}_{source.name}"
        key = destination.casefold()
        if key not in destinations:
            destinations[key] = source
            assets.append(LatexAsset(source=source, destination=destination))
        options = match.group("options")
        return f"\\includegraphics{options}{{image/{destination}}}"

    flattened = _GRAPHICS_RE.sub(replace_graphic, expanded)
    return FlattenedLatex(text=flattened, assets=tuple(assets))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON file {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_regular(source: Path, destination: Path) -> None:
    if not source.is_file() or is_link_or_junction(source):
        raise ValueError(f"source artifact is missing or linked: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _normalized_failure_queue(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if isinstance(payload, list):
        return {"failures": payload}
    if isinstance(payload, dict) and isinstance(payload.get("failures"), list):
        return payload
    raise ValueError("failure queue must be a list or contain a failures list")


def _manifest_screenshot_source(manifest_dir: Path, value: object) -> tuple[Path, str]:
    if not isinstance(value, str) or not value:
        raise ValueError("visual review screenshot path must be a non-empty string")
    relative = Path(value.replace("\\", "/"))
    if relative.is_absolute():
        raise ValueError(f"visual review screenshot is outside review directory: {value}")
    if relative.parts and relative.parts[0].lower() == "image":
        relative = Path(*relative.parts[1:])
    if len(relative.parts) != 1:
        raise ValueError(f"visual review screenshot must be a flat filename: {value}")
    source = (manifest_dir / relative).resolve()
    if not _inside(source, manifest_dir.resolve()):
        raise ValueError(f"visual review screenshot is outside review directory: {value}")
    return source, relative.name


def _pdf_page_count(path: Path) -> int:
    try:
        with fitz.open(path) as document:
            return document.page_count
    except Exception as exc:
        raise ValueError(f"unable to read thesis PDF: {exc}") from exc


def _artifact_lines(output: Path) -> list[str]:
    files = [path for path in output.iterdir() if path.is_file() and path.name != "report.md"]
    image_dir = output / "image"
    files.extend(path for path in image_dir.iterdir() if path.is_file())
    lines = []
    for path in sorted(files, key=lambda item: item.relative_to(output).as_posix()):
        relative = path.relative_to(output).as_posix()
        lines.append(f"- `{relative}`: `{sha256_file(path)}` ({path.stat().st_size} bytes)")
    return lines


def _compile_environment(workdir: Path) -> dict[str, str]:
    log_path = workdir / "compile.log"
    try:
        log = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log = ""
    latexmk_match = re.search(r"Latexmk:.*?Version\s+([0-9.]+)", log)
    xetex_match = re.search(
        r"This is XeTeX, Version\s+([^\r\n]+)", log
    )
    class_match = re.search(
        r"Document Class: buaathesis\s+(.+?)(?:\s+The LaTeX|\r?$)",
        log,
        flags=re.MULTILINE,
    )
    return {
        "latexmk": (
            f"Latexmk {latexmk_match.group(1).rstrip('.')}"
            if latexmk_match
            else "unknown"
        ),
        "xetex": f"XeTeX {xetex_match.group(1).strip()}" if xetex_match else "unknown",
        "class_version": class_match.group(1).strip() if class_match else "unknown",
    }


def _template_source(run_dir: Path) -> str:
    path = run_dir / "template_inspection.json"
    if not path.is_file() or is_link_or_junction(path):
        return "unknown"
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return "unknown"
    clone_url = payload.get("clone_url")
    return clone_url if isinstance(clone_url, str) and clone_url else "unknown"


def _declared_fonts(class_path: Path) -> list[str]:
    try:
        text = class_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    fonts = re.findall(r"\\setmainfont(?:\[[^\]]*\])?\{([^{}]+)\}", text)
    fonts.extend(
        re.findall(
            r"\\setCJKfamilyfont\{[^{}]+\}(?:\[[^\]]*\])?\{([^{}]+)\}",
            text,
        )
    )
    return list(dict.fromkeys(font.strip() for font in fonts if font.strip()))


def _pdf_font_inventory(pdf_path: Path) -> list[str]:
    fonts: set[str] = set()
    try:
        with fitz.open(pdf_path) as document:
            for page in document:
                for record in page.get_fonts(full=True):
                    if len(record) > 3 and isinstance(record[3], str) and record[3]:
                        fonts.add(record[3])
    except Exception:
        return []
    return sorted(fonts)


def _gate_statuses(gate_board: dict[str, Any]) -> str:
    statuses = []
    for gate_id, record in sorted(gate_board.items()):
        if isinstance(record, dict):
            statuses.append(f"{gate_id}={record.get('status', 'unknown')}")
    return ", ".join(statuses) if statuses else "none"


def _write_delivery_report(
    output: Path,
    *,
    source: Path,
    source_sha256: str,
    source_size: int,
    template_dir: Path,
    pipeline_report: dict[str, Any],
    visual_manifest: dict[str, Any],
    queue: dict[str, Any],
    gate_board: dict[str, Any],
    run_dir: Path,
    latex_verification: dict[str, Any],
) -> str:
    manifest_sha = artifact_manifest_sha256(output)
    class_path = template_dir / "buaathesis.cls"
    class_sha = sha256_file(class_path) if class_path.is_file() else "missing"
    compile_environment = _compile_environment(run_dir / "workdir")
    template_source = _template_source(run_dir)
    declared_fonts = _declared_fonts(class_path)
    pdf_fonts = _pdf_font_inventory(output / "thesis.pdf")
    compile_status = pipeline_report.get("compile_status") or {}
    equations = pipeline_report.get("equations") or {}
    reviews = visual_manifest.get("reviews") or []
    review_statuses: dict[str, int] = {}
    for review in reviews:
        if isinstance(review, dict):
            status = str(review.get("status") or "unknown")
            review_statuses[status] = review_statuses.get(status, 0) + 1
    source_note = (
        "The editable DOCX is a byte-preserving copy of the DOCX source. "
        "The normalized pagination is represented by thesis.tex and thesis.pdf."
        if source.suffix.lower() == ".docx"
        else "The editable DOCX is a separately supplied semantic reconstruction of the PDF source."
    )
    lines = [
        "# BUAA thesis delivery report",
        "",
        "## Artifact identity",
        f"- source_candidate_path: {source.resolve()}",
        f"- source_sha256: {source_sha256}",
        f"- source_size: {source_size}",
        f"- artifact_manifest_sha256: {manifest_sha}",
        "",
        "## Result",
        f"- Pipeline status: `{pipeline_report.get('status', 'unknown')}`",
        f"- Compile status: `{compile_status.get('status', 'unknown')}`",
        f"- Compile engine: `{compile_status.get('engine', 'unknown')}`",
        f"- Active failure count: `{len(queue.get('failures', []))}`",
        f"- Harness gates: `{_gate_statuses(gate_board)}`",
        f"- Visual review records: `{len(reviews)}` ({json.dumps(review_statuses, ensure_ascii=False)})",
        f"- PDF pages: `{visual_manifest.get('pdf_page_count', 'unknown')}`",
        f"- Flattened TeX fresh compile: `{latex_verification.get('status', 'unknown')}`",
        f"- Flattened TeX pixel mismatch pages: `{latex_verification.get('pixel_mismatch_pages', [])}`",
        "",
        "## Rendering",
        f"- BUAAthesis template: `{template_dir.resolve()}`",
        f"- BUAAthesis source: `{template_source}`",
        f"- `buaathesis.cls` SHA256: `{class_sha}`",
        f"- BUAAthesis class version: `{compile_environment['class_version']}`",
        f"- XeLaTeX runtime: `{compile_environment['xetex']}`",
        f"- Latexmk runtime: `{compile_environment['latexmk']}`",
        f"- Declared font requirements: `{', '.join(declared_fonts) or 'none recorded'}`",
        f"- PDF font inventory: `{', '.join(pdf_fonts) or 'none'}`",
        "- Reproducible command: `latexmk -xelatex -interaction=nonstopmode -halt-on-error thesis.tex`",
        "- Required engine: XeLaTeX with a TeX Live installation and the fonts required by BUAAthesis.",
        f"- Native LaTeX equations: `{equations.get('native_latex', 0)}/{equations.get('total', 0)}`",
        "- Final body figures are referenced only from `image/` and use bounded dynamic sizing.",
        "",
        "## Editable Word",
        source_note,
        "",
        "## Public artifact hashes",
        *_artifact_lines(output),
        "",
    ]
    report = "\n".join(lines)
    (output / "report.md").write_text(report, encoding="utf-8")
    return manifest_sha


def package_agent_delivery(
    *,
    source_path: Path,
    pipeline_run_dir: Path,
    output_dir: Path,
    visual_manifest_path: Path,
    template_dir: Path,
    editable_docx_path: Path | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    source = Path(source_path).resolve()
    run_dir = Path(pipeline_run_dir).resolve()
    raw_output = Path(output_dir).absolute()
    if raw_output.exists() and is_link_or_junction(raw_output):
        raise ValueError(f"unsafe output directory: {raw_output}")
    output = raw_output.resolve(strict=False)
    manifest_path = Path(visual_manifest_path).resolve()
    template = Path(template_dir).resolve()
    if not source.is_file() or is_link_or_junction(source):
        raise ValueError(f"invalid source candidate: {source}")
    if not run_dir.is_dir() or is_link_or_junction(run_dir):
        raise ValueError(f"invalid pipeline run directory: {run_dir}")
    if output == output.parent or not output.name:
        raise ValueError(f"unsafe output directory: {output}")
    if not template.is_dir() or is_link_or_junction(template):
        raise ValueError(f"invalid BUAAthesis template directory: {template}")
    if output.exists() and replace_existing:
        validate_replace_target(
            output,
            protected_paths=[source, run_dir, manifest_path, template],
        )

    workdir = run_dir / "workdir"
    flattened = flatten_latex_document(workdir / "thesis.tex", workdir)
    pdf = run_dir / "thesis.pdf"
    if not pdf.is_file():
        pdf = workdir / "thesis.pdf"
    model_path = run_dir / "model.json"
    queue_path = run_dir / "harness" / "failure_queue.json"
    pipeline_report_path = run_dir / "report.json"
    extraction_identity_path = run_dir / "harness" / "source_identity_report.json"
    editable = Path(editable_docx_path).resolve() if editable_docx_path else source
    if editable.suffix.lower() != ".docx":
        raise ValueError("a semantic editable DOCX is required for PDF source delivery")
    editable_inspection = validate_semantic_docx(
        editable,
        source_type=source.suffix.lower().lstrip("."),
    )

    model = _read_json(model_path)
    if not isinstance(model, dict):
        raise ValueError("model.json must contain an object")
    pipeline_report = _read_json(pipeline_report_path)
    if not isinstance(pipeline_report, dict):
        raise ValueError("pipeline report must contain an object")
    extraction_identity = _read_json(extraction_identity_path)
    if not isinstance(extraction_identity, dict):
        raise ValueError("source identity report must contain an object")
    source_identity = validate_pipeline_source_identity(
        source,
        model=model,
        pipeline_report=pipeline_report,
        extraction_identity=extraction_identity,
    )
    source_sha = str(source_identity["source_sha256"])
    source_size = int(source_identity["source_size"])
    visual_manifest = _read_json(manifest_path)
    if not isinstance(visual_manifest, dict) or not isinstance(
        visual_manifest.get("reviews"), list
    ):
        raise ValueError("visual manifest must be an object with a reviews list")
    if visual_manifest.get("pdf_sha256") != sha256_file(pdf):
        raise ValueError("visual manifest PDF SHA256 does not match pipeline thesis.pdf")
    if visual_manifest.get("pdf_page_count") != _pdf_page_count(pdf):
        raise ValueError("visual manifest page count does not match pipeline thesis.pdf")

    queue = _normalized_failure_queue(queue_path)
    gate_board = _read_json(run_dir / "harness" / "gate_board.json")
    if not isinstance(gate_board, dict):
        raise ValueError("gate board must contain an object")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        image_dir = staging / "image"
        image_dir.mkdir()
        _copy_regular(editable, staging / "thesis.docx")
        _copy_regular(pdf, staging / "thesis.pdf")
        (staging / "thesis.tex").write_text(flattened.text, encoding="utf-8")
        _write_json(staging / "model.json", model)
        _write_json(staging / "failure_queue.json", queue)

        copied_image_hashes: dict[str, str] = {}

        def copy_image(source_image: Path, filename: str) -> None:
            source_hash = sha256_file(source_image)
            key = filename.casefold()
            existing_hash = copied_image_hashes.get(key)
            if existing_hash is not None and existing_hash != source_hash:
                raise ValueError(f"public image filename collision: {filename}")
            if existing_hash is None:
                _copy_regular(source_image, image_dir / filename)
                copied_image_hashes[key] = source_hash

        for asset in flattened.assets:
            copy_image(asset.source, asset.destination)
        for review in visual_manifest["reviews"]:
            if not isinstance(review, dict):
                raise ValueError("visual review records must be objects")
            screenshot_source, filename = _manifest_screenshot_source(
                manifest_path.parent, review.get("screenshot")
            )
            copy_image(screenshot_source, filename)
        _write_json(image_dir / "visual_review.json", visual_manifest)

        latex_verification = verify_flattened_latex_equivalence(
            staging,
            pipeline_pdf=pdf,
            template_dir=template,
        )

        manifest_sha = _write_delivery_report(
            staging,
            source=source,
            source_sha256=source_sha,
            source_size=source_size,
            template_dir=template,
            pipeline_report=pipeline_report,
            visual_manifest=visual_manifest,
            queue=queue,
            gate_board=gate_board,
            run_dir=run_dir,
            latex_verification=latex_verification,
        )

        if output.exists():
            if not replace_existing:
                raise FileExistsError(f"output directory already exists: {output}")
            validate_replace_target(
                output,
                protected_paths=[source, run_dir, manifest_path, template],
            )
            shutil.rmtree(output)
        staging.replace(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return {
        "status": "packaged",
        "output": str(output),
        "source_candidate_path": str(source),
        "source_sha256": source_sha,
        "source_size": source_size,
        "artifact_manifest_sha256": manifest_sha,
        "pdf_sha256": sha256_file(output / "thesis.pdf"),
        "pdf_page_count": visual_manifest["pdf_page_count"],
        "active_failures": len(queue.get("failures", [])),
        "editable_docx": editable_inspection,
        "latex_verification": latex_verification,
    }


__all__ = [
    "FlattenedLatex",
    "LatexAsset",
    "flatten_latex_document",
    "package_agent_delivery",
    "validate_pipeline_source_identity",
    "validate_replace_target",
    "validate_semantic_docx",
    "verify_flattened_latex_equivalence",
]
