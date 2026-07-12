from __future__ import annotations

from typing import Any

from .escape import tex_escape


def equation_block(item: dict[str, Any]) -> str:
    latex = str(item.get("latex") or item.get("text") or "").strip()
    if not latex:
        return r"\[\text{公式待复核}\]"
    return "\n".join([r"\begin{equation}", latex, r"\end{equation}"])


def equation_preview_block(item: dict[str, Any]) -> str:
    render_asset = str(item.get("render_asset") or "")
    if not render_asset:
        return r"\[\text{公式预览缺失，需复核}\]"
    return "\n".join(
        [
            r"\begin{center}",
            rf"\adjustbox{{max width=0.72\linewidth,max height=2.0\baselineskip}}{{\includegraphics{{{tex_escape(render_asset)}}}}}",
            r"\end{center}",
        ]
    )


def inline_equation_preview(item: dict[str, Any]) -> str:
    render_asset = str(item.get("render_asset") or "")
    if not render_asset:
        return r"\(\text{公式待复核}\)"
    return rf"\raisebox{{-0.2\height}}{{\includegraphics[height=1.25em,keepaspectratio]{{{tex_escape(render_asset)}}}}}"


def equation_report(
    equations: list[dict[str, Any]],
    body_equations: list[dict[str, Any]],
    rendered_equations: list[dict[str, Any]],
    preview_equations: list[dict[str, Any]],
) -> dict[str, Any]:
    all_items = [*rendered_equations, *preview_equations, *body_equations, *equations]
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(all_items):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or f"anonymous-{index}")
        existing = by_id.setdefault(item_id, {})
        existing.update({key: value for key, value in item.items() if value not in (None, "", [], {})})
    unique_items = list(by_id.values())
    ole_objects = [
        item
        for item in unique_items
        if item.get("source_kind") == "embedded-object"
        or "oleObject" in str(item.get("source_text") or item.get("id") or "")
    ]
    native_streams = [item for item in unique_items if item.get("native_format")]
    native_pipeline_items = [item for item in unique_items if isinstance(item.get("native_conversion"), dict)]
    native_converted = [
        item for item in native_pipeline_items if item.get("native_conversion", {}).get("status") == "converted"
    ]
    translator_warnings = [
        item
        for item in native_pipeline_items
        if any(
            str(failure_id).startswith("H-EQ-003")
            for failure_id in item.get("native_conversion", {}).get("failure_ids") or []
        )
    ]
    return {
        "total": equation_total(rendered_equations, preview_equations, body_equations, equations),
        "native_latex": len(rendered_equations),
        "image_fallback": len([item for item in preview_equations if item.get("render_asset")]),
        "placeholders": len(body_equations),
        "native_latex_complete": False if (preview_equations or equations or body_equations) else True,
        "conversion_tool": (
            "native_equation_pipeline"
            if native_pipeline_items
            else "mathtype_mtef_probe"
            if native_streams
            else "none"
        ),
        "native_streams_found": len(native_streams),
        "mathtype_mtef": len([item for item in native_streams if item.get("native_format") == "mathtype_mtef"]),
        "omml_converted": len(
            [
                item
                for item in native_converted
                if item.get("native_conversion", {}).get("method") == "omml_parser"
            ]
        ),
        "native_pipeline_converted": len(native_converted),
        "translator_warnings": len(translator_warnings),
        "native_latex_rendered": len(rendered_equations),
        "equation_previews_rendered": len([item for item in preview_equations if item.get("render_asset")]),
        "ole_objects": len(ole_objects),
        "placeholders_inserted": len([item for item in body_equations if item.get("insert_in_body")]),
        "workflow": {
            "trusted_latex": "rendered_as_native_latex",
            "docx_omml_or_ole": "converted_only_after_native_compile_and_verification",
            "mathtype_mtef": "sdk_converted_or_stable_review_failure",
            "pdf_image_equation": "recognizer_candidate_requires_review",
            "untrusted_or_missing_latex": "reported_for_review",
        },
        "needs_review": len(equations),
        "needs_review_items": equations,
    }


def equation_total(
    rendered_equations: list[dict[str, Any]],
    preview_equations: list[dict[str, Any]],
    body_equations: list[dict[str, Any]],
    review_equations: list[dict[str, Any]],
) -> int:
    ids = {
        str(item.get("id"))
        for item in [*rendered_equations, *preview_equations, *body_equations, *review_equations]
        if item.get("id")
    }
    if ids:
        return len(ids)
    return len(rendered_equations) + len(preview_equations) + len(body_equations) + len(review_equations)
