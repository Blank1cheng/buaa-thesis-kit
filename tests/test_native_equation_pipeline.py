from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

from buaa_thesis_kit.equations.mathtype_sdk import (
    clean_mathtype_translation,
    extract_mtef_payload,
)
from buaa_thesis_kit.equations.omml_to_latex import OmmlConversionError, omml_to_latex
from buaa_thesis_kit.equations.native_pipeline import run_equation_items
from buaa_thesis_kit.equations.recognizer import CommandImageRecognizer, parse_recognizer_argv
from buaa_thesis_kit.equations.verify import compare_formula_images, validate_latex_candidate
from buaa_thesis_kit.equations.mathtype_sdk import MathTypeConversion
from buaa_thesis_kit.rapid_latex_adapter import recognize_formula


def test_extract_mtef_payload_skips_equation_native_header() -> None:
    mtef = bytes([5, 1, 0, 7, 4, 0])
    native_header = (28).to_bytes(4, "little") + b"x" * 24

    assert extract_mtef_payload(native_header + mtef) == mtef
    assert extract_mtef_payload(mtef) == mtef


def test_extract_mtef_payload_rejects_invalid_native_stream() -> None:
    with pytest.raises(ValueError, match="MTEF"):
        extract_mtef_payload(b"not-an-equation")


def test_clean_mathtype_translation_removes_audit_comments_and_delimiters() -> None:
    translated = (
        "% MathType!MTEF!2!1!+-\r\n"
        "% encoded audit payload\r\n"
        r"\[OTF(\xi)=MTF(\xi){\text{ = }}1\]"
    )

    assert clean_mathtype_translation(translated) == r"OTF(\xi)=MTF(\xi)=1"


def test_omml_fraction_subscript_and_radical_convert_to_latex() -> None:
    omml = """
    <m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
      <m:oMath>
        <m:f>
          <m:num><m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sub><m:r><m:t>k</m:t></m:r></m:sub></m:sSub></m:num>
          <m:den><m:rad><m:e><m:r><m:t>n</m:t></m:r></m:e></m:rad></m:den>
        </m:f>
      </m:oMath>
    </m:oMathPara>
    """

    assert omml_to_latex(omml) == r"\frac{x_{k}}{\sqrt{n}}"


def test_omml_nary_and_matrix_convert_to_latex() -> None:
    omml = """
    <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
      <m:nary>
        <m:naryPr><m:chr m:val="∑"/></m:naryPr>
        <m:sub><m:r><m:t>i=1</m:t></m:r></m:sub>
        <m:sup><m:r><m:t>n</m:t></m:r></m:sup>
        <m:e>
          <m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e>
            <m:m>
              <m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr>
              <m:mr><m:e><m:r><m:t>c</m:t></m:r></m:e><m:e><m:r><m:t>d</m:t></m:r></m:e></m:mr>
            </m:m>
          </m:e></m:d>
        </m:e>
      </m:nary>
    </m:oMath>
    """

    assert omml_to_latex(omml) == r"\sum_{i=1}^{n}\begin{bmatrix}a & b \\ c & d\end{bmatrix}"


def test_omml_unknown_structural_node_is_not_silently_flattened() -> None:
    omml = """
    <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
      <m:unknown><m:r><m:t>x</m:t></m:r></m:unknown>
    </m:oMath>
    """

    with pytest.raises(OmmlConversionError, match="unknown"):
        omml_to_latex(omml)


def test_latex_candidate_validation_rejects_document_commands_and_unbalanced_groups() -> None:
    assert validate_latex_candidate(r"E=mc^2") == []
    assert "forbidden_command:input" in validate_latex_candidate(r"\input{secret}")
    assert "unbalanced_braces" in validate_latex_candidate(r"\frac{x}{y")


