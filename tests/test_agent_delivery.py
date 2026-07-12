import hashlib
import json
import re
import subprocess
from pathlib import Path

import fitz
import pytest
from PIL import Image

from buaa_thesis_kit.harness.delivery import (
    validate_delivery,
    validate_visual_manifest,
)
from scripts import validate_agent_delivery as delivery_cli


REQUIRED_GATES = ("G20", "G21", "G22", "G23", "G24", "G25", "G27", "G28")
REQUIRED_VISUAL_REGIONS = (
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
)
FAILURE_FIELDS = {
    "id",
    "gate",
    "status",
    "reason",
    "region",
    "evidence",
    "evidence_text",
    "expected",
    "suggested_fix",
    "can_fix_now",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color="white").save(path, format="PNG")


def _write_pdf_screenshot(
    pdf_path: Path,
    *,
    page_number: int,
    bbox: list[float],
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as document:
        pixmap = document[page_number - 1].get_pixmap(
            matrix=fitz.Matrix(2, 2),
            clip=fitz.Rect(bbox),
            alpha=False,
        )
        pixmap.save(destination)


def _valid_failure(*, status: str = "needs_review") -> dict[str, object]:
    return {
        "id": "H-G28-001",
        "gate": "G28",
        "status": status,
        "reason": "manual_visual_confirmation_required",
        "region": "cover",
        "evidence": {
            "paths": ["image/cover.png"],
            "page": 1,
            "bbox": [0, 0, 100, 100],
            "sha256": "0" * 64,
        },
        "evidence_text": "Cover requires a final visual confirmation.",
        "expected": "The cover matches the official layout.",
        "suggested_fix": "Review the cover screenshot.",
        "can_fix_now": False,
    }


@pytest.fixture
def delivery_bundle(tmp_path: Path) -> dict[str, Path]:
    candidate = tmp_path / "candidate.docx"
    candidate.write_bytes(b"candidate document bytes")

    output = tmp_path / "output"
    image_dir = output / "image"
    image_dir.mkdir(parents=True)
    (output / "thesis.docx").write_bytes(b"rendered docx")
    pdf = fitz.open()
    for _ in range(len(REQUIRED_VISUAL_REGIONS)):
        pdf.new_page(width=595, height=842)
    pdf.save(output / "thesis.pdf")
    pdf.close()
    (output / "thesis.tex").write_text("\\documentclass{book}\n", encoding="utf-8")
    _write_json(
        output / "model.json",
        {
            "source": {
                "candidate_path": str(candidate),
                "source_sha256": _sha256(candidate),
                "source_size": candidate.stat().st_size,
            }
        },
    )
    _write_json(output / "failure_queue.json", {"failures": []})

    gate_board = tmp_path / "gate_board.json"
    _write_json(
        gate_board,
        {gate_id: {"status": "pass"} for gate_id in REQUIRED_GATES},
    )
    _write_visual_manifest(output)
    _write_report(output, candidate)
    return {"candidate": candidate, "output": output, "gate_board": gate_board}


def _validate(bundle: dict[str, Path]) -> dict[str, object]:
    return validate_delivery(
        bundle["output"],
        profile="latex_pdf",
        gate_board_path=bundle["gate_board"],
        candidate_path=bundle["candidate"],
    )


def _failure_reasons(result: dict[str, object]) -> set[str]:
    return {item["reason"] for item in result["failures"]}


def _assert_normalized_failure(item: dict[str, object]) -> None:
    string_fields = {
        "id",
        "gate",
        "status",
        "reason",
        "region",
        "evidence_text",
        "expected",
        "suggested_fix",
    }
    assert FAILURE_FIELDS <= set(item)
    for field in string_fields:
        assert isinstance(item[field], str) and item[field].strip()
    match = re.fullmatch(
        r"H-([A-Z][A-Z0-9]*)-([A-Z0-9]+(?:-[A-Z0-9]+)*)", item["id"]
    )
    assert match is not None
    assert match.group(1) == item["gate"]
    assert any(character.isalpha() for character in match.group(2))
    assert item["status"] in {"failed", "needs_review"}
    _assert_evidence(item["evidence"])
    assert isinstance(item["can_fix_now"], bool)


def _assert_evidence(evidence: object) -> None:
    assert type(evidence) is dict
    assert {"paths", "page", "bbox", "sha256"} <= set(evidence)
    assert isinstance(evidence["paths"], list)
    assert all(isinstance(path, str) for path in evidence["paths"])
    assert evidence["page"] is None or (
        isinstance(evidence["page"], int) and not isinstance(evidence["page"], bool)
    )
    assert evidence["bbox"] is None or (
        isinstance(evidence["bbox"], list)
        and len(evidence["bbox"]) == 4
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in evidence["bbox"]
        )
    )
    assert evidence["sha256"] is None or re.fullmatch(
        r"[0-9a-f]{64}", evidence["sha256"]
    )


