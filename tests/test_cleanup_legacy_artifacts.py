from __future__ import annotations

from pathlib import Path

from scripts.cleanup_legacy_artifacts import apply_cleanup, plan_cleanup


def test_cleanup_dry_run_plans_legacy_outputs_but_keeps_latex(tmp_path: Path):
    output = tmp_path / "output"
    (output / "debug").mkdir(parents=True)
    (output / "debug" / "old.docx").write_text("old", encoding="utf-8")
    (output / "pipeline_gate").mkdir()
    (output / "pipeline_gate" / "thesis.docx").write_text("word", encoding="utf-8")
    (output / "latex_pipeline").mkdir()
    (output / "latex_pipeline" / "thesis.pdf").write_text("pdf", encoding="utf-8")
    (output / "latex_probe").mkdir()
    (output / "latex_probe" / "thesis.pdf").write_text("probe", encoding="utf-8")
    (output / "image").mkdir()
    (output / "goal_acceptance.md").write_text("accepted", encoding="utf-8")

    report = plan_cleanup(output_root=output, include_latex=False)

    planned = {Path(item["path"]).as_posix() for item in report["planned"]}
    assert any(path.endswith("output/debug") for path in planned)
    assert any(path.endswith("output/pipeline_gate") for path in planned)
    assert any(path.endswith("output/latex_probe") for path in planned)
    assert not any(path.endswith("output/latex_pipeline") for path in planned)
    assert not any(path.endswith("output/image") for path in planned)
    assert (output / "debug" / "old.docx").exists()
    assert report["planned_bytes"] > 0
    assert any(item["path"].endswith("thesis.pdf") and item["sha256"] for item in report["retained"])


def test_workspace_cleanup_plans_generated_tmp_and_external_template_alias(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    (tmp_path / "generated" / "probe").mkdir(parents=True)
    (tmp_path / "generated" / "probe" / "old.bin").write_bytes(b"old")
    (tmp_path / "tmp" / "latex_refs").mkdir(parents=True)
    (tmp_path / "tmp" / "latex_refs" / "old.cls").write_text("old", encoding="utf-8")
    alias = tmp_path / "templates" / "external" / "BUAAthesis"
    alias.mkdir(parents=True)
    (alias / "README").write_text("old alias", encoding="utf-8")

    report = plan_cleanup(output_root=output, workspace_root=tmp_path)

    reasons = {item["reason"] for item in report["planned"]}
    assert reasons == {"generated_process_artifacts", "temporary_process_artifacts", "external_template_alias"}


def test_apply_cleanup_removes_only_planned_paths_inside_workspace(tmp_path: Path):
    output = tmp_path / "output"
    (output / "latex_pipeline").mkdir(parents=True)
    (output / "latex_pipeline" / "thesis.pdf").write_bytes(b"final")
    (output / "old_probe").mkdir()
    (output / "old_probe" / "old.txt").write_text("old", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "old.bin").write_bytes(b"old")
    outside = tmp_path.parent / f"{tmp_path.name}_outside.txt"
    outside.write_text("keep", encoding="utf-8")

    report = plan_cleanup(output_root=output, workspace_root=tmp_path)
    report["planned"].append({"path": str(outside), "type": "file", "reason": "forged", "bytes": 4})
    applied = apply_cleanup(report)

    assert not (output / "old_probe").exists()
    assert not (tmp_path / "generated").exists()
    assert (output / "latex_pipeline" / "thesis.pdf").read_bytes() == b"final"
    assert outside.exists()
    assert str(outside) in applied["skipped_unsafe"]
    outside.unlink()
