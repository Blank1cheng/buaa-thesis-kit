import json
from pathlib import Path

from jsonschema import validate

from buaa_thesis_kit.models import (
    AssetItem,
    ContentBlock,
    EquationItem,
    Metadata,
    OcrLedgerItem,
    SourceEvidence,
    ThesisModel,
)


def test_thesis_model_serializes_required_metadata():
    model = ThesisModel(
        metadata=Metadata(
            title_cn="基于数据驱动的系统研究",
            student_name="张三",
            student_id="20370001",
            college="自动化科学与电气工程学院",
            major="自动化",
            advisor="李四",
            date="2026年6月",
        )
    )

    payload = model.to_dict()

    assert payload["metadata"]["title_cn"] == "基于数据驱动的系统研究"
    assert payload["metadata"]["unit_code"] == "10006"
    assert payload["status"] == "draft"


def test_source_evidence_defaults_to_low_confidence_manual_review():
    evidence = SourceEvidence(file="input.docx", method="filename")

    assert evidence.confidence == 0.0
    assert evidence.requires_review is True


def test_thesis_model_serializes_nested_items_and_metadata_evidence():
    evidence = SourceEvidence(
        file="input.docx",
        method="paragraph",
        paragraph_index=3,
        confidence=0.8,
        requires_review=False,
    )
    model = ThesisModel(
        metadata=Metadata(
            title_cn="基于数据驱动的系统研究",
            student_name="张三",
            student_id="20370001",
            college="自动化科学与电气工程学院",
            major="自动化",
            advisor="李四",
            date="2026年6月",
            evidence={"title_cn": evidence},
        ),
        sections=[ContentBlock(id="sec-1", type="heading", title="绪论", level=1, source=evidence)],
        figures=[AssetItem(id="fig-1", type="image", path="figures/fig1.png", caption="系统框图", source=evidence)],
        tables=[ContentBlock(id="tbl-1", type="table", title="实验结果", text="A,B", source=evidence)],
        equations=[EquationItem(id="eq-1", kind="latex", latex="E=mc^2", number="(1)", source=evidence)],
        references=[ContentBlock(id="ref-1", type="reference", text="Reference text")],
        appendices=[ContentBlock(id="app-1", type="appendix", title="附录A")],
        ocr_ledger=[
            OcrLedgerItem(
                page=1,
                status="needs_ocr",
                image_path="image/pdf-page-001.png",
                confidence=0.0,
                requires_review=True,
            )
        ],
    )

    payload = model.to_dict()

    assert payload["metadata"]["evidence"]["title_cn"]["paragraph_index"] == 3
    assert payload["sections"][0]["source"]["method"] == "paragraph"
    assert payload["figures"][0]["caption"] == "系统框图"
    assert payload["tables"][0]["source"]["confidence"] == 0.8
    assert payload["equations"][0]["source"]["requires_review"] is False
    assert payload["references"][0]["source"] is None
    assert payload["appendices"][0]["title"] == "附录A"
    assert payload["ocr_ledger"][0]["page"] == 1
    assert payload["ocr_ledger"][0]["status"] == "needs_ocr"


def test_mutating_serialized_payload_does_not_mutate_model():
    model = ThesisModel(
        front_matter={"keywords": ["数据驱动", "系统"]},
        extraction_warnings=["missing abstract"],
    )

    payload = model.to_dict()
    payload["front_matter"]["keywords"].append("mutated")
    payload["extraction_warnings"].append("mutated")

    assert model.front_matter == {"keywords": ["数据驱动", "系统"]}
    assert model.extraction_warnings == ["missing abstract"]


def test_thesis_model_payload_validates_with_plain_jsonschema_validate():
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "thesis-model.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = ThesisModel(
        metadata=Metadata(
            title_cn="基于数据驱动的系统研究",
            student_name="张三",
            student_id="20370001",
            college="自动化科学与电气工程学院",
            major="自动化",
            advisor="李四",
            date="2026年6月",
        ),
        sections=[ContentBlock(id="sec-1", type="heading", title="绪论")],
        figures=[AssetItem(id="fig-1", type="image", path="figures/fig1.png")],
        tables=[ContentBlock(id="tbl-1", type="table", title="实验结果")],
        equations=[EquationItem(id="eq-1", kind="latex", latex="E=mc^2")],
        references=[ContentBlock(id="ref-1", type="reference", text="Reference text")],
    )

    validate(instance=model.to_dict(), schema=schema)
