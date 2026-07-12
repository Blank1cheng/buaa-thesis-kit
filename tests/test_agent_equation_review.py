from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from buaa_thesis_kit.latex.equation_review import apply_agent_equation_reviews


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    source = tmp_path / "source.docx"
    source.write_bytes(b"source-artifact")
    native_root = tmp_path / "equation_native"
    equation_dir = native_root / "equations" / "eq-13"
    equation_dir.mkdir(parents=True)
    candidate = equation_dir / "candidate.tex"
    preview = equation_dir / "source_preview.png"
    rendered = equation_dir / "rendered.png"
    candidate.write_text(r"OTF(\xi,\eta)=MTF(\xi,\eta)e^{iPhTF(\xi,\eta)}", encoding="utf-8")
    preview.write_bytes(b"source-preview")
    rendered.write_bytes(b"rendered-preview")
    report = {
        "status": "needs_review",
        "equation_count": 1,
        "converted": 0,
        "needs_review": 1,
        "failed": 0,
        "unsupported": 0,
        "equations": [
            {
                "id": "eq-13",
                "status": "candidate_needs_review",
                "latex": candidate.read_text(encoding="utf-8"),
                "compile": {"status": "success"},
                "visual": {"status": "pass"},
            }
        ],
        "failure_queue": [
            {
                "id": "H-EQ-003-eq-13",
                "region": "equations.eq-13",
                "reason": "mathtype_translator_warning",
            }
        ],
    }
    ledger = {
        "source_candidate_path": str(source.resolve()),
        "source_sha256": _sha256(source),
        "reviews": [
            {
                "equation_id": "eq-13",
                "decision": "approved",
                "latex": candidate.read_text(encoding="utf-8"),
                "candidate_sha256": _sha256(candidate),
                "source_preview_sha256": _sha256(preview),
                "rendered_sha256": _sha256(rendered),
                "reviewer": "agent_visual",
                "evidence_text": "Compared every symbol against the source preview.",
            }
        ],
    }
    ledger_path = tmp_path / "equation_review.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return source, native_root, ledger_path, report


def test_agent_review_promotes_hash_bound_candidate(tmp_path: Path) -> None:
    source, native_root, ledger, report = _fixture(tmp_path)

    updated, audit = apply_agent_equation_reviews(report, ledger, source, native_root)

    assert updated["status"] == "pass"
    assert updated["converted"] == 1
    assert updated["needs_review"] == 0
    assert updated["failure_queue"] == []
    assert updated["equations"][0]["status"] == "converted"
    assert updated["equations"][0]["agent_review"]["reviewer"] == "agent_visual"
    assert audit["status"] == "pass"
    assert audit["approved_equation_ids"] == ["eq-13"]
    assert "ledger_path" not in json.dumps(updated)
    assert "ledger_path" not in audit
    assert audit["ledger_sha256"] == _sha256(ledger)


def test_agent_review_rejects_candidate_hash_mismatch(tmp_path: Path) -> None:
    source, native_root, ledger, report = _fixture(tmp_path)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["reviews"][0]["candidate_sha256"] = "0" * 64
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="candidate_sha256_mismatch"):
        apply_agent_equation_reviews(report, ledger, source, native_root)


def test_agent_review_rejects_source_identity_mismatch(tmp_path: Path) -> None:
    source, native_root, ledger, report = _fixture(tmp_path)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["source_sha256"] = "f" * 64
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="source_sha256_mismatch"):
        apply_agent_equation_reviews(report, ledger, source, native_root)


def test_agent_review_accepts_hash_bound_symbol_correction(tmp_path: Path) -> None:
    source, native_root, ledger, report = _fixture(tmp_path)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    corrected = r"OTF(\xi,\eta)=MTF(\xi,\eta),\quad e^{iPhTF(\xi,\eta)}"
    payload["reviews"][0]["latex"] = corrected
    payload["reviews"][0]["corrected_latex_sha256"] = hashlib.sha256(corrected.encode("utf-8")).hexdigest()
    payload["reviews"][0]["correction_reason"] = "Restore the comma visible in the source preview."
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    compiled: list[str] = []

    def compile_corrected(latex: str, out_dir: Path) -> dict:
        compiled.append(latex)
        (out_dir / "candidate.tex").write_text(latex, encoding="utf-8")
        rendered = out_dir / "rendered.png"
        rendered.write_bytes(b"corrected-render")
        return {"status": "success", "rendered_png": str(rendered)}

    def compare_corrected(source_preview: Path, rendered: Path) -> dict:
        assert source_preview.read_bytes() == b"source-preview"
        assert rendered.read_bytes() == b"corrected-render"
        return {"status": "pass", "score": 1.0}

    updated, audit = apply_agent_equation_reviews(
        report,
        ledger,
        source,
        native_root,
        compiler=compile_corrected,
        comparator=compare_corrected,
    )

    assert compiled == [corrected]
    assert updated["equations"][0]["latex"] == corrected
    assert updated["equations"][0]["agent_review"]["candidate_corrected"] is True
    assert updated["equations"][0]["compile"]["status"] == "success"
    assert updated["equations"][0]["visual"]["status"] == "pass"
    assert updated["equations"][0]["agent_review"]["corrected_candidate_sha256"] == _sha256(
        native_root / "equations" / "eq-13" / "candidate.tex"
    )
    assert updated["equations"][0]["agent_review"]["corrected_rendered_sha256"] == _sha256(
        native_root / "equations" / "eq-13" / "rendered.png"
    )
    assert updated["equations"][0]["artifacts"]["candidate.tex"]["sha256"] == _sha256(
        native_root / "equations" / "eq-13" / "candidate.tex"
    )
    artifact_hashes = json.loads(
        (native_root / "equations" / "eq-13" / "artifact_hashes.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact_hashes == updated["equations"][0]["artifacts"]
    assert updated["equations"][0]["agent_review"]["requires_post_render_visual_review"] is False
    assert audit["status"] == "pass"
