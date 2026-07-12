import json
import zipfile
from pathlib import Path

from lxml import etree
from pypdf import PdfWriter

from buaa_thesis_kit.models import Metadata, ThesisModel


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
TEMPLATE = Path("templates/official/buaa_undergraduate_template_instrumented.docx")


def _cover_model() -> ThesisModel:
    return ThesisModel(
        metadata=Metadata(
            title_cn="基于实拍图像的光电系统性能评估关键技术研究",
            college="自动化科学与电气工程学院",
            major="自动化",
            student_name="崔润昊",
            student_id="17375303",
            advisor="唐荻音",
            classification="TP273",
            unit_code="10006",
            date="2021 年 5 月",
        )
    )


def _document_root(path: Path):
    with zipfile.ZipFile(path) as package:
        return etree.fromstring(package.read("word/document.xml"))


def _paragraph_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))


def _paragraph_containing(path: Path, needle: str):
    for paragraph in _document_root(path).xpath(".//w:p", namespaces=NS):
        if needle in _paragraph_text(paragraph):
            return paragraph
    raise AssertionError(f"paragraph not found: {needle}")


def _direct_run_texts(paragraph) -> list[str]:
    return [
        "".join(node.text or "" for node in run.xpath(".//w:t", namespaces=NS))
        for run in paragraph.xpath("./w:r", namespaces=NS)
    ]


def _run_spacing(run) -> str | None:
    spacing = run.find("./w:rPr/w:spacing", namespaces=NS)
    return spacing.get(f"{{{W_NS}}}val") if spacing is not None else None


def _run_size(run) -> int | None:
    size = run.find("./w:rPr/w:sz", namespaces=NS)
    return int(size.get(f"{{{W_NS}}}val")) if size is not None else None


def _run_fonts(run) -> dict[str, str | None]:
    fonts = run.find("./w:rPr/w:rFonts", namespaces=NS)
    if fonts is None:
        return {"ascii": None, "hAnsi": None, "eastAsia": None}
    return {
        "ascii": fonts.get(f"{{{W_NS}}}ascii"),
        "hAnsi": fonts.get(f"{{{W_NS}}}hAnsi"),
        "eastAsia": fonts.get(f"{{{W_NS}}}eastAsia"),
    }


def _paragraph_spacing(paragraph) -> dict[str, str]:
    spacing = paragraph.find("./w:pPr/w:spacing", namespaces=NS)
    if spacing is None:
        return {}
    return {key.split("}")[-1]: value for key, value in spacing.attrib.items()}


def _runs_containing(root, value: str):
    return [
        run
        for run in root.xpath(".//w:r", namespaces=NS)
        if value in _paragraph_text(run)
    ]


def test_cover_classification_value_is_not_character_spaced_after_fill(tmp_path):
    from buaa_thesis_kit.assemble_in_place import assemble_in_place

    output = tmp_path / "thesis.docx"

    assemble_in_place(TEMPLATE, _cover_model(), output)

    paragraph = _paragraph_containing(output, "分类号")
    assert _paragraph_text(paragraph) == "分类号    TP273"
    run_texts = [text for text in _direct_run_texts(paragraph) if text]
    assert run_texts == ["分类号    ", "TP273"]
    value_run = [run for run in paragraph.xpath("./w:r", namespaces=NS) if _paragraph_text(run) == "TP273"][0]
    assert _run_spacing(value_run) == "0"


