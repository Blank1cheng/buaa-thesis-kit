from __future__ import annotations

import re
import shutil
import tempfile
import json
from pathlib import Path
from typing import Any

from buaa_thesis_kit.docx_extract import extract_thesis_model
from buaa_thesis_kit.frontmatter_render.render_taskbook import (
    build_task_book_model,
    task_book_review_items,
)
from buaa_thesis_kit.graph import GraphRunner, GraphState, NodeResult
from buaa_thesis_kit.graph_nodes import (
    apply_word_fixes,
    decide,
    diagnose_compliance,
    inspect_source_features,
    plan_minimal_fixes,
    visual_compare,
)
from buaa_thesis_kit.harness.validators import run_role_quiz, validate_model_file, validate_output_text_file
from buaa_thesis_kit.harness.artifact_identity import artifact_identity
from buaa_thesis_kit.harness.progress import write_progress_artifacts
from buaa_thesis_kit.models import EquationItem, ThesisModel
from buaa_thesis_kit.pdf_extract import extract_pdf_model
from buaa_thesis_kit.pdf_export import export_pdf_from_docx
from buaa_thesis_kit.tex_gen import generate_tex
from buaa_thesis_kit.validate import (
    PROCESS_FILE_NAMES,
    PROCESS_FILE_SUFFIXES,
    build_report,
    validate_clean_output,
    write_report_md,
)
from buaa_thesis_kit.word_convert import convert_doc_to_docx
from scripts.validate_instrumented_template import validate_instrumented_template, validate_instrumented_template_file
from scripts.validate_render_smoke import validate_render_smoke


DEFAULT_DOCX_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "templates" / "official" / "buaa_undergraduate_template_instrumented.docx"
)
DEFAULT_OFFICIAL_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "templates" / "official" / "buaa_undergraduate_template.docx"
)
LEGACY_DOCX_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "templates" / "buaa_undergraduate_thesis_template.docx"
)
PUBLIC_OUTPUT_STATUSES = {
    "harness": "missing",
    "word": "missing",
    "pdf": "missing",
    "tex": "missing",
    "report.md": "pass",
    "image": "missing",
    "model.json": "missing",
    "template_inheritance_report.json": "missing",
}


def run_pipeline(
    source: Path,
    output_dir: Path,
    template_path: Path | None = None,
    keep_work: bool = False,
    strict: bool = False,
    sample_mode: str = "full",
) -> dict[str, Any]:
    """Run the BUAA thesis repair-first graph pipeline."""
    sample_mode = _normalize_sample_mode(sample_mode)
    source_path = Path(source).expanduser().resolve(strict=False)
    output_root = _prepare_output_dir(Path(output_dir), source_path)
    image_dir = output_root / "image"
    image_dir.mkdir(parents=True, exist_ok=True)

    outputs = dict(PUBLIC_OUTPUT_STATUSES)
    outputs["image"] = "pass"
    blocking_items: list[str] = []
    manual_review: list[str] = []
    notes: list[str] = []
    model = ThesisModel()
    work_dir: Path | None = None
    remove_work = False

    try:
        source_suffix = source_path.suffix.lower()
        if source_suffix not in {".doc", ".docx", ".pdf"}:
            blocking_items.append(
                f"Supported input types are DOC, DOCX, and PDF; unsupported source: {source_path.name}"
            )
            return _finalize_report(
                source_path,
                output_root,
                outputs,
                _summary(model),
                blocking_items,
                manual_review,
                notes,
                _metadata_report(model),
                {},
                [],
                [],
                strict=strict,
                sample_mode=sample_mode,
            )

        work_dir, remove_work = _prepare_work_dir(output_root, keep_work)
        if keep_work:
            notes.append(f"Work directory retained: {work_dir}")

        word_template = _resolve_word_template(Path(template_path) if template_path is not None else None)
        state = GraphState(
            source_path=source_path,
            output_root=output_root,
            work_dir=work_dir,
            template_path=word_template,
            sample_mode=sample_mode,
            outputs=outputs,
        )
        state.notes.extend(notes)
        state.blocking_items.extend(blocking_items)
        state.manual_review.extend(manual_review)

        graph = GraphRunner(_pipeline_nodes(source_suffix, image_dir), start_node="ingest")
        state = graph.run(state)
        model = state.model
        model_json = output_root / "model.json"
        _write_model_json(model, model_json)
        state.outputs["model.json"] = _file_status(model_json)
        state.notes.append(f"Graph nodes executed: {' -> '.join(state.history)}")

        return _finalize_report(
            source_path,
            output_root,
            state.outputs,
            _summary(model),
            state.blocking_items,
            state.manual_review,
            state.notes,
            _metadata_report(model),
            state.editability,
            _ocr_report(model),
            _equation_report(model),
            strict=strict,
            sample_mode=sample_mode,
            template_path=state.template_path,
        )
    finally:
        if work_dir is not None and remove_work:
            _remove_work_dir(work_dir, output_root)