def _write_visual_manifest(
    output: Path,
    *,
    pdf_sha256: str | None = None,
    regions: tuple[str, ...] = REQUIRED_VISUAL_REGIONS,
    review_status: str = "pass",
) -> Path:
    reviews = []
    for index, region in enumerate(regions, start=1):
        screenshot = f"{region}.png"
        bbox = [0, 0, 100, 100]
        _write_pdf_screenshot(
            output / "thesis.pdf",
            page_number=index,
            bbox=bbox,
            destination=output / "image" / screenshot,
        )
        reviews.append(
            {
                "region": region,
                "pages": [index],
                "screenshot": screenshot,
                "status": review_status,
                "checks": ["content", "layout"],
                "bbox": bbox,
                "failure_ids": (
                    [] if review_status == "pass" else [f"H-G28-{index:03d}"]
                ),
            }
        )
    manifest_path = output / "image" / "visual_review.json"
    _write_json(
        manifest_path,
        {
            "pdf_sha256": pdf_sha256 or _sha256(output / "thesis.pdf"),
            "pdf_page_count": len(REQUIRED_VISUAL_REGIONS),
            "reviews": reviews,
        },
    )
    return manifest_path


def _artifact_manifest_sha256(output: Path) -> str:
    files = [
        path
        for path in output.iterdir()
        if path.is_file() and path.name != "report.md"
    ]
    image_dir = output / "image"
    if image_dir.is_dir():
        files.extend(path for path in image_dir.iterdir() if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(output).as_posix()):
        relative_path = path.relative_to(output).as_posix()
        digest.update(
            f"{relative_path}\0{_sha256(path)}\0{path.stat().st_size}\n".encode("utf-8")
        )
    return digest.hexdigest()


def _write_report(output: Path, candidate: Path) -> None:
    (output / "report.md").write_text(
        "# Delivery report\n\n"
        "## Artifact identity\n"
        f"- source_candidate_path: {candidate.resolve()}\n"
        f"- source_sha256: {_sha256(candidate)}\n"
        f"- source_size: {candidate.stat().st_size}\n"
        f"- artifact_manifest_sha256: {_artifact_manifest_sha256(output)}\n",
        encoding="utf-8",
    )


def _refresh_report(bundle: dict[str, Path]) -> None:
    _write_report(bundle["output"], bundle["candidate"])


def test_complete_latex_pdf_delivery_bundle_passes(delivery_bundle):
    result = _validate(delivery_bundle)

    assert result["status"] == "pass"
    assert result["visual_manifest_report"]["status"] == "pass"
    assert result["source_identity"]["source_sha256"] == _sha256(
        delivery_bundle["candidate"]
    )
    assert {"thesis.docx", "thesis.pdf", "thesis.tex", "model.json"} <= set(
        result["artifact_identities"]
    )
    assert result["profile_result"]["profile"] == "latex_pdf"
    assert result["profile_result"]["status"] == "pass"
    assert result["failures"] == []
    expected_image_artifacts = {
        "image/visual_review.json",
        *(f"image/{region}.png" for region in REQUIRED_VISUAL_REGIONS),
    }
    assert expected_image_artifacts <= set(result["artifact_identities"])
    for relative_path in expected_image_artifacts:
        path = delivery_bundle["output"] / relative_path
        identity = result["artifact_identities"][relative_path]
        assert identity == {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        }


