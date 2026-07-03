from pathlib import Path

import base64
from docx import Document
from pypdf import PdfWriter

from buaa_thesis_kit.models import ContentBlock, Metadata, ThesisModel


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "buaa_undergraduate_thesis_template.docx"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _write_minimal_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Title: Repair First Thesis")
    document.add_paragraph("Student Name: Zhang San")
    document.add_paragraph("Student ID: 20370001")
    document.add_paragraph("1 Introduction")
    document.add_paragraph("Body text that must be preserved.")
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def _write_valid_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_image_only_docx(path: Path) -> None:
    image = path.with_suffix(".png")
    image.write_bytes(TINY_PNG)
    document = Document()
    document.add_picture(str(image))
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def test_graph_runner_revises_after_visual_compare_failure_before_finalizing(tmp_path):
    from buaa_thesis_kit.graph import GraphRunner, GraphState, NodeResult

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    work = tmp_path / "output_work"
    _write_minimal_docx(source)

    def ingest(state: GraphState) -> NodeResult:
        state.notes.append("ingested")
        return NodeResult(next_node="visual_compare")

    def visual_compare(state: GraphState) -> NodeResult:
        if state.retry_count == 0:
            state.findings.append("visual_mismatch")
        return NodeResult(next_node="decide")

    def decide(state: GraphState) -> NodeResult:
        if state.findings and state.retry_count == 0:
            return NodeResult(next_node="revise_plan")
        return NodeResult(next_node="finalize_output")

    def revise_plan(state: GraphState) -> NodeResult:
        state.findings.clear()
        return NodeResult(next_node="visual_compare")

    def finalize_output(state: GraphState) -> NodeResult:
        state.outputs["report.md"] = "pass"
        return NodeResult(next_node=None)

    state = GraphState(source_path=source, output_root=output, work_dir=work, max_retries=2)
    result = GraphRunner(
        {
            "ingest": ingest,
            "visual_compare": visual_compare,
            "decide": decide,
            "revise_plan": revise_plan,
            "finalize_output": finalize_output,
        },
        start_node="ingest",
    ).run(state)

    assert result.status == "pass"
    assert result.retry_count == 1
    assert result.history == [
        "ingest",
        "visual_compare",
        "decide",
        "revise_plan",
        "visual_compare",
        "decide",
        "finalize_output",
    ]


def test_graph_runner_fails_when_revise_loop_exceeds_max_retries(tmp_path):
    from buaa_thesis_kit.graph import GraphRunner, GraphState, NodeResult

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    work = tmp_path / "output_work"
    _write_minimal_docx(source)

    def always_retry(_state: GraphState) -> NodeResult:
        return NodeResult(next_node="revise_plan")

    def revise(_state: GraphState) -> NodeResult:
        return NodeResult(next_node="decide")

    state = GraphState(source_path=source, output_root=output, work_dir=work, max_retries=1)
    result = GraphRunner(
        {"decide": always_retry, "revise_plan": revise},
        start_node="decide",
    ).run(state)

    assert result.status == "failed"
    assert result.retry_count == 1
    assert result.history == ["decide", "revise_plan", "decide"]
    assert any("maximum graph retry count exceeded" in item for item in result.blocking_items)


def test_graph_runner_fails_when_node_cycle_exceeds_max_steps(tmp_path):
    from buaa_thesis_kit.graph import GraphRunner, GraphState, NodeResult

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    work = tmp_path / "output_work"
    _write_minimal_docx(source)

    def loop(_state: GraphState) -> NodeResult:
        return NodeResult(next_node="loop")

    state = GraphState(source_path=source, output_root=output, work_dir=work, max_steps=3)
    result = GraphRunner({"loop": loop}, start_node="loop").run(state)

    assert result.status == "failed"
    assert result.history == ["loop", "loop", "loop"]
    assert any("maximum graph step count exceeded" in item for item in result.blocking_items)


def test_plan_minimal_fixes_promotes_missing_spine_to_repair_action(tmp_path):
    from buaa_thesis_kit.graph import GraphState
    from buaa_thesis_kit.graph_nodes import plan_minimal_fixes

    source = tmp_path / "source.docx"
    work = tmp_path / "output_work"
    output = tmp_path / "output"
    _write_minimal_docx(source)
    state = GraphState(source_path=source, output_root=output, work_dir=work)
    state.findings.append("missing_spine")
    state.model = ThesisModel(
        metadata=Metadata(
            title_cn="Repair First Thesis",
            student_name="Zhang San",
            college="Automation College",
            major="Automation",
            date="2026",
        )
    )

    result = plan_minimal_fixes(state)

    assert result.next_node == "apply_word_fixes"
    assert state.repair_actions == ["insert_spine"]
    assert not state.blocking_items