def _pipeline_nodes(source_suffix: str, image_dir: Path) -> dict[str, Any]:
    def ingest(state: GraphState) -> NodeResult:
        if source_suffix == ".doc":
            converted_source = state.work_dir / "source.docx"
            conversion_ok, conversion_message = convert_doc_to_docx(state.source_path, converted_source)
            if conversion_ok:
                state.extraction_source = converted_source
                state.source_kind = "docx"
                state.notes.append(conversion_message)
                return NodeResult(next_node="profile_reference")
            state.blocking_items.append(f"DOC conversion blocking: {conversion_message}")
            return NodeResult(next_node="finalize_output")

        state.extraction_source = state.source_path
        state.source_kind = source_suffix.lstrip(".")
        return NodeResult(next_node="profile_reference")

    def profile_reference(state: GraphState) -> NodeResult:
        reference_pdf = Path("C:/Users/admin/Desktop/\u5d14\u6da6\u660a\u6bd5\u8bbe\u6253\u5370\u7248.pdf")
        if reference_pdf.exists():
            state.notes.append(f"Reference PDF available for visual profile: {reference_pdf}")
        else:
            state.manual_review.append(f"Reference PDF missing, visual profile skipped: {reference_pdf}")
        return NodeResult(next_node="inspect_source")

    def inspect_source(state: GraphState) -> NodeResult:
        try:
            if state.source_kind == "docx":
                state.model = extract_thesis_model(Path(state.extraction_source), state.work_dir)
            else:
                state.model = extract_pdf_model(Path(state.extraction_source), state.work_dir)
        except Exception as exc:  # python-docx/ZIP/XML failures are reported, not leaked.
            state.model = ThesisModel(status="failed")
            state.model.extraction_warnings.append(f"extraction failed unexpectedly: {exc}")
        return NodeResult(next_node="validate_model")

    def validate_model_gate(state: GraphState) -> NodeResult:
        model_json = state.output_root / "model.json"
        _write_model_json(state.model, model_json)
        state.outputs["model.json"] = _file_status(model_json)
        report = validate_model_file(
            model_json,
            sample_mode=state.sample_mode,
            output_report=state.output_root / "harness" / "model_validation_report.json",
        )
        _record_harness_stage(state, "model", "model_validation_report.json", report)
        if report["status"] != "pass":
            state.blocking_items.append(f"harness_model_failed: {_failure_ids(report)}")
            return NodeResult(next_node="finalize_output")
        state.notes.append("Harness model validation passed.")
        return NodeResult(next_node="inspect_source_features")

    def export_pdf(state: GraphState) -> NodeResult:
        state.notes.extend(_copy_final_figure_assets(state.model, image_dir))
        state.notes.extend(_sync_ocr_ledger_images(state.model))
        state.notes.extend(_copy_final_equation_assets(state.model, image_dir))

        thesis_docx = state.output_root / "thesis.docx"
        if state.authoritative_docx is not None and state.authoritative_docx.exists():
            try:
                shutil.copy2(state.authoritative_docx, thesis_docx)
                state.outputs["word"] = _file_status(thesis_docx)
            except OSError as exc:
                state.outputs["word"] = "failed"
                state.blocking_items.append(f"Word DOCX finalization failed: {exc}")
        else:
            state.outputs["word"] = "failed"
            state.blocking_items.append("Word DOCX generation failed: no authoritative DOCX was produced.")

        if state.outputs["word"] in {"pass", "needs_review"}:
            output_text_report = validate_output_text_file(
                thesis_docx,
                state.output_root / "harness" / "output_text_report.json",
            )
            _record_harness_stage(state, "output_text", "output_text_report.json", output_text_report)
            if output_text_report["status"] != "pass":
                state.blocking_items.append(f"harness_output_text_failed: {_failure_ids(output_text_report)}")
                state.outputs["pdf"] = "failed"
                state.outputs["tex"] = "failed"
                return NodeResult(next_node="visual_compare")

        thesis_tex = state.output_root / "thesis.tex"
        tex_needs_review = False
        try:
            generate_tex(state.model, thesis_tex, image_root=image_dir)
            tex_needs_review = _tex_contains_review_markers(thesis_tex)
            state.outputs["tex"] = "needs_review" if tex_needs_review else _file_status(thesis_tex)
        except Exception as exc:
            state.outputs["tex"] = "failed"
            state.blocking_items.append(f"TeX generation failed: {exc}")

        thesis_pdf = state.output_root / "thesis.pdf"
        if state.outputs["word"] in {"pass", "needs_review"}:
            pdf_ok, pdf_message = export_pdf_from_docx(thesis_docx, thesis_pdf)
            if pdf_ok:
                output_text_post_report = validate_output_text_file(
                    thesis_docx,
                    state.output_root / "harness" / "output_text_post_finalize_report.json",
                )
                _record_harness_stage(
                    state,
                    "output_text_post_finalize",
                    "output_text_post_finalize_report.json",
                    output_text_post_report,
                )
                if output_text_post_report["status"] != "pass":
                    state.blocking_items.append(
                        f"harness_output_text_post_finalize_failed: {_failure_ids(output_text_post_report)}"
                    )
                    state.outputs["pdf"] = "failed"
                    return NodeResult(next_node="visual_compare")
                state.outputs["pdf"] = "pass"
                state.notes.append(pdf_message)
                state.notes.extend(_write_template_diff_preview(thesis_pdf, state.output_root))
                render_smoke_report = _run_render_smoke_gate(state, thesis_docx, thesis_pdf)
                if render_smoke_report["status"] != "pass":
                    state.manual_review.append(
                        f"render_smoke_failed: {_failure_ids(render_smoke_report)}"
                    )
            else:
                state.outputs["pdf"] = "failed"
                state.blocking_items.append(f"PDF export blocking: {pdf_message}")
        else:
            state.outputs["pdf"] = "failed"
            state.blocking_items.append("PDF export skipped: thesis.docx was not generated successfully.")

        if _is_in_place_template(state.template_path) and thesis_docx.exists():
            try:
                from scripts.validate_template_inheritance import validate_template_inheritance

                inheritance_path = state.output_root / "template_inheritance_report.json"
                inheritance = validate_template_inheritance(
                    state.template_path,
                    thesis_docx,
                    inheritance_path,
                    word_com_finalized=state.outputs.get("pdf") == "pass",
                )
                state.outputs["template_inheritance_report.json"] = _file_status(inheritance_path)
                if inheritance["status"] != "pass":
                    state.blocking_items.append("template_inheritance_failed")
                else:
                    state.notes.append("Template inheritance validation passed.")
            except Exception as exc:
                state.outputs["template_inheritance_report.json"] = "failed"
                state.blocking_items.append(f"Template inheritance validation failed: {exc}")
        elif thesis_docx.exists():
            state.outputs["template_inheritance_report.json"] = "missing"
            state.manual_review.append("Template inheritance validation skipped: official instrumented template unavailable.")

        state.manual_review.extend(_manual_review_items(state.model, tex_needs_review))
        return NodeResult(next_node="visual_compare")

    def finalize_output(_state: GraphState) -> NodeResult:
        return NodeResult(next_node=None)

    return {
        "ingest": ingest,
        "profile_reference": profile_reference,
        "inspect_source": inspect_source,
        "validate_model": validate_model_gate,
        "inspect_source_features": inspect_source_features,
        "diagnose_compliance": diagnose_compliance,
        "plan_minimal_fixes": plan_minimal_fixes,
        "apply_word_fixes": apply_word_fixes,
        "export_pdf": export_pdf,
        "visual_compare": visual_compare,
        "decide": decide,
        "finalize_output": finalize_output,
        "revise_plan": plan_minimal_fixes,
    }