def test_delivery_requires_visual_manifest(delivery_bundle):
    (delivery_bundle["output"] / "image" / "visual_review.json").unlink()

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "missing_visual_manifest" in _failure_reasons(result)


def test_delivery_fails_when_visual_identity_gate_fails(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["pdf_sha256"] = "0" * 64
    _write_json(manifest, payload)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert result["visual_manifest_report"]["gates"]["V00"]["status"] == "failed"


def test_delivery_fails_when_visual_completeness_gate_fails(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["checks"] = []
    _write_json(manifest, payload)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert result["visual_manifest_report"]["gates"]["V01"]["status"] == "failed"


def test_delivery_needs_review_when_visual_review_gate_needs_review(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "needs_review"
    payload["reviews"][0]["failure_ids"] = ["H-G28-001"]
    _write_json(manifest, payload)
    item = _valid_failure()
    item["id"] = "H-G28-001"
    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": [item]},
    )
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "needs_review"
    assert result["visual_manifest_report"]["gates"]["V02"]["status"] == "needs_review"


def test_delivery_rejects_numeric_visual_failure_id_missing_from_queue(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "needs_review"
    payload["reviews"][0]["failure_ids"] = ["H-G28-999"]
    _write_json(manifest, payload)
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "visual_failure_id_not_in_queue" in _failure_reasons(result)


def test_delivery_rejects_visual_failure_id_missing_from_active_queue(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "needs_review"
    payload["reviews"][0]["failure_ids"] = ["H-G28-COVER-REVIEW"]
    _write_json(manifest, payload)
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "visual_failure_id_not_in_queue" in _failure_reasons(result)


def test_delivery_accepts_visual_failure_id_present_in_active_queue(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "needs_review"
    payload["reviews"][0]["failure_ids"] = ["H-G28-COVER-REVIEW"]
    _write_json(manifest, payload)
    item = _valid_failure()
    item["id"] = "H-G28-COVER-REVIEW"
    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": [item]},
    )
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "needs_review"
    assert "visual_failure_id_not_in_queue" not in _failure_reasons(result)


def test_missing_pdf_fails_with_delivery_failure(delivery_bundle):
    (delivery_bundle["output"] / "thesis.pdf").unlink()

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    failure = next(
        item for item in result["failures"] if item["reason"] == "missing_delivery_artifact"
    )
    assert failure["id"].startswith("H-DEL")
    _assert_evidence(failure["evidence"])
    assert failure["evidence"]["paths"] == ["thesis.pdf"]
    assert "thesis.pdf" in json.dumps(failure["evidence"].get("details"))


def test_generated_failure_id_is_stable_across_unrelated_output_changes(delivery_bundle):
    (delivery_bundle["output"] / "thesis.pdf").unlink()
    first = _validate(delivery_bundle)
    first_failure = next(
        item for item in first["failures"] if item["reason"] == "missing_delivery_artifact"
    )

    (delivery_bundle["output"] / "unrelated.tmp").write_text(
        "unrelated evidence text changed", encoding="utf-8"
    )
    report = delivery_bundle["output"] / "report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "\nUnrelated report details changed.\n",
        encoding="utf-8",
    )
    second = _validate(delivery_bundle)
    second_failure = next(
        item for item in second["failures"] if item["reason"] == "missing_delivery_artifact"
    )

    assert first_failure["id"] == second_failure["id"]
    match = re.fullmatch(
        r"H-([A-Z][A-Z0-9]*)-([A-Z0-9]+(?:-[A-Z0-9]+)*)",
        first_failure["id"],
    )
    assert match is not None
    assert any(character.isalpha() for character in match.group(2))


def test_model_source_sha_must_match_candidate(delivery_bundle):
    model_path = delivery_bundle["output"] / "model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["source"]["source_sha256"] = "0" * 64
    _write_json(model_path, model)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "source_identity_mismatch" in _failure_reasons(result)


@pytest.mark.parametrize(
    "field",
    [
        "source_candidate_path",
        "source_sha256",
        "source_size",
        "artifact_manifest_sha256",
    ],
)
def test_report_artifact_identity_must_match_delivery_bundle(delivery_bundle, field):
    report = delivery_bundle["output"] / "report.md"
    replacement = {
        "source_candidate_path": str(
            (delivery_bundle["output"].parent / "wrong.docx").resolve()
        ),
        "source_sha256": "0" * 64,
        "source_size": "999999",
        "artifact_manifest_sha256": "f" * 64,
    }[field]
    lines = report.read_text(encoding="utf-8").splitlines()
    report.write_text(
        "\n".join(
            f"- {field}: {replacement}" if line.startswith(f"- {field}:") else line
            for line in lines
        )
        + "\n",
        encoding="utf-8",
    )

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "report_identity_mismatch" in _failure_reasons(result)


def test_generated_failure_id_ignores_changed_diagnostic_details(delivery_bundle):
    report = delivery_bundle["output"] / "report.md"
    original = report.read_text(encoding="utf-8")
    report.write_text(
        re.sub(
            r"(?m)^- source_sha256: .+$",
            f"- source_sha256: {'0' * 64}",
            original,
        ),
        encoding="utf-8",
    )
    first = _validate(delivery_bundle)
    first_failure = next(
        item for item in first["failures"] if item["reason"] == "report_identity_mismatch"
    )

    report.write_text(
        re.sub(
            r"(?m)^- source_sha256: .+$",
            f"- source_sha256: {'f' * 64}",
            original,
        ),
        encoding="utf-8",
    )
    second = _validate(delivery_bundle)
    second_failure = next(
        item for item in second["failures"] if item["reason"] == "report_identity_mismatch"
    )

    assert first_failure["evidence"] != second_failure["evidence"]
    assert first_failure["id"] == second_failure["id"]


@pytest.mark.parametrize("artifact", ["compile.log", "standalone.tex", "scratch/cache.bin"])
def test_output_root_rejects_process_artifacts_and_extra_directories(
    delivery_bundle, artifact
):
    path = delivery_bundle["output"] / artifact
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"process artifact")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_process_artifact" in _failure_reasons(result)


def test_generated_forbidden_artifact_ids_are_semantic_and_unique(delivery_bundle):
    for index in range(100):
        (delivery_bundle["output"] / f"process-{index:03d}.tmp").write_text(
            "temporary", encoding="utf-8"
        )

    result = _validate(delivery_bundle)

    failures = [
        item
        for item in result["failures"]
        if item["reason"] == "forbidden_process_artifact"
    ]
    assert len(failures) == 100
    ids = [item["id"] for item in failures]
    assert len(ids) == len(set(ids))
    for failure_id in ids:
        match = re.fullmatch(
            r"H-([A-Z][A-Z0-9]*)-([A-Z0-9]+(?:-[A-Z0-9]+)*)",
            failure_id,
        )
        assert match is not None
        assert any(character.isalpha() for character in match.group(2))


def test_generated_ids_do_not_collide_after_semantic_normalization(delivery_bundle):
    for name in ("a+b.tmp", "a b.tmp"):
        (delivery_bundle["output"] / name).write_text("temporary", encoding="utf-8")

    result = _validate(delivery_bundle)

    failures = [
        item
        for item in result["failures"]
        if item["reason"] == "forbidden_process_artifact"
    ]
    assert len(failures) == 2
    assert failures[0]["id"] != failures[1]["id"]
    assert all(
        re.fullmatch(
            r"H-[A-Z][A-Z0-9]*-[A-Z0-9]+(?:-[A-Z0-9]+)*",
            item["id"],
        )
        for item in failures
    )


def test_delivery_rejects_required_root_file_symlink(delivery_bundle):
    thesis_tex = delivery_bundle["output"] / "thesis.tex"
    outside = delivery_bundle["output"].parent / "outside.tex"
    outside.write_text("\\documentclass{book}\n", encoding="utf-8")
    thesis_tex.unlink()
    try:
        thesis_tex.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_symlink_artifact" in _failure_reasons(result)


def test_delivery_rejects_output_directory_symlink(delivery_bundle):
    output = delivery_bundle["output"]
    outside = output.parent / "outside-output"
    output.rename(outside)
    try:
        output.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        outside.rename(output)
        pytest.skip(f"symlink unavailable: {exc}")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_symlink_artifact" in _failure_reasons(result)


def test_delivery_rejects_output_directory_junction(delivery_bundle):
    if not hasattr(Path, "is_junction"):
        pytest.skip("Path.is_junction is unavailable")
    output = delivery_bundle["output"]
    outside = output.parent / "outside-junction-output"
    output.rename(outside)
    completed = subprocess.run(
        ["cmd", "/d", "/c", f'mklink /J "{output}" "{outside}"'],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        outside.rename(output)
        pytest.skip(f"junction unavailable: {completed.stderr or completed.stdout}")
    assert output.is_junction()

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_symlink_artifact" in _failure_reasons(result)


def test_delivery_rejects_image_directory_symlink(delivery_bundle):
    image_dir = delivery_bundle["output"] / "image"
    outside = delivery_bundle["output"].parent / "outside-image"
    image_dir.rename(outside)
    try:
        image_dir.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        outside.rename(image_dir)
        pytest.skip(f"symlink unavailable: {exc}")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_symlink_artifact" in _failure_reasons(result)


def test_delivery_rejects_image_file_symlink(delivery_bundle):
    screenshot = delivery_bundle["output"] / "image" / "cover.png"
    outside = delivery_bundle["output"].parent / "outside.png"
    outside.write_bytes(b"png")
    screenshot.unlink()
    try:
        screenshot.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_symlink_artifact" in _failure_reasons(result)


def test_output_image_allows_final_raster_and_vector_media(delivery_bundle):
    image_dir = delivery_bundle["output"] / "image"
    (image_dir / "page-1.png").write_bytes(b"png")
    (image_dir / "page-2.jpg").write_bytes(b"jpg")
    (image_dir / "figure.svg").write_text("<svg></svg>", encoding="utf-8")
    (image_dir / "figure.eps").write_text("%!PS-Adobe-3.0 EPSF-3.0\n", encoding="utf-8")
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "pass"
    assert "forbidden_process_artifact" not in _failure_reasons(result)


def test_output_image_rejects_json_other_than_visual_manifest(delivery_bundle):
    _write_json(delivery_bundle["output"] / "image" / "review.json", {"status": "pass"})

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_process_artifact" in _failure_reasons(result)


def test_output_image_rejects_unreferenced_pdf(delivery_bundle):
    (delivery_bundle["output"] / "image" / "figure.pdf").write_bytes(b"%PDF-1.4\n")

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_process_artifact" in _failure_reasons(result)


def test_output_image_rejects_pdf_referenced_only_in_tex_comment(delivery_bundle):
    (delivery_bundle["output"] / "image" / "process.pdf").write_bytes(b"%PDF-1.4\n")
    tex = delivery_bundle["output"] / "thesis.tex"
    tex.write_text(
        tex.read_text(encoding="utf-8")
        + "% \\includegraphics{image/process.pdf}\n",
        encoding="utf-8",
    )

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "forbidden_process_artifact" in _failure_reasons(result)


def test_output_image_allows_and_hashes_pdf_referenced_by_thesis_tex(delivery_bundle):
    figure = delivery_bundle["output"] / "image" / "figure.pdf"
    figure.write_bytes(b"%PDF-1.4\n")
    tex = delivery_bundle["output"] / "thesis.tex"
    tex.write_text(
        tex.read_text(encoding="utf-8") + "\\includegraphics{image/figure.pdf}\n",
        encoding="utf-8",
    )
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "pass"
    assert result["artifact_identities"]["image/figure.pdf"] == {
        "path": str(figure.resolve()),
        "sha256": _sha256(figure),
        "size": figure.stat().st_size,
    }


def test_failed_required_gate_cannot_be_overridden_by_complete_artifacts(delivery_bundle):
    board = json.loads(delivery_bundle["gate_board"].read_text(encoding="utf-8"))
    board["G23"] = {"status": "failed", "reason": "latex_compile_failed"}
    _write_json(delivery_bundle["gate_board"], board)

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert result["profile_result"]["status"] == "failed"
    assert result["profile_result"]["failed_gates"] == ["G23"]


def test_failure_queue_rejects_items_missing_required_fields(delivery_bundle):
    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": [{"id": "H-DEL-BROKEN"}]},
    )

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "invalid_failure_queue_item" in _failure_reasons(result)


def test_valid_needs_review_failure_queue_item_requires_review(delivery_bundle):
    item = _valid_failure()
    assert FAILURE_FIELDS == set(item)
    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": [item]},
    )
    _refresh_report(delivery_bundle)

    result = _validate(delivery_bundle)

    assert result["status"] == "needs_review"
    assert result["failures"] == [item]


@pytest.mark.parametrize(
    "field",
    [
        "gate",
        "status",
        "reason",
        "region",
        "evidence_text",
        "expected",
        "suggested_fix",
    ],
)
def test_failure_queue_requires_nonempty_string_fields(delivery_bundle, field):
    item = _valid_failure()
    item[field] = ""
    _write_json(delivery_bundle["output"] / "failure_queue.json", {"failures": [item]})

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "invalid_failure_queue_item" in _failure_reasons(result)


@pytest.mark.parametrize(
    "evidence",
    [
        {"page": 1, "bbox": [0, 0, 100, 100], "sha256": "0" * 64},
        {
            "paths": "image/cover.png",
            "page": 1,
            "bbox": [0, 0, 100, 100],
            "sha256": "0" * 64,
        },
        {
            "paths": ["image/cover.png"],
            "page": "1",
            "bbox": [0, 0, 100, 100],
            "sha256": "0" * 64,
        },
        {
            "paths": ["image/cover.png"],
            "page": 1,
            "bbox": [0, 0, 100],
            "sha256": "0" * 64,
        },
        {
            "paths": ["image/cover.png"],
            "page": 1,
            "bbox": [0, 0, 100, 100],
            "sha256": "not-a-sha",
        },
    ],
)
def test_failure_queue_requires_normalized_evidence(delivery_bundle, evidence):
    item = _valid_failure()
    item["evidence"] = evidence
    _write_json(delivery_bundle["output"] / "failure_queue.json", {"failures": [item]})

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "invalid_failure_queue_item" in _failure_reasons(result)


def test_failure_queue_requires_boolean_can_fix_now(delivery_bundle):
    item = _valid_failure()
    item["can_fix_now"] = "false"
    _write_json(delivery_bundle["output"] / "failure_queue.json", {"failures": [item]})

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "invalid_failure_queue_item" in _failure_reasons(result)


@pytest.mark.parametrize(
    "failure_id",
    [
        "H-G28-cover-review",
        "H-G28-COVER_REVIEW",
        "H-G28-",
        "H--COVER-REVIEW",
        "H-DEL-REVIEW-001",
        "H-G27-001",
        "G28-001",
    ],
)
def test_failure_queue_requires_stable_gate_sequence_id(delivery_bundle, failure_id):
    item = _valid_failure()
    item["id"] = failure_id
    _write_json(delivery_bundle["output"] / "failure_queue.json", {"failures": [item]})

    result = _validate(delivery_bundle)

    assert result["status"] == "failed"
    assert "invalid_failure_queue_item" in _failure_reasons(result)


def test_failure_queue_rejects_duplicate_ids(delivery_bundle):
    first = _valid_failure()
    second = {**_valid_failure(), "region": "spine"}
    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": [first, second]},
    )

    result = _validate(delivery_bundle)

    invalid = [
        item for item in result["failures"] if item["reason"] == "invalid_failure_queue_item"
    ]
    assert result["status"] == "failed"
    assert invalid


