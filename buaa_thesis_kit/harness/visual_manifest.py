from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, UnidentifiedImageError

from .delivery_failures import FAILURE_ID_PATTERN, make_failure
from .delivery_identity import is_link_or_junction, sha256_file
from .profiles import evaluate_profile


REQUIRED_VISUAL_REGIONS = {
    "cover",
    "spine",
    "taskbook",
    "declaration",
    "abstract_cn",
    "abstract_en",
    "toc",
    "chapter_openers",
    "figures_tables_equations",
    "references",
    "acknowledgement_appendix",
}
REVIEW_FIELDS = {
    "region",
    "pages",
    "screenshot",
    "status",
    "checks",
    "bbox",
    "failure_ids",
}
SCREENSHOT_SUFFIXES = {".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
SCREENSHOT_RENDER_SCALES = (1.0, 1.5, 2.0, 3.0)


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _failure(
    semantic_id: str,
    *,
    gate: str,
    status: str,
    reason: str,
    evidence: Any,
    evidence_text: str,
    expected: str,
) -> dict[str, Any]:
    return make_failure(
        semantic_id,
        gate=gate,
        status=status,
        reason=reason,
        region="visual_manifest",
        evidence=evidence,
        evidence_text=evidence_text,
        expected=expected,
        suggested_fix="Repair the visual manifest or regenerate its evidence.",
        can_fix_now=True,
    )


def _resolve_screenshot(image_dir: Path, screenshot: object) -> Path | None:
    if not isinstance(screenshot, str) or not screenshot:
        return None
    relative = Path(screenshot)
    if relative.is_absolute():
        return None
    if relative.parts and relative.parts[0].lower() == "image":
        relative = Path(*relative.parts[1:])
    if not relative.parts or relative.suffix.lower() not in SCREENSHOT_SUFFIXES:
        return None
    try:
        image_root = image_dir.resolve()
        resolved = (image_root / relative).resolve()
        if (
            not resolved.is_relative_to(image_root)
            or not resolved.is_file()
            or is_link_or_junction(resolved)
        ):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _image_is_decodable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (
        OSError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return False


def _screenshot_matches_pdf_region(
    pdf_path: Path,
    *,
    page_number: int,
    bbox: list[float],
    screenshot_path: Path,
) -> bool:
    try:
        with Image.open(screenshot_path) as image:
            screenshot = image.convert("RGB")
            screenshot_size = screenshot.size
            screenshot_pixels = screenshot.tobytes()
        clip = fitz.Rect(*bbox)
        with fitz.open(pdf_path) as document:
            page = document[page_number - 1]
            for scale in SCREENSHOT_RENDER_SCALES:
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    clip=clip,
                    alpha=False,
                )
                if (
                    (pixmap.width, pixmap.height) == screenshot_size
                    and pixmap.n == 3
                    and pixmap.samples == screenshot_pixels
                ):
                    return True
    except (
        IndexError,
        OSError,
        RuntimeError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return False
    return False


def _bbox_shape_valid(bbox: object) -> bool:
    return (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in bbox
        )
        and bbox[0] < bbox[2]
        and bbox[1] < bbox[3]
    )


def _empty_result_failure(
    semantic_id: str, reason: str, evidence: Any, evidence_text: str
) -> dict[str, Any]:
    return _failure(
        semantic_id,
        gate="V01",
        status="failed",
        reason=reason,
        evidence=evidence,
        evidence_text=evidence_text,
        expected="A complete visual manifest with one evidence record per PDF page.",
    )


def missing_visual_report(output: Path) -> dict[str, Any]:
    failure = _failure(
        "MISSING-VISUAL-MANIFEST",
        gate="V00",
        status="failed",
        reason="missing_visual_manifest",
        evidence={"paths": [str(output / "image" / "visual_review.json")]},
        evidence_text="The standard visual review manifest is missing.",
        expected="output/image/visual_review.json exists and is valid.",
    )
    gates = {
        "V00": {"status": "failed"},
        "V01": {"status": "failed"},
        "V02": {"status": "needs_review"},
    }
    return {
        "status": "failed",
        "gates": gates,
        "profile_result": evaluate_profile("agent_visual_review", gates),
        "failures": [failure],
        "referenced_failure_ids": [],
    }


def validate_visual_manifest(output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        output = Path(output_dir)
        manifest = Path(manifest_path)
    except TypeError as exc:
        raise ValueError("paths must be path-like values") from exc

    failures: list[dict[str, Any]] = []
    identity_failed = False
    schema_failed = False
    actual_page_count: int | None = None
    page_rects: dict[int, tuple[float, float]] = {}
    review_statuses: list[str] = []
    covered_pages: set[int] = set()
    regions: set[str] = set()
    region_pages: set[tuple[str, int]] = set()
    screenshots: set[str] = set()
    referenced_failure_ids: set[str] = set()

    if is_link_or_junction(manifest):
        payload, read_error = None, "visual manifest is a linked artifact"
    else:
        payload, read_error = _read_json(manifest)
    if read_error:
        identity_failed = schema_failed = True
        failures.extend(
            [
                _failure(
                    "MANIFEST-READ",
                    gate="V00",
                    status="failed",
                    reason="visual_manifest_read_error",
                    evidence={"paths": [str(manifest)], "details": read_error},
                    evidence_text=read_error,
                    expected="A readable regular UTF-8 JSON visual manifest.",
                ),
                _empty_result_failure(
                    "MANIFEST-SCHEMA",
                    "invalid_visual_manifest_schema",
                    {"paths": [str(manifest)], "details": read_error},
                    "The manifest schema cannot be established.",
                ),
            ]
        )
        reviews: list[Any] = []
    elif not isinstance(payload, Mapping):
        identity_failed = schema_failed = True
        reviews = []
        failures.extend(
            [
                _failure(
                    "PDF-IDENTITY-NOT-AVAILABLE",
                    gate="V00",
                    status="failed",
                    reason="visual_pdf_identity_mismatch",
                    evidence={"details": payload},
                    evidence_text="The manifest cannot provide a PDF identity.",
                    expected="pdf_sha256 and pdf_page_count match thesis.pdf.",
                ),
                _empty_result_failure(
                    "MANIFEST-SCHEMA",
                    "invalid_visual_manifest_schema",
                    {"details": payload},
                    "The visual manifest root must be an object.",
                ),
            ]
        )
    else:
        raw_reviews = payload.get("reviews")
        if isinstance(raw_reviews, list):
            reviews = raw_reviews
        else:
            reviews = []
            schema_failed = True
            failures.append(
                _empty_result_failure(
                    "REVIEWS-SCHEMA",
                    "invalid_visual_manifest_schema",
                    {"details": raw_reviews},
                    "reviews must be a list.",
                )
            )

        pdf_path = output / "thesis.pdf"
        actual_sha: str | None = None
        pdf_error: str | None = None
        try:
            if not pdf_path.is_file() or is_link_or_junction(pdf_path):
                raise OSError("thesis.pdf is missing or linked")
            actual_sha = sha256_file(pdf_path)
            with fitz.open(pdf_path) as document:
                actual_page_count = document.page_count
                page_rects = {
                    number: (
                        float(document[number - 1].rect.width),
                        float(document[number - 1].rect.height),
                    )
                    for number in range(1, actual_page_count + 1)
                }
            if actual_page_count <= 0:
                raise ValueError("thesis.pdf has no pages")
        except Exception as exc:
            pdf_error = f"{type(exc).__name__}: {exc}"
            identity_failed = True
            failures.append(
                _failure(
                    "PDF-READ",
                    gate="V00",
                    status="failed",
                    reason="visual_pdf_read_error",
                    evidence={"paths": [str(pdf_path)], "details": pdf_error},
                    evidence_text="thesis.pdf could not be read as a PDF.",
                    expected="A readable PDF with at least one page.",
                )
            )

        if payload.get("pdf_sha256") != actual_sha:
            identity_failed = True
            failures.append(
                _failure(
                    "PDF-SHA256",
                    gate="V00",
                    status="failed",
                    reason="visual_pdf_identity_mismatch",
                    evidence={
                        "paths": [str(pdf_path)],
                        "sha256": actual_sha,
                        "details": {
                            "manifest": payload.get("pdf_sha256"),
                            "error": pdf_error,
                        },
                    },
                    evidence_text="Manifest pdf_sha256 does not match thesis.pdf.",
                    expected="The manifest PDF SHA256 matches thesis.pdf.",
                )
            )
        manifest_count = payload.get("pdf_page_count")
        if (
            not isinstance(manifest_count, int)
            or isinstance(manifest_count, bool)
            or manifest_count != actual_page_count
        ):
            identity_failed = True
            failures.append(
                _failure(
                    "PDF-PAGE-COUNT",
                    gate="V00",
                    status="failed",
                    reason="visual_pdf_page_count_mismatch",
                    evidence={
                        "paths": [str(pdf_path)],
                        "details": {"manifest": manifest_count, "actual": actual_page_count},
                    },
                    evidence_text="pdf_page_count does not match thesis.pdf.",
                    expected="pdf_page_count equals the actual PDF page count.",
                )
            )

    for index, review in enumerate(reviews):
        semantic = f"REVIEW-{index + 1:03d}"
        if not isinstance(review, Mapping) or not REVIEW_FIELDS <= set(review):
            schema_failed = True
            failures.append(
                _empty_result_failure(
                    f"{semantic}-SCHEMA",
                    "invalid_visual_review_schema",
                    {"details": {"index": index, "review": review}},
                    "Review record is missing required fields.",
                )
            )
            continue

        region = review.get("region")
        pages = review.get("pages")
        screenshot = review.get("screenshot")
        status = review.get("status")
        checks = review.get("checks")
        bbox = review.get("bbox")
        failure_ids = review.get("failure_ids")
        region_valid = isinstance(region, str) and bool(region.strip())
        pages_valid = (
            isinstance(pages, list)
            and len(pages) == 1
            and isinstance(pages[0], int)
            and not isinstance(pages[0], bool)
            and pages[0] > 0
        )
        page = pages[0] if pages_valid else None
        page_in_range = pages_valid and (
            actual_page_count is None or page <= actual_page_count
        )
        page_size = page_rects.get(page) if page is not None else None
        bbox_valid = _bbox_shape_valid(bbox) and (
            page_size is None
            or (
                0 <= bbox[0] < bbox[2] <= page_size[0]
                and 0 <= bbox[1] < bbox[3] <= page_size[1]
            )
        )
        checks_valid = isinstance(checks, (list, Mapping)) and bool(checks)
        status_valid = status in {"pass", "needs_review", "failed"}
        ids_valid = (
            isinstance(failure_ids, list)
            and all(
                isinstance(item, str) and FAILURE_ID_PATTERN.fullmatch(item)
                for item in failure_ids
            )
            and (
                (status == "pass" and not failure_ids)
                or (status in {"needs_review", "failed"} and bool(failure_ids))
            )
        )
        if isinstance(failure_ids, list):
            referenced_failure_ids.update(
                item
                for item in failure_ids
                if isinstance(item, str) and FAILURE_ID_PATTERN.fullmatch(item)
            )
        if not all(
            (
                region_valid,
                pages_valid,
                page_in_range,
                bbox_valid,
                checks_valid,
                status_valid,
                ids_valid,
            )
        ):
            schema_failed = True
            failures.append(
                _empty_result_failure(
                    f"{semantic}-SCHEMA",
                    "invalid_visual_review_schema",
                    {"page": page, "bbox": bbox, "details": {"index": index, "review": review}},
                    "Review fields or status/evidence relationship are invalid.",
                )
            )

        if region_valid:
            regions.add(region)
        if region_valid and page_in_range and page is not None:
            pair = (region, page)
            if pair in region_pages:
                schema_failed = True
                failures.append(
                    _empty_result_failure(
                        f"{semantic}-DUPLICATE-REGION-PAGE",
                        "duplicate_visual_review_region_page",
                        {"page": page, "details": {"region": region, "index": index}},
                        "A (region, page) pair appears more than once.",
                    )
                )
            region_pages.add(pair)
        if pages_valid:
            covered_pages.add(page)

        resolved = _resolve_screenshot(output / "image", screenshot)
        if resolved is None:
            identity_failed = True
            failures.append(
                _failure(
                    f"{semantic}-SCREENSHOT-PATH",
                    gate="V00",
                    status="failed",
                    reason="invalid_visual_screenshot_path",
                    evidence={"paths": [str(screenshot)], "page": page},
                    evidence_text="Screenshot is missing or outside output/image.",
                    expected="An existing raster image inside output/image.",
                )
            )
        else:
            key = str(resolved).casefold()
            if key in screenshots:
                schema_failed = True
                failures.append(
                    _empty_result_failure(
                        f"{semantic}-DUPLICATE-SCREENSHOT",
                        "duplicate_visual_screenshot",
                        {"paths": [str(resolved)], "page": page, "bbox": bbox},
                        "A screenshot is reused by multiple review records.",
                    )
                )
            screenshots.add(key)
            if not _image_is_decodable(resolved):
                identity_failed = True
                failures.append(
                    _failure(
                        f"{semantic}-SCREENSHOT-CONTENT",
                        gate="V00",
                        status="failed",
                        reason="invalid_visual_screenshot_content",
                        evidence={
                            "paths": [str(resolved)],
                            "page": page,
                            "bbox": bbox,
                            "sha256": sha256_file(resolved),
                        },
                        evidence_text="Screenshot cannot be decoded as an image.",
                        expected="A nonempty raster image decodable by Pillow.",
                    )
                )
            elif page_in_range and bbox_valid and page is not None:
                if not _screenshot_matches_pdf_region(
                    output / "thesis.pdf",
                    page_number=page,
                    bbox=list(bbox),
                    screenshot_path=resolved,
                ):
                    identity_failed = True
                    failures.append(
                        _failure(
                            f"{semantic}-SCREENSHOT-PDF",
                            gate="V00",
                            status="failed",
                            reason="visual_screenshot_pdf_mismatch",
                            evidence={
                                "paths": [str(resolved), str(output / "thesis.pdf")],
                                "page": page,
                                "bbox": bbox,
                                "sha256": sha256_file(resolved),
                            },
                            evidence_text=(
                                "Screenshot pixels do not match the declared PDF page and bbox."
                            ),
                            expected=(
                                "The screenshot is an exact supported-scale raster of the declared PDF region."
                            ),
                        )
                    )
        review_statuses.append(status if isinstance(status, str) else "unknown")

    missing_regions = sorted(REQUIRED_VISUAL_REGIONS - regions)
    if missing_regions:
        schema_failed = True
        failures.append(
            _empty_result_failure(
                "MISSING-REGIONS",
                "missing_visual_review_region",
                {"details": {"missing_regions": missing_regions}},
                "Required visual review regions are missing.",
            )
        )
    if actual_page_count is not None:
        expected_pages = set(range(1, actual_page_count + 1))
        if covered_pages != expected_pages:
            schema_failed = True
            failures.append(
                _empty_result_failure(
                    "PAGE-COVERAGE",
                    "incomplete_visual_page_coverage",
                    {
                        "details": {
                            "missing_pages": sorted(expected_pages - covered_pages),
                            "out_of_range_pages": sorted(covered_pages - expected_pages),
                        }
                    },
                    "Visual reviews do not cover exactly every PDF page.",
                )
            )

    if "failed" in review_statuses:
        v02_status = "failed"
    elif any(status != "pass" for status in review_statuses):
        v02_status = "needs_review"
    else:
        v02_status = "pass"
    if v02_status != "pass":
        failures.append(
            _failure(
                "REVIEW-STATUS",
                gate="V02",
                status=v02_status,
                reason=(
                    "visual_review_failed"
                    if v02_status == "failed"
                    else "visual_review_needs_review"
                ),
                evidence={"details": {"statuses": review_statuses}},
                evidence_text="One or more visual reviews are unresolved.",
                expected="Every visual review has status pass.",
            )
        )

    gates = {
        "V00": {"status": "failed" if identity_failed else "pass"},
        "V01": {"status": "failed" if schema_failed else "pass"},
        "V02": {"status": v02_status},
    }
    profile_result = evaluate_profile("agent_visual_review", gates)
    return {
        "status": profile_result["status"],
        "gates": gates,
        "profile_result": profile_result,
        "failures": failures,
        "referenced_failure_ids": sorted(referenced_failure_ids),
    }