def test_render_cover_debug_writes_official_anchor_cover_sandbox(tmp_path, monkeypatch):
    from scripts import render_cover_debug

    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(_cover_model().to_dict(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cover"

    def fake_export(source: Path, target: Path) -> tuple[bool, str]:
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with target.open("wb") as handle:
            writer.write(handle)
        return True, "fake pdf export"

    monkeypatch.setattr(render_cover_debug, "export_pdf_from_docx", fake_export)

    report = render_cover_debug.render_cover_debug(
        model_path=model_path,
        template_path=TEMPLATE,
        out_dir=out,
    )

    expected_files = {
        "00_cover_from_official_template.docx",
        "01_cover_instrumented.docx",
        "02_cover_after_metadata_fill.docx",
        "03_cover_after_word_finalize.docx",
        "04_cover.pdf",
        "page_001_cover.png",
        "cover_report.json",
        "artifact_hashes.json",
    }
    assert expected_files.issubset({path.name for path in out.iterdir()})
    for name in expected_files:
        if not name.endswith(".docx"):
            continue
        text = "\n".join(_paragraph_text(p) for p in _document_root(out / name).xpath(".//w:p", namespaces=NS))
        assert "本科生毕业设计（论文）任务书" not in text
        assert "本人声明" not in text
        assert "摘    要" not in text
        assert "目       录" not in text

    saved_report = json.loads((out / "cover_report.json").read_text(encoding="utf-8"))
    assert saved_report == report
    assert saved_report["before_classification_text"] == "T P 2 7 3"
    assert saved_report["after_classification_text"] == "TP273"
    assert saved_report["classification_text"] == "TP273"
    assert saved_report["classification_split"] is False
    assert saved_report["cover_page_count"] == 1
    assert saved_report["cover_overflow"] is False
    assert saved_report["stray_texts"] == []
    assert saved_report["wordmark_present"] is True
    assert saved_report["thesis_type_text"] == "毕业设计(论文)"
    assert saved_report["title_lines"] == ["基于实拍图像的光电系统性能评估", "关键技术研究"]
    assert saved_report["bottom_fields"] == {
        "college": {"text": "自动化科学与电气工程学院", "page": 1},
        "major": {"text": "自动化", "page": 1},
        "student_name": {"text": "崔润昊", "page": 1},
        "advisor": {"text": "唐荻音", "page": 1},
        "date": {"text": "2021 年 5 月", "page": 1},
    }
    assert saved_report["date_in_advisor_field"] is False
    assert saved_report["thesis_type_and_title_merged"] is False
    assert saved_report["failures"] == []
    assert saved_report["source_template_path"] == str(TEMPLATE)
    assert saved_report["candidate_sha256"]
    hashes = json.loads((out / "artifact_hashes.json").read_text(encoding="utf-8"))
    for name in expected_files - {"artifact_hashes.json"}:
        assert name in hashes
        assert len(hashes[name]) == 64


def test_cover_instrumentation_compacts_bottom_fields_for_single_page(tmp_path, monkeypatch):
    from scripts import render_cover_debug

    model = _cover_model()
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model.to_dict(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cover"

    def fake_export(source: Path, target: Path) -> tuple[bool, str]:
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with target.open("wb") as handle:
            writer.write(handle)
        return True, "fake pdf export"

    monkeypatch.setattr(render_cover_debug, "export_pdf_from_docx", fake_export)

    render_cover_debug.render_cover_debug(
        model_path=model_path,
        template_path=TEMPLATE,
        out_dir=out,
    )

    root = _document_root(out / "03_cover_after_word_finalize.docx")
    body_children = list(root.find("w:body", namespaces=NS))
    date_index = next(
        index
        for index, child in enumerate(body_children)
        if child.tag == f"{{{W_NS}}}p" and model.metadata.date in _paragraph_text(child)
    )
    assert body_children[date_index - 1].tag == f"{{{W_NS}}}p"
    assert _paragraph_text(body_children[date_index - 1]).strip() == ""
    assert body_children[date_index - 2].tag == f"{{{W_NS}}}tbl"

    college_runs = [
        run
        for run in root.xpath(".//w:tbl//w:r", namespaces=NS)
        if _paragraph_text(run) == model.metadata.college
    ]
    assert len(college_runs) == 1
    assert _run_size(college_runs[0]) == 30
    assert _run_fonts(college_runs[0])["eastAsia"] == "黑体"

    classification_paragraph = _paragraph_containing(out / "03_cover_after_word_finalize.docx", model.metadata.classification)
    classification_text = _paragraph_text(classification_paragraph).strip()
    assert classification_text.startswith("分类号")
    assert not classification_text.startswith("1")


def test_cover_typography_matches_official_size_requirements(tmp_path, monkeypatch):
    from scripts import render_cover_debug

    model = _cover_model()
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model.to_dict(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "cover"

    def fake_export(source: Path, target: Path) -> tuple[bool, str]:
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with target.open("wb") as handle:
            writer.write(handle)
        return True, "fake pdf export"

    monkeypatch.setattr(render_cover_debug, "export_pdf_from_docx", fake_export)

    render_cover_debug.render_cover_debug(
        model_path=model_path,
        template_path=TEMPLATE,
        out_dir=out,
    )

    root = _document_root(out / "03_cover_after_word_finalize.docx")
    body_children = list(root.find("w:body", namespaces=NS))
    top_runs = [
        run
        for paragraph in body_children[:3]
        for run in paragraph.xpath("./w:r", namespaces=NS)
    ]

    for label in ("单位代码", "学", "号", "分类号"):
        label_runs = [run for run in top_runs if label in _paragraph_text(run)]
        assert label_runs, label
        assert all(_run_size(run) == 21 for run in label_runs)
        assert all(_run_fonts(run)["eastAsia"] == "黑体" for run in label_runs)

    for value in ("10006", "17375303", "TP273"):
        value_runs = [run for run in top_runs if value in _paragraph_text(run)]
        assert value_runs, value
        assert all(_run_size(run) == 24 for run in value_runs)
        assert all(_run_fonts(run)["ascii"] == "Times New Roman" for run in value_runs)
        assert all(_run_fonts(run)["hAnsi"] == "Times New Roman" for run in value_runs)

    for title_line in ("基于实拍图像的光电系统性能评估", "关键技术研究"):
        paragraph = _paragraph_containing(out / "03_cover_after_word_finalize.docx", title_line)
        assert _paragraph_spacing(paragraph) == {"line": "360", "lineRule": "auto"}
        title_runs = [run for run in paragraph.xpath("./w:r", namespaces=NS) if _paragraph_text(run)]
        assert title_runs
        assert all(_run_size(run) == 44 for run in title_runs)
        assert all(_run_fonts(run)["eastAsia"] == "黑体" for run in title_runs)


def test_render_smoke_reports_cover_specific_failures_for_flowed_cover():
    from scripts.validate_render_smoke import _page_rule_failures

    failures = _page_rule_failures(
        [
            "\n".join(
                [
                    "单 10006",
                    "学    号     17375303",
                    "分类号    TP273",
                    "毕业设计(论文)基于实拍图",
                    "像的光电系统性能评估关",
                    "键技术研究",
                    "学院名称",
                    "专业名称",
                ]
            ),
            "学生姓名\n指导教师2021\n年 5 月",
        ]
    )

    reason_ids = {item["id"] for item in failures}
    assert "cover_classification_split" not in reason_ids
    assert {
        "cover_metadata_anchor_misaligned",
        "cover_thesis_type_and_title_merged",
        "cover_title_layout_bad",
        "cover_bottom_fields_missing_values",
        "cover_date_merged_into_advisor",
    }.issubset(reason_ids)