def test_validator_generated_failures_use_normalized_queue_schema(delivery_bundle):
    (delivery_bundle["output"] / "image" / "visual_review.json").unlink()

    result = _validate(delivery_bundle)

    assert result["failures"]
    for item in result["failures"]:
        _assert_normalized_failure(item)

    _write_json(
        delivery_bundle["output"] / "failure_queue.json",
        {"failures": result["failures"]},
    )
    _refresh_report(delivery_bundle)
    revalidated = _validate(delivery_bundle)

    assert "invalid_failure_queue_item" not in _failure_reasons(revalidated)


def test_complete_visual_manifest_passes_all_visual_gates(delivery_bundle):
    manifest = _write_visual_manifest(delivery_bundle["output"])

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "pass"
    assert result["gates"]["V00"]["status"] == "pass"
    assert result["gates"]["V01"]["status"] == "pass"
    assert result["gates"]["V02"]["status"] == "pass"


def test_visual_manifest_rejects_decodable_image_unrelated_to_pdf_page(
    delivery_bundle,
):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    screenshot = (
        delivery_bundle["output"]
        / "image"
        / payload["reviews"][0]["screenshot"]
    )
    _write_png(screenshot)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert "visual_screenshot_pdf_mismatch" in {
        item["reason"] for item in result["failures"]
    }