def _prepare_output_dir(output_dir: Path, source_path: Path | None = None) -> Path:
    root = output_dir.expanduser().resolve(strict=False)
    _assert_safe_directory_target(root, source_path)
    if root.exists() and not root.is_dir():
        raise ValueError(f"Output path exists and is not a directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for child in list(root.iterdir()):
        _remove_child_inside_root(child, root)
    return root


def _assert_safe_directory_target(path: Path, source_path: Path | None = None) -> None:
    anchor = Path(path.anchor).resolve(strict=False) if path.anchor else None
    if anchor is not None and path == anchor:
        raise ValueError(f"Refusing to clean filesystem root: {path}")
    cwd = Path.cwd().resolve(strict=False)
    if path == cwd:
        raise ValueError(f"Refusing to clean current working directory: {path}")
    if _is_relative_to(cwd, path):
        raise ValueError(f"Refusing to clean directory that contains current workspace: {path}")
    if source_path is not None and _is_relative_to(source_path, path):
        raise ValueError(f"Refusing to clean output directory that contains source file: {path}")


def _remove_child_inside_root(child: Path, root: Path) -> None:
    root_resolved = root.resolve(strict=False)
    if child.parent.resolve(strict=False) != root_resolved:
        raise ValueError(f"Refusing to remove path outside output directory: {child}")

    is_junction = getattr(child, "is_junction", lambda: False)()
    if child.is_symlink():
        child.unlink()
    elif is_junction:
        child.rmdir()
    elif child.is_dir():
        child_resolved = child.resolve(strict=False)
        try:
            child_resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"Refusing to recursively remove path outside output directory: {child}") from exc
        shutil.rmtree(child)
    else:
        child.unlink()