def test_apply_word_fixes_renders_docx_source_through_buaa_template(tmp_path):
    from buaa_thesis_kit.graph import GraphState
    from buaa_thesis_kit.graph_nodes import apply_word_fixes

    source = tmp_path / "source.docx"
    work = tmp_path / "output_work"
    output = tmp_path / "output"
    document = Document()
    document.add_paragraph("UNNORMALIZED SOURCE COVER ARTIFACT")
    document.add_paragraph("Body text that must be preserved.")
    document.save(source)
    state = GraphState(source_path=source, output_root=output, work_dir=work, template_path=TEMPLATE)
    state.extraction_source = source
    state.source_kind = "docx"
    state.repair_actions.append("insert_spine")
    state.model = ThesisModel(
        metadata=Metadata(
            title_cn="Repair First Thesis",
            student_name="Zhang San",
            college="Automation College",
            major="Automation",
            date="2026",
        )
    )
    state.model.sections.append(
        ContentBlock(
            id="sec-1",
            type="chapter",
            title="1 Introduction",
            text="Body text that must be preserved.",
            level=1,
        )
    )

    result = apply_word_fixes(state)

    assert result.next_node == "export_pdf"
    assert state.authoritative_docx is not None
    output_doc = Document(str(state.authoritative_docx))
    paragraphs = [paragraph.text for paragraph in output_doc.paragraphs]
    assert "Body text that must be preserved." in paragraphs
    assert "UNNORMALIZED SOURCE COVER ARTIFACT" not in paragraphs
    assert any("毕业设计(论文)" in text for text in paragraphs)
    assert any("书脊" in text for text in paragraphs)
    assert any("Repair First Thesis" in text for text in paragraphs)


def test_apply_word_fixes_does_not_treat_template_spine_instruction_as_existing_spine(tmp_path):
    from buaa_thesis_kit.graph import GraphState
    from buaa_thesis_kit.graph_nodes import apply_word_fixes

    source = tmp_path / "source.docx"
    work = tmp_path / "output_work"
    output = tmp_path / "output"
    document = Document()
    document.add_paragraph("论文封面书脊")
    document.add_paragraph("Body text that must be preserved.")
    document.save(source)

    state = GraphState(source_path=source, output_root=output, work_dir=work, template_path=TEMPLATE)
    state.extraction_source = source
    state.source_kind = "docx"
    state.repair_actions.append("insert_spine")
    state.model = ThesisModel(
        metadata=Metadata(
            title_cn="Repair First Thesis",
            student_name="Zhang San",
            college="Automation College",
            major="Automation",
            date="2026",
        )
    )

    apply_word_fixes(state)

    output_doc = Document(str(state.authoritative_docx))
    paragraphs = [paragraph.text for paragraph in output_doc.paragraphs]
    assert "论文封面书脊" not in paragraphs
    assert "书脊" in paragraphs
    assert state.applied_repairs == ["insert_spine"]


def test_visual_compare_blocks_pdf_word_without_editable_text(tmp_path):
    from buaa_thesis_kit.graph import GraphState
    from buaa_thesis_kit.graph_nodes import visual_compare

    output = tmp_path / "output"
    work = tmp_path / "work"
    source = tmp_path / "source.pdf"
    authoritative = tmp_path / "image-only.docx"
    _write_valid_pdf(source)
    _write_image_only_docx(authoritative)

    state = GraphState(source_path=source, output_root=output, work_dir=work)
    state.source_kind = "pdf"
    state.authoritative_docx = authoritative
    state.model = ThesisModel(
        metadata=Metadata(title_cn="PDF Pipeline Thesis", student_id="20370001")
    )

    result = visual_compare(state)

    assert result.next_node == "decide"
    assert any("editable_text_missing" in item for item in state.blocking_items)


def test_pipeline_report_records_graph_history_and_spine_repair(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    _write_minimal_docx(source)

    def stub_pdf_export(_source: Path, target: Path) -> tuple[bool, str]:
        _write_valid_pdf(target)
        return True, "stubbed Word PDF export"

    monkeypatch.setattr(pipeline, "export_pdf_from_docx", stub_pdf_export)

    report = pipeline.run_pipeline(source, output)

    assert report["outputs"]["word"] == "pass"
    assert report["outputs"]["pdf"] == "pass"
    assert report["outputs"]["tex"] in {"pass", "needs_review"}
    assert report["outputs"]["image"] == "pass"
    assert any("Graph nodes executed:" in note for note in report["notes"])
    assert any("missing_spine" in note for note in report["notes"])
    assert (output / "thesis.docx").is_file()
    assert (output / "thesis.pdf").is_file()
    assert (output / "thesis.tex").is_file()
    assert (output / "report.md").is_file()
    assert (output / "image").is_dir()
