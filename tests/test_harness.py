import json
from pathlib import Path

from docx import Document


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def _bad_output_docx(path: Path) -> None:
    _write_docx(
        path,
        [
            "单位代码 10006",
            "学号 17375303",
            "分类号 T P 2 7 3",
            "基于实拍图像的光电系统性能评估关键技术研",
            "究",
            "论文封面书脊",
            "四号黑体字",
            "本人声明",
            "摘    要",
            "Research on Key Technologies of Performance Evaluation of Electro-Optical System Based on Actual Scene Images",
            "Author: CUI Runhao",
            "目    录",
            "本人声明 ................................................................ 1",
            "Mao Xia, Ding Yukun. Template reference.",
            "I级叶/盘转子错频方案的对比分析 ................ 15",
            "1 绪论",
            "北京航空航天大学毕业设计(论文)",
            "第 48 页",
            "[Figure requires review]",
        ],
    )


def _expected_model(path: Path) -> None:
    payload = {
        "metadata": {
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _good_model(path: Path) -> None:
    payload = {
        "metadata": {
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
        },
        "front_matter": {
            "chinese_abstract": "本文研究光电系统性能评估方法。",
            "english_abstract": "Abstract. This thesis studies performance evaluation.",
            "title_en": "Research on Key Technologies of Performance Evaluation of Electro-Optical System Based on Actual Scene Images",
            "author_en": "CUI Runhao",
            "tutor_en": "TANG Diyin",
            "keywords_en": "performance evaluation",
        },
        "sections": [{"type": "chapter", "title": "1 绪论", "text": "本课题来源于国家自然科学基金。"}],
        "references": [],
        "status": "needs_review",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_role_quiz_classifies_required_taxonomy(tmp_path):
    from buaa_thesis_kit.harness.validators import run_role_quiz

    report = run_role_quiz(tmp_path / "role_quiz_report.json")

    assert report["status"] == "pass"
    by_text = {case["text"]: case for case in report["cases"]}
    assert by_text["单位代码"]["actual_role"] == "template_static_required"
    assert by_text["论文封面书脊"]["actual_role"] == "template_instruction"
    assert by_text["王小亮"]["actual_role"] == "template_sample_value"
    assert by_text["[Figure requires review]"]["actual_role"] == "debug_forbidden"


def test_harness_config_files_live_under_config_directory():
    config_dir = Path("buaa_thesis_kit/harness/config")

    assert (config_dir / "role_schema.yaml").is_file()
    assert (config_dir / "region_rules.yaml").is_file()
    assert (config_dir / "forbidden_tokens.yaml").is_file()
    assert (config_dir / "template_sample_tokens.yaml").is_file()


def test_validate_model_blocks_template_samples_and_region_contamination(tmp_path):
    from buaa_thesis_kit.harness.validators import validate_model_file

    model = tmp_path / "model.json"
    expected = tmp_path / "expected.json"
    _expected_model(expected)
    payload = {
        "metadata": {
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
        },
        "front_matter": {
            "chinese_abstract": "Research on Key Technologies Author: Tutor: Abstract Key Words",
            "english_abstract": "Electro-desalting is the most efficient method.",
        },
        "sections": [{"type": "chapter", "title": "论文封面书脊", "text": "王小亮 MERGEFORMAT"}],
    }
    model.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = validate_model_file(model, expected, sample_mode="truncated")

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert "forbidden_text_in_model" in reason_ids
    assert "abstract_cn_contains_english" in reason_ids
    assert "abstract_en_contains_template_sample" in reason_ids


def test_validate_output_text_fails_bad_docx_with_required_reasons(tmp_path):
    from buaa_thesis_kit.harness.validators import validate_output_text_file

    bad = tmp_path / "thesis6.docx"
    _bad_output_docx(bad)

    report = validate_output_text_file(bad)

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert "template_instructions_or_sample_leak" in reason_ids
    assert "cover_classification_split" in reason_ids
    assert "cn_abstract_contains_english_title" in reason_ids
    assert "toc_contains_declaration" in reason_ids
    assert "toc_contains_template_sample_reference" in reason_ids
    assert "body_contains_template_page_number_48" in reason_ids


def test_validate_render_fails_current_bad_output_shape(tmp_path):
    from buaa_thesis_kit.harness.validators import validate_render_file

    bad = tmp_path / "thesis6.docx"
    _bad_output_docx(bad)

    report = validate_render_file(candidate=bad, out_dir=tmp_path / "render_diff", sample_mode="truncated")

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert {
        "cover_classification_split",
        "title_line_break_bad",
        "cn_abstract_contains_english_title",
        "toc_contains_declaration",
        "toc_contains_template_sample_reference",
        "body_contains_template_page_number_48",
        "template_instructions_or_sample_leak",
    }.issubset(reason_ids)
    assert (tmp_path / "render_diff" / "report.json").exists()


def test_run_harness_stops_on_failed_output_text(tmp_path):
    import scripts.run_harness as harness_script

    bad = tmp_path / "thesis6.docx"
    model = tmp_path / "model.json"
    expected = tmp_path / "expected.json"
    _bad_output_docx(bad)
    _good_model(model)
    _expected_model(expected)

    report = harness_script.run_harness(
        source=bad,
        official_template=bad,
        candidate=bad,
        model_json=model,
        expected_model=expected,
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert report["status"] == "failed"
    assert report["failed_stage"] == "output_text"
    assert (tmp_path / "harness" / "status.json").exists()
    assert not (tmp_path / "harness" / "render_report.json").exists()
    status = json.loads((tmp_path / "harness" / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"


def test_run_harness_default_captures_render_smoke_failures(tmp_path, monkeypatch):
    import scripts.run_harness as harness_script

    candidate = tmp_path / "thesis.docx"
    _write_docx(candidate, ["鍗曚綅浠ｇ爜 10006", "鍒嗙被鍙?TP273"])

    def fake_render_smoke(*, candidate, out_dir, sample_mode, existing_pdf=None):
        report = {
            "status": "failed",
            "candidate": str(candidate),
            "sample_mode": sample_mode,
            "failures": [
                {"id": "cover_classification_split", "region": "cover", "token": "T P 2 7 3"},
            ],
            "artifacts": {"page_images": []},
        }
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    monkeypatch.setattr(harness_script, "validate_render_smoke", fake_render_smoke)

    report = harness_script.run_harness(
        candidate=candidate,
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert report["status"] == "failed"
    assert report["failed_stage"] == "render_smoke"
    assert (tmp_path / "harness" / "render_smoke" / "report.json").is_file()
    queue = json.loads((tmp_path / "harness" / "failure_queue.json").read_text(encoding="utf-8"))
    assert queue["failures"][0]["reason"] == "cover_classification_split"