def _prepare_work_dir(output_root: Path, keep_work: bool) -> tuple[Path, bool]:
    if keep_work:
        work_dir = output_root.with_name(f"{output_root.name}_work")
        _assert_adjacent_work_dir(work_dir, output_root)
        work_dir.mkdir(parents=True, exist_ok=True)
        for child in list(work_dir.iterdir()):
            _remove_child_inside_root(child, work_dir)
        return work_dir, False

    work_dir = Path(
        tempfile.mkdtemp(prefix=f"{output_root.name}_work_", dir=str(output_root.parent))
    ).resolve(strict=False)
    _assert_adjacent_work_dir(work_dir, output_root)
    return work_dir, True


def _assert_adjacent_work_dir(work_dir: Path, output_root: Path) -> None:
    if work_dir.resolve(strict=False) == output_root.resolve(strict=False):
        raise ValueError("Work directory must not be the public output directory.")
    if work_dir.resolve(strict=False).parent != output_root.resolve(strict=False).parent:
        raise ValueError(f"Work directory must be adjacent to output directory: {work_dir}")
    if not work_dir.name.startswith(f"{output_root.name}_work"):
        raise ValueError(f"Unexpected work directory name: {work_dir}")


def _remove_work_dir(work_dir: Path, output_root: Path) -> None:
    _assert_adjacent_work_dir(work_dir, output_root)
    if work_dir.exists():
        shutil.rmtree(work_dir)


def _copy_final_figure_assets(model: ThesisModel, image_dir: Path) -> list[str]:
    notes: list[str] = []
    used_names = {path.name for path in image_dir.iterdir()} if image_dir.exists() else set()
    image_dir.mkdir(parents=True, exist_ok=True)

    for figure in model.figures:
        if not figure.path:
            figure.requires_review = True
            notes.append(f"Figure {figure.id} has no source image path.")
            continue

        source = Path(figure.path)
        if not source.exists() or not source.is_file():
            figure.requires_review = True
            notes.append(f"Figure {figure.id} source image missing: {_safe_display_path(source)}")
            continue

        if _is_relative_to(source, image_dir):
            figure.path = str(source.resolve(strict=False))
            used_names.add(source.name)
            continue

        safe_name = _safe_asset_name(source.name)
        if _is_process_filename(safe_name):
            figure.requires_review = True
            notes.append(f"Figure {figure.id} skipped process-like asset name: {safe_name}")
            continue

        destination = _unique_destination(image_dir, safe_name, used_names)
        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            figure.requires_review = True
            notes.append(f"Figure {figure.id} could not be copied to output/image: {exc}")
            continue
        figure.path = str(destination.resolve(strict=False))

    return notes