def test_visual_comparison_reads_unicode_windows_paths(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    directory = tmp_path / "公式证据"
    directory.mkdir()
    image = np.full((80, 240), 255, dtype=np.uint8)
    cv2.putText(image, "x=1", (25, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    source = directory / "源公式.png"
    rendered = directory / "渲染公式.png"
    source.write_bytes(encoded.tobytes())
    rendered.write_bytes(encoded.tobytes())

    report = compare_formula_images(source, rendered)

    assert report["status"] == "pass"
    assert report["score"] >= report["threshold"]


def test_visual_comparison_accepts_font_variation_but_rejects_gross_layout_mismatch(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    def write_formula(path: Path, text: str, font: int, thickness: int) -> None:
        image = np.full((100, 360), 255, dtype=np.uint8)
        cv2.putText(image, text, (20, 70), font, 1.7, 0, thickness, cv2.LINE_AA)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        path.write_bytes(encoded.tobytes())

    source = tmp_path / "source.png"
    font_variant = tmp_path / "font-variant.png"
    wrong_layout = tmp_path / "wrong-layout.png"
    write_formula(source, "OTF(fsp)", cv2.FONT_HERSHEY_SIMPLEX, 3)
    write_formula(font_variant, "OTF(fsp)", cv2.FONT_HERSHEY_COMPLEX, 2)
    wrong = np.full((100, 360), 255, dtype=np.uint8)
    cv2.line(wrong, (30, 50), (330, 50), 0, 7)
    ok, encoded = cv2.imencode(".png", wrong)
    assert ok
    wrong_layout.write_bytes(encoded.tobytes())

    assert compare_formula_images(source, font_variant)["status"] == "pass"
    assert compare_formula_images(source, wrong_layout)["status"] == "needs_review"


def test_equation_item_pipeline_writes_auditable_converted_artifact(tmp_path: Path) -> None:
    native = tmp_path / "eq-1.mtef"
    native.write_bytes((28).to_bytes(4, "little") + b"x" * 24 + bytes([5, 1, 0, 7, 4, 0]))
    preview = tmp_path / "eq-1.png"
    preview.write_bytes(b"preview")

    class FakeConverter:
        def convert(self, _payload: bytes) -> MathTypeConversion:
            return MathTypeConversion(status="converted", latex=r"E=mc^2", return_code=0)

    def fake_compile(latex: str, out_dir: Path) -> dict:
        assert latex == r"E=mc^2"
        (out_dir / "standalone.pdf").write_bytes(b"pdf")
        (out_dir / "rendered.png").write_bytes(b"rendered")
        return {
            "status": "success",
            "pdf": str(out_dir / "standalone.pdf"),
            "rendered_png": str(out_dir / "rendered.png"),
        }

    def fake_compare(_source: Path, _rendered: Path) -> dict:
        return {"status": "pass", "score": 0.93, "threshold": 0.72}

    result = run_equation_items(
        [
            {
                "id": "eq-1",
                "kind": "embedded-object",
                "native_path": str(native),
                "preview_path": str(preview),
                "native_format": "mathtype_mtef",
                "source": {"file": "source.docx", "paragraph_index": 12},
            }
        ],
        tmp_path / "out",
        mathtype_converter=FakeConverter(),
        compiler=fake_compile,
        comparator=fake_compare,
    )

    item = result["equations"][0]
    assert result["status"] == "pass"
    assert item["status"] == "converted"
    assert item["latex"] == r"E=mc^2"
    assert (tmp_path / "out" / "equations" / "eq-1" / "candidate.tex").read_text(encoding="utf-8") == r"E=mc^2"
    assert item["artifacts"]["source.mtef"]["sha256"]
    assert result["failure_queue"] == []


def test_equation_item_pipeline_keeps_translator_warning_in_stable_review_queue(tmp_path: Path) -> None:
    native = tmp_path / "eq-2.mtef"
    native.write_bytes((28).to_bytes(4, "little") + b"x" * 24 + bytes([5, 1, 0, 7, 4, 0]))

    class WarningConverter:
        def convert(self, _payload: bytes) -> MathTypeConversion:
            return MathTypeConversion(
                status="candidate_needs_review",
                latex=r"x=y",
                return_code=-14,
                warning="translator error",
            )

    def fake_compile(_latex: str, out_dir: Path) -> dict:
        (out_dir / "standalone.pdf").write_bytes(b"pdf")
        return {"status": "success", "pdf": str(out_dir / "standalone.pdf"), "rendered_png": ""}

    result = run_equation_items(
        [{"id": "eq-2", "kind": "embedded-object", "native_path": str(native)}],
        tmp_path / "out",
        mathtype_converter=WarningConverter(),
        compiler=fake_compile,
    )

    assert result["status"] == "needs_review"
    assert result["equations"][0]["status"] == "candidate_needs_review"
    assert result["failure_queue"][0]["id"] == "H-EQ-003-eq-2"
    assert result["failure_queue"][0]["reason"] == "mathtype_translator_warning"


def test_equation_pipeline_prefers_omml_over_conflicting_latex(tmp_path: Path) -> None:
    omml = (
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:r><m:t>x</m:t></m:r><m:r><m:t>=</m:t></m:r><m:r><m:t>1</m:t></m:r>'
        "</m:oMath>"
    )

    def fake_compile(latex: str, out_dir: Path) -> dict:
        assert latex == "x=1"
        (out_dir / "standalone.pdf").write_bytes(b"pdf")
        return {"status": "success", "pdf": str(out_dir / "standalone.pdf"), "rendered_png": ""}

    result = run_equation_items(
        [{"id": "eq-omml", "kind": "omml", "omml": omml, "latex": "WRONG", "requires_review": False}],
        tmp_path / "out",
        compiler=fake_compile,
    )

    assert result["equations"][0]["status"] == "converted"
    assert result["equations"][0]["latex"] == "x=1"
    assert result["equations"][0]["conversion"]["method"] == "omml_parser"


def test_pdf_text_equation_requiring_review_is_not_auto_trusted(tmp_path: Path) -> None:
    result = run_equation_items(
        [
            {
                "id": "pdf-equation-1",
                "kind": "pdf-text-equation",
                "latex": "x=1",
                "requires_review": True,
            }
        ],
        tmp_path / "out",
    )

    assert result["equations"][0]["status"] == "unsupported"
    assert result["equations"][0]["latex"] == ""
    assert result["failure_queue"][0]["id"] == "H-EQ-001-pdf-equation-1"


def test_pdf_text_equation_cannot_bypass_review_with_generated_omml(tmp_path: Path) -> None:
    result = run_equation_items(
        [
            {
                "id": "pdf-equation-unsafe",
                "kind": "pdf-text-equation",
                "latex": "x=1",
                "omml": (
                    '<m:oMath xmlns:m="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/math"><m:r><m:t>x=1</m:t></m:r></m:oMath>'
                ),
                "requires_review": False,
            }
        ],
        tmp_path / "out",
    )

    assert result["equations"][0]["status"] == "unsupported"
    assert result["equations"][0]["conversion"]["method"] == "none"
    assert result["failure_queue"][0]["reason"] == "native_source_missing"


def test_command_image_recognizer_uses_argv_json_protocol_without_shell(tmp_path: Path) -> None:
    preview = tmp_path / "formula.png"
    preview.write_bytes(b"preview")
    helper = tmp_path / "recognizer.py"
    helper.write_text(
        "import json, pathlib, sys\n"
        "image = pathlib.Path(sys.argv[1])\n"
        "print(json.dumps({'latex': r'E=mc^2', 'confidence': 0.97, 'engine': 'fake-ocr', "
        "'engine_version': '1.2.3', 'inference_seconds': 0.25, 'seen': image.name}))\n",
        encoding="utf-8",
    )

    result = CommandImageRecognizer([sys.executable, str(helper), "{image}"], timeout_seconds=5).recognize(preview)

    assert result.status == "candidate_needs_review"
    assert result.latex == r"E=mc^2"
    assert result.confidence == pytest.approx(0.97)
    assert result.engine == "fake-ocr"
    assert result.metadata["engine_version"] == "1.2.3"
    assert result.metadata["inference_seconds"] == pytest.approx(0.25)
    assert result.metadata["seen"] == "formula.png"
    assert result.audit["shell"] is False
    assert result.audit["returncode"] == 0
    assert result.audit["resolved_argv"][-1] == str(preview.resolve())


def test_command_image_recognizer_rejects_non_json_output(tmp_path: Path) -> None:
    preview = tmp_path / "formula.png"
    preview.write_bytes(b"preview")
    helper = tmp_path / "recognizer.py"
    helper.write_text("print('not-json')\n", encoding="utf-8")

    result = CommandImageRecognizer([sys.executable, str(helper), "{image}"], timeout_seconds=5).recognize(preview)

    assert result.status == "failed"
    assert result.reason == "recognizer_invalid_json"
    assert result.latex == ""


def test_recognizer_command_requires_json_argv() -> None:
    assert parse_recognizer_argv('["recognizer.exe", "--input", "{image}"]') == [
        "recognizer.exe",
        "--input",
        "{image}",
    ]
    with pytest.raises(ValueError, match="JSON array"):
        parse_recognizer_argv("recognizer.exe --input {image}")


def test_rapid_latex_adapter_emits_auditable_json_without_dependency(tmp_path: Path) -> None:
    image = tmp_path / "formula.png"
    image.write_bytes(b"image")

    class FakeModel:
        def __call__(self, payload: bytes):
            print("model diagnostic")
            assert payload == b"image"
            return r"\frac{x}{y}", 0.125

    payload, logs = recognize_formula(
        image,
        model_factory=FakeModel,
        version_resolver=lambda _name: "0.0.9",
    )

    assert payload["latex"] == r"\frac{x}{y}"
    assert payload["engine"] == "rapid_latex_ocr"
    assert payload["engine_version"] == "0.0.9"
    assert payload["inference_seconds"] == pytest.approx(0.125)
    assert "model diagnostic" in logs


def test_image_recognition_candidate_never_auto_passes(tmp_path: Path) -> None:
    preview = tmp_path / "eq-image.png"
    preview.write_bytes(b"preview")

    class FakeRecognizer:
        def recognize(self, _preview: Path):
            from buaa_thesis_kit.equations.recognizer import RecognitionResult

            return RecognitionResult(
                status="candidate_needs_review",
                latex=r"x^2+y^2=1",
                confidence=0.99,
                engine="fake-ocr",
                audit={"shell": False},
            )

    def fake_compile(_latex: str, out_dir: Path) -> dict:
        (out_dir / "standalone.pdf").write_bytes(b"pdf")
        (out_dir / "rendered.png").write_bytes(b"rendered")
        return {
            "status": "success",
            "pdf": str(out_dir / "standalone.pdf"),
            "rendered_png": str(out_dir / "rendered.png"),
        }

    result = run_equation_items(
        [{"id": "eq-image", "kind": "image-equation", "preview_path": str(preview)}],
        tmp_path / "out",
        recognizer=FakeRecognizer(),
        compiler=fake_compile,
        comparator=lambda *_args: {"status": "pass", "score": 0.99, "threshold": 0.72},
    )

    assert result["status"] == "needs_review"
    assert result["equations"][0]["status"] == "candidate_needs_review"
    assert result["equations"][0]["conversion"]["method"] == "image_recognizer"
    assert result["failure_queue"][0]["id"] == "H-EQ-009-eq-image"
    assert result["failure_queue"][0]["reason"] == "image_recognition_review_required"


def test_equation_cli_json_loader_preserves_model_root_and_identity(tmp_path: Path) -> None:
    from buaa_thesis_kit.equations.runner import load_equation_input

    native = tmp_path / "debug" / "equations_native" / "eq-1.mtef"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"mtef")
    model_path = tmp_path / "model.json"
    model_path.write_text(
        json.dumps(
            {
                "equations_need_review": [
                    {"id": "eq-1", "kind": "embedded-object", "native_asset": "debug/equations_native/eq-1.mtef"}
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = load_equation_input(model_path, tmp_path / "out")

    assert loaded.source_type == "model_json"
    assert loaded.model_root == tmp_path
    assert loaded.equations[0]["native_asset"].endswith("eq-1.mtef")
    assert loaded.identity["source_candidate_path"] == str(model_path.resolve())
    assert loaded.identity["candidate_size"] == model_path.stat().st_size
    assert len(loaded.identity["candidate_sha256"]) == 64


@pytest.mark.parametrize(
    ("suffix", "extractor_name", "source_type"),
    [(".docx", "extract_thesis_model", "docx"), (".pdf", "extract_pdf_model", "pdf")],
)
def test_equation_input_loader_dispatches_document_extractors_and_persists_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    extractor_name: str,
    source_type: str,
) -> None:
    from buaa_thesis_kit.equations import runner

    source = tmp_path / f"source{suffix}"
    source.write_bytes(b"source")

    class FakeModel:
        status = "needs_review"
        extraction_warnings = ["review"]

        def to_dict(self):
            return {
                "equations": [{"id": "eq-1", "kind": "omml", "omml": "<m:oMath/>"}],
                "status": self.status,
                "extraction_warnings": self.extraction_warnings,
            }

    def fake_extract(path: Path, work_dir: Path):
        assert path == source.resolve()
        assert work_dir == (tmp_path / "out" / "extraction").resolve()
        return FakeModel()

    monkeypatch.setattr(runner, extractor_name, fake_extract)
    loaded = runner.load_equation_input(source, tmp_path / "out")

    assert loaded.source_type == source_type
    assert loaded.model_root == (tmp_path / "out" / "extraction").resolve()
    assert loaded.model_path.is_file()
    assert loaded.equations[0]["id"] == "eq-1"
    assert loaded.model_status == "needs_review"
    assert loaded.extraction_warnings == ["review"]


def test_equation_pipeline_does_not_pass_when_no_equations_are_located(tmp_path: Path) -> None:
    result = run_equation_items([], tmp_path / "out")

    assert result["status"] == "failed"
    assert result["equation_count"] == 0
    assert result["failure_queue"][0]["id"] == "H-EQ-011-document"
    assert result["failure_queue"][0]["reason"] == "no_equations_located"


def test_run_equation_pipeline_binds_report_to_input_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from buaa_thesis_kit.equations import runner

    model_path = tmp_path / "model.json"
    model_path.write_text(
        json.dumps({"equations": [{"id": "eq-1", "kind": "latex", "latex": "x=1"}]}),
        encoding="utf-8",
    )

    def fake_run(equations, out_dir, **kwargs):
        assert equations[0]["id"] == "eq-1"
        report = {"status": "pass", "equation_count": 1, "failure_queue": []}
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(runner, "run_equation_items", fake_run)

    report = runner.run_equation_pipeline(model_path, tmp_path / "out")

    assert report["artifact_identity"]["source_candidate_path"] == str(model_path.resolve())
    assert report["artifact_identity"]["candidate_sha256"]
    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert persisted["artifact_identity"] == report["artifact_identity"]
    assert json.loads((tmp_path / "out" / "input_identity.json").read_text(encoding="utf-8")) == report["artifact_identity"]