def test_visual_manifest_pdf_page_count_must_match_actual_pdf(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["pdf_page_count"] = 10
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V00"]["status"] == "failed"


def test_visual_manifest_reviews_must_cover_every_pdf_page(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][-1]["pages"] = [10]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_each_review_must_reference_exactly_one_page(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["pages"] = [1, 2]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_one_review_cannot_claim_all_pages(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["pages"] = list(range(1, 12))
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_rejects_screenshot_reused_across_pages(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][1]["screenshot"] = payload["reviews"][0]["screenshot"]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


@pytest.mark.parametrize(
    "bbox",
    [
        [-1, 0, 100, 100],
        [0, -1, 100, 100],
        [0, 0, 596, 100],
        [0, 0, 100, 843],
    ],
)
def test_visual_manifest_bbox_must_stay_within_pdf_page(delivery_bundle, bbox):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["bbox"] = bbox
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_rejects_page_outside_pdf_range(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][-1]["pages"] = [12]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_missing_required_region_fails_v01(delivery_bundle):
    manifest = _write_visual_manifest(
        delivery_bundle["output"], regions=REQUIRED_VISUAL_REGIONS[:-1]
    )

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


@pytest.mark.parametrize("identity_error", ["sha", "path"])
def test_visual_manifest_bad_pdf_identity_or_screenshot_path_fails_v00(
    delivery_bundle, identity_error
):
    manifest = _write_visual_manifest(delivery_bundle["output"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if identity_error == "sha":
        payload["pdf_sha256"] = "0" * 64
    else:
        outside = delivery_bundle["output"].parent / "outside.png"
        outside.write_bytes(b"png")
        payload["reviews"][0]["screenshot"] = "../outside.png"
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V00"]["status"] == "failed"


def test_visual_manifest_review_status_propagates_to_v02(delivery_bundle):
    manifest = _write_visual_manifest(
        delivery_bundle["output"], review_status="needs_review"
    )

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "needs_review"
    assert result["gates"]["V00"]["status"] == "pass"
    assert result["gates"]["V01"]["status"] == "pass"
    assert result["gates"]["V02"]["status"] == "needs_review"


@pytest.mark.parametrize("screenshot", ["visual_review.json", "review.pdf"])
def test_visual_manifest_screenshot_must_be_an_image(delivery_bundle, screenshot):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    if screenshot.endswith(".pdf"):
        (delivery_bundle["output"] / "image" / screenshot).write_bytes(b"%PDF-1.4\n")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["screenshot"] = screenshot
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V00"]["status"] == "failed"


@pytest.mark.parametrize("content", [b"", b"not-a-decodable-png"])
def test_visual_manifest_rejects_corrupt_screenshot_content(delivery_bundle, content):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    (delivery_bundle["output"] / "image" / "cover.png").write_bytes(content)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V00"]["status"] == "failed"
    assert "invalid_visual_screenshot_content" in _failure_reasons(result)


def test_visual_manifest_allows_same_region_on_different_pages(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    screenshot = delivery_bundle["output"] / "image" / "cover-page-2.png"
    _write_pdf_screenshot(
        delivery_bundle["output"] / "thesis.pdf",
        page_number=2,
        bbox=payload["reviews"][0]["bbox"],
        destination=screenshot,
    )
    extra = dict(payload["reviews"][0])
    extra["pages"] = [2]
    extra["screenshot"] = screenshot.name
    payload["reviews"].append(extra)
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "pass"
    assert result["gates"]["V01"]["status"] == "pass"


def test_visual_manifest_rejects_duplicate_region_page_pair(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    screenshot = delivery_bundle["output"] / "image" / "cover-duplicate.png"
    _write_png(screenshot)
    duplicate = dict(payload["reviews"][0])
    duplicate["screenshot"] = screenshot.name
    payload["reviews"].append(duplicate)
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_rejects_empty_checks(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["checks"] = []
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


@pytest.mark.parametrize("field", ["bbox", "failure_ids"])
def test_visual_manifest_requires_review_evidence_fields(delivery_bundle, field):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    del payload["reviews"][0][field]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_identical_review_schema_failures_at_different_indices_get_distinct_ids(
    delivery_bundle,
):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    malformed = dict(payload["reviews"][0])
    del malformed["bbox"]
    payload["reviews"].extend([dict(malformed), dict(malformed)])
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    schema_failures = [
        item
        for item in result["failures"]
        if item["reason"] == "invalid_visual_review_schema"
    ]
    assert len(schema_failures) >= 2
    assert schema_failures[-2]["id"] != schema_failures[-1]["id"]
    assert all(
        re.fullmatch(
            r"H-[A-Z][A-Z0-9]*-[A-Z0-9]+(?:-[A-Z0-9]+)*",
            item["id"],
        )
        for item in schema_failures
    )


@pytest.mark.parametrize("status", ["needs_review", "failed"])
def test_visual_manifest_nonpass_review_requires_failure_id(delivery_bundle, status):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = status
    payload["reviews"][0]["failure_ids"] = []
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_nonpass_review_requires_valid_failure_id(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "needs_review"
    payload["reviews"][0]["failure_ids"] = ["not-an-h-id"]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_pass_review_requires_empty_failure_ids(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["failure_ids"] = ["H-G28-001"]
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_visual_manifest_rejects_illegal_review_status(delivery_bundle):
    manifest = delivery_bundle["output"] / "image" / "visual_review.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["reviews"][0]["status"] = "waived"
    _write_json(manifest, payload)

    result = validate_visual_manifest(delivery_bundle["output"], manifest)

    assert result["status"] == "failed"
    assert result["gates"]["V01"]["status"] == "failed"


def test_cli_refuses_to_write_validation_report_inside_delivery_output(delivery_bundle):
    report_path = delivery_bundle["output"] / "validation.json"

    with pytest.raises(SystemExit) as exc_info:
        delivery_cli.main(
            [
                "--output",
                str(delivery_bundle["output"]),
                "--profile",
                "latex_pdf",
                "--gate-board",
                str(delivery_bundle["gate_board"]),
                "--candidate",
                str(delivery_bundle["candidate"]),
                "--out",
                str(report_path),
            ]
        )

    assert exc_info.value.code == 2
    assert not report_path.exists()