def _copy_final_equation_assets(model: ThesisModel, image_dir: Path) -> list[str]:
    notes: list[str] = []
    used_names = {path.name for path in image_dir.iterdir()} if image_dir.exists() else set()
    image_dir.mkdir(parents=True, exist_ok=True)

    for equation in model.equations:
        if not equation.preview_path:
            continue

        source = Path(equation.preview_path)
        if not source.exists() or not source.is_file():
            equation.requires_review = True
            notes.append(f"Equation {equation.id} preview image missing: {_safe_display_path(source)}")
            continue

        if _is_relative_to(source, image_dir):
            equation.preview_path = str(source.resolve(strict=False))
            used_names.add(source.name)
            continue

        safe_name = _safe_asset_name(source.name)
        if _is_process_filename(safe_name):
            equation.requires_review = True
            notes.append(f"Equation {equation.id} skipped process-like preview asset name: {safe_name}")
            continue

        destination = _unique_destination(image_dir, safe_name, used_names)
        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            equation.requires_review = True
            notes.append(f"Equation {equation.id} preview could not be copied to output/image: {exc}")
            continue
        equation.preview_path = str(destination.resolve(strict=False))

    return notes


def _sync_ocr_ledger_images(model: ThesisModel) -> list[str]:
    notes: list[str] = []
    page_images = {
        figure.source.page_hint: figure.path
        for figure in model.figures
        if figure.type == "pdf-page-image" and figure.source is not None and figure.source.page_hint is not None
    }
    for item in model.ocr_ledger:
        image_path = page_images.get(item.page)
        if image_path:
            item.image_path = image_path
        elif item.requires_review:
            notes.append(f"OCR ledger page {item.page} has no public evidence image.")
    return notes


def _safe_asset_name(name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name).strip("._")
    return safe_name or "asset.bin"


def _unique_destination(image_dir: Path, filename: str, used_names: set[str]) -> Path:
    path = Path(filename)
    stem = path.stem or "asset"
    suffix = "".join(path.suffixes)
    candidate = filename
    counter = 2
    while candidate in used_names or (image_dir / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return image_dir / candidate


def _is_process_filename(filename: str) -> bool:
    name = filename.lower()
    return name in PROCESS_FILE_NAMES or any(name.endswith(suffix) for suffix in PROCESS_FILE_SUFFIXES)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _safe_display_path(path: Path) -> str:
    return Path(path).name or str(path)


def _file_status(path: Path) -> str:
    return "pass" if path.exists() and path.is_file() and path.stat().st_size > 0 else "failed"


def _write_model_json(model: ThesisModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _record_harness_stage(state: GraphState, stage: str, report_name: str, report: dict[str, Any]) -> None:
    harness_dir = state.output_root / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    report_path = harness_dir / report_name
    if not report_path.exists():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    state.harness_stages.append({"stage": stage, "status": str(report.get("status", "failed")), "report": str(report_path)})
    failed_stage = next((item["stage"] for item in state.harness_stages if item["status"] != "pass"), None)
    harness_status = "failed" if failed_stage else "pass"
    state.outputs["harness"] = harness_status
    status_report = {
        "status": harness_status,
        "failed_stage": failed_stage,
        "stages": state.harness_stages,
    }
    (harness_dir / "status.json").write_text(json.dumps(status_report, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_render_smoke_gate(state: GraphState, thesis_docx: Path, thesis_pdf: Path) -> dict[str, Any]:
    try:
        report = validate_render_smoke(
            candidate=thesis_docx,
            out_dir=state.output_root / "render_smoke",
            existing_pdf=thesis_pdf,
            sample_mode=state.sample_mode,
        )
    except Exception as exc:
        report = {
            "status": "failed",
            "candidate": str(thesis_docx),
            "pdf": str(thesis_pdf),
            "sample_mode": state.sample_mode,
            "failures": [{"id": "render_smoke_exception", "region": "render_smoke", "message": str(exc)}],
        }
        smoke_dir = state.output_root / "render_smoke"
        smoke_dir.mkdir(parents=True, exist_ok=True)
        (smoke_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    state.notes.append("Render smoke report written: " + str(state.output_root / "render_smoke" / "report.json"))
    return report


def _failure_ids(report: dict[str, Any]) -> str:
    failures = report.get("failures", [])
    ids = [str(item.get("id", item.get("rule", "unknown"))) for item in failures if isinstance(item, dict)]
    return ", ".join(ids) if ids else "unknown"


def _write_template_diff_preview(thesis_pdf: Path, output_root: Path) -> list[str]:
    """Render a stable PNG preview for visual template review."""
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        return [f"Template diff preview skipped: PyMuPDF unavailable: {exc}"]

    if not thesis_pdf.exists():
        return [f"Template diff preview skipped: missing PDF: {thesis_pdf.name}"]

    diff_dir = output_root / "template_diff"
    diff_dir.mkdir(parents=True, exist_ok=True)
    try:
        with fitz.open(str(thesis_pdf)) as document:
            if document.page_count == 0:
                return ["Template diff preview skipped: PDF has no pages."]
            page = document.load_page(0)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            preview_path = diff_dir / "candidate_page_001.png"
            pixmap.save(str(preview_path))
    except Exception as exc:
        return [f"Template diff preview failed: {exc}"]
    return [f"Template diff preview written: {preview_path}"]


def _resolve_word_template(template_path: Path | None) -> Path:
    if template_path is not None:
        return _require_valid_instrumented_template(_instrument_if_official_raw(template_path))
    if DEFAULT_DOCX_TEMPLATE.exists():
        return _require_valid_instrumented_template(DEFAULT_DOCX_TEMPLATE)
    if DEFAULT_OFFICIAL_TEMPLATE.exists():
        return _require_valid_instrumented_template(_instrument_if_official_raw(DEFAULT_OFFICIAL_TEMPLATE))
    raise FileNotFoundError(
        "Instrumented official template is missing; expected "
        f"{DEFAULT_DOCX_TEMPLATE}"
    )


def _instrument_if_official_raw(template_path: Path) -> Path:
    candidate = Path(template_path)
    if _is_in_place_template(candidate):
        return candidate
    if candidate.resolve(strict=False) == DEFAULT_OFFICIAL_TEMPLATE.resolve(strict=False):
        from scripts.instrument_official_template import instrument_official_template

        instrument_official_template(candidate, DEFAULT_DOCX_TEMPLATE)
        return DEFAULT_DOCX_TEMPLATE
    return candidate


def _require_valid_instrumented_template(template_path: Path) -> Path:
    report = validate_instrumented_template_file(template_path)
    if report.get("status") != "pass":
        failures = report.get("failures", [])
        ids = [
            str(item.get("id", "unknown"))
            for item in failures
            if isinstance(item, dict)
        ]
        detail = ", ".join(ids) if ids else "unknown"
        raise ValueError(f"Instrumented template validation failed: {detail}")
    return Path(template_path)


def _is_in_place_template(template_path: Path | None) -> bool:
    if template_path is None or not Path(template_path).exists():
        return False
    try:
        import zipfile

        with zipfile.ZipFile(template_path) as package:
            document_xml = package.read("word/document.xml").decode("utf-8", errors="ignore")
    except (OSError, KeyError, zipfile.BadZipFile):
        return False
    return "{{BODY_START}}" in document_xml and "{{BODY_END}}" in document_xml


def _tex_contains_review_markers(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        return "% REVIEW:" in path.read_text(encoding="utf-8")
    except OSError:
        return True


def _summary(model: ThesisModel) -> dict[str, int]:
    return {
        "sections": len(model.sections),
        "figures": len(model.figures),
        "tables": len(model.tables),
        "equations": len(model.equations),
        "references": len(model.references),
        "appendices": len(model.appendices),
        "extraction_warnings": len(model.extraction_warnings),
    }


def _metadata_report(model: ThesisModel) -> dict[str, dict[str, Any]]:
    metadata = model.metadata
    fields = (
        "title_cn",
        "title_en",
        "student_name",
        "student_id",
        "college",
        "major",
        "advisor",
        "date",
        "classification",
        "unit_code",
    )
    report: dict[str, dict[str, Any]] = {}
    for field in fields:
        value = getattr(metadata, field)
        evidence = metadata.evidence.get(field)
        report[field] = {
            "value": value,
            "evidence": evidence.to_dict() if evidence is not None else None,
        }
    return report


def _ocr_report(model: ThesisModel) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in item.to_dict().items()
            if key != "source"
        }
        for item in model.ocr_ledger
    ]


def _equation_report(model: ThesisModel) -> list[dict[str, Any]]:
    return [_equation_report_item(equation) for equation in model.equations]


def _equation_report_item(equation: EquationItem) -> dict[str, Any]:
    return {
        "id": equation.id,
        "kind": equation.kind,
        "status": _equation_status(equation),
        "number": equation.number,
        "text": equation.text,
        "preview_path": equation.preview_path,
        "editable_in_word": _equation_editable_in_word(equation),
        "requires_review": equation.requires_review,
    }


def _equation_status(equation: EquationItem) -> str:
    if equation.omml.strip():
        return "editable_omml"
    if _has_existing_ole_equation(equation):
        return "editable_ole_object"
    if equation.latex.strip() and not equation.requires_review:
        return "trusted_latex"
    if equation.latex.strip():
        return "latex_needs_review"
    if equation.preview_path:
        return "preview_image_needs_review"
    return "manual_transcription_required"


def _equation_editable_in_word(equation: EquationItem) -> bool:
    return bool(equation.omml.strip()) or _has_existing_ole_equation(equation)


def _has_existing_ole_equation(equation: EquationItem) -> bool:
    return bool(
        equation.object_xml.strip()
        and equation.object_path
        and Path(equation.object_path).exists()
    )


def _model_failed_message(model: ThesisModel) -> str:
    details = "; ".join(model.extraction_warnings) if model.extraction_warnings else "no details"
    return f"Extraction failed: {details}"


def _manual_review_items(model: ThesisModel, tex_needs_review: bool) -> list[str]:
    items: list[str] = []
    items.extend(f"Extraction warning: {warning}" for warning in model.extraction_warnings)
    items.extend(task_book_review_items(build_task_book_model(model)))
    if model.status == "needs_review":
        items.append("Model status needs_review: extracted content requires manual review.")
    for figure in model.figures:
        if figure.requires_review:
            label = Path(figure.path).name if figure.path else figure.id
            items.append(f"Figure {figure.id} requires review: {label}")
    for equation in model.equations:
        if equation.requires_review:
            items.append(f"Equation {equation.id} requires review: {equation.kind}")
    if tex_needs_review:
        items.append("TeX review status: needs_review; thesis.tex contains REVIEW markers.")
    return items


def _finalize_report(
    source: Path,
    output_root: Path,
    outputs: dict[str, str],
    summary: dict[str, int],
    blocking_items: list[str],
    manual_review: list[str],
    notes: list[str],
    metadata: dict[str, Any],
    editability: dict[str, Any],
    ocr_ledger: list[dict[str, Any]],
    equation_ledger: list[dict[str, Any]],
    strict: bool = False,
    sample_mode: str = "full",
    template_path: Path | None = None,
) -> dict[str, Any]:
    report_path = output_root / "report.md"
    initial_blocking = _strict_blocking_items(blocking_items, manual_review, outputs, strict=strict)
    report = build_report(
        source=str(source),
        outputs=outputs,
        summary=summary,
        blocking_items=_dedupe(initial_blocking),
        manual_review=_dedupe(manual_review),
        notes=_dedupe(notes),
        metadata=metadata,
        editability=editability,
        ocr_ledger=ocr_ledger,
        equation_ledger=equation_ledger,
    )
    _attach_final_artifact_identity(report, output_root)
    write_report_md(report, report_path)

    clean_ok, clean_messages = validate_clean_output(output_root)
    final_blocking = list(blocking_items)
    final_notes = list(notes)
    if clean_ok:
        final_notes.append("Clean output validation passed.")
    else:
        final_blocking.extend(
            f"Clean output validation failed: {message}" for message in clean_messages
        )
    final_blocking = _strict_blocking_items(final_blocking, manual_review, outputs, strict=strict)

    final_report = build_report(
        source=str(source),
        outputs=outputs,
        summary=summary,
        blocking_items=_dedupe(final_blocking),
        manual_review=_dedupe(manual_review),
        notes=_dedupe(final_notes),
        metadata=metadata,
        editability=editability,
        ocr_ledger=ocr_ledger,
        equation_ledger=equation_ledger,
    )
    _attach_final_artifact_identity(final_report, output_root)
    write_report_md(final_report, report_path)
    _write_harness_progress(output_root, source=source, sample_mode=sample_mode, template_path=template_path)
    return final_report


def _attach_final_artifact_identity(report: dict[str, Any], output_root: Path) -> None:
    thesis_docx = output_root / "thesis.docx"
    if not thesis_docx.exists() or not thesis_docx.is_file():
        return
    model_json = output_root / "model.json"
    report["artifact_identity"] = artifact_identity(
        candidate_path=thesis_docx,
        source_model_path=model_json if model_json.exists() else None,
    )


def _write_harness_progress(
    output_root: Path,
    *,
    source: Path,
    sample_mode: str,
    template_path: Path | None,
) -> None:
    thesis_docx = output_root / "thesis.docx"
    model_json = output_root / "model.json"
    harness_dir = output_root / "harness"
    _ensure_pipeline_harness_reports(harness_dir, template_path=template_path)
    write_progress_artifacts(
        harness_dir,
        candidate_path=thesis_docx if thesis_docx.exists() else None,
        model_path=model_json if model_json.exists() else None,
        template_path=template_path,
        sample_mode=sample_mode,
        commands=[
            "python scripts/run_pipeline.py "
            + str(source)
            + " --out "
            + str(output_root)
            + " --sample-mode "
            + sample_mode
        ],
        render_smoke_dir=output_root / "render_smoke",
    )


def _ensure_pipeline_harness_reports(harness_dir: Path, *, template_path: Path | None) -> None:
    harness_dir.mkdir(parents=True, exist_ok=True)
    role_report = harness_dir / "role_quiz_report.json"
    if not role_report.exists():
        run_role_quiz(role_report)

    template_report = harness_dir / "instrumented_template_report.json"
    if not template_report.exists():
        if template_path is not None and Path(template_path).exists():
            validate_instrumented_template(Path(template_path), template_report)
        else:
            template_report.write_text(
                json.dumps(
                    {
                        "status": "skipped",
                        "template": str(template_path) if template_path is not None else None,
                        "failures": [],
                        "reason": "template_path_not_available",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    bad_fixture_report = harness_dir / "bad_fixture_regression_report.json"
    if not bad_fixture_report.exists():
        bad_fixture_report.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "failures": [],
                    "reason": "not_a_bad_fixture_regression_run",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _strict_blocking_items(
    blocking_items: list[str],
    manual_review: list[str],
    outputs: dict[str, str],
    *,
    strict: bool,
) -> list[str]:
    if not strict:
        return list(blocking_items)
    if not manual_review and not any(status == "needs_review" for status in outputs.values()):
        return list(blocking_items)

    result = list(blocking_items)
    review_count = len(manual_review)
    review_outputs = sorted(key for key, status in outputs.items() if status == "needs_review")
    detail = []
    if review_count:
        detail.append(f"{review_count} manual review item(s)")
    if review_outputs:
        detail.append(f"needs_review outputs: {', '.join(review_outputs)}")
    result.append(
        "strict_finalization_failed: "
        + "; ".join(detail)
        + ". Resolve all review items before final submission."
    )
    return result


def _normalize_sample_mode(sample_mode: str) -> str:
    value = str(sample_mode or "full").strip().lower().replace("-", "_")
    if value not in {"full", "truncated"}:
        raise ValueError(f"Unsupported sample mode: {sample_mode}")
    return value


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


__all__ = ["run_pipeline"]
