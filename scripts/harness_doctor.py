from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.progress import write_progress_artifacts


def run_doctor(
    *,
    out_dir: Path,
    candidate: Path | None = None,
    sample_mode: str | None = None,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _clear_generated_dirs(out)
    source_harness = _discover_source_harness(out)
    if source_harness != out:
        _clear_generated_progress(out)
        _copy_json_reports(source_harness, out)
        _copy_parent_reports(source_harness, out)
    resolved_candidate = _resolve_candidate(out, source_harness, candidate)
    render_dir = _prepare_render_smoke_dir(out, source_harness, resolved_candidate)
    resolved_sample_mode = sample_mode or _infer_sample_mode(out, source_harness, render_dir)
    return write_progress_artifacts(
        out,
        candidate_path=resolved_candidate,
        sample_mode=resolved_sample_mode,
        commands=["python scripts/harness_doctor.py --out " + str(out)],
        render_smoke_dir=render_dir,
    )


def _discover_source_harness(out: Path) -> Path:
    if out.name != "harness" and (any(out.glob("*_report.json")) or (out / "status.json").exists()):
        return out
    pipeline_harness = out.parent / "pipeline_gate" / "harness"
    if pipeline_harness.exists() and pipeline_harness.is_dir():
        out_status = out / "status.json"
        pipeline_status = pipeline_harness / "status.json"
        out_candidate = _status_candidate(out_status)
        if out_candidate is not None and not _is_relative_to(out_candidate, pipeline_harness.parent):
            return pipeline_harness
        if not out_status.exists() or (
            pipeline_status.exists()
            and pipeline_status.stat().st_mtime >= out_status.stat().st_mtime
        ):
            return pipeline_harness
    if any(out.glob("*_report.json")) or (out / "status.json").exists():
        return out
    candidates = [pipeline_harness, out.parent / "pipeline" / "harness", out.parent / "latest" / "harness"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return out


def _status_candidate(status_path: Path) -> Path | None:
    if not status_path.exists():
        return None
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = payload.get("candidate_path") or payload.get("candidate")
    return Path(str(value)) if value else None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _clear_generated_progress(target: Path) -> None:
    for path in list(target.glob("*.json")) + [target / "progress.md"]:
        if path.exists() and path.is_file():
            path.unlink()
    _clear_generated_dirs(target)


def _clear_generated_dirs(target: Path) -> None:
    for dirname in ("debug_render", "full_bad", "render_diff"):
        path = target / dirname
        if path.exists() and path.is_dir() and _is_relative_to(path, target):
            shutil.rmtree(path)


def _copy_json_reports(source: Path, target: Path) -> None:
    for path in source.glob("*.json"):
        if path.name in {"gate_board.json", "failure_queue.json", "evidence_packet.json"}:
            continue
        shutil.copy2(path, target / path.name)


def _copy_parent_reports(source: Path, target: Path) -> None:
    for name in ("template_inheritance_report.json",):
        source_report = source.parent / name
        if source_report.exists() and source_report.is_file():
            shutil.copy2(source_report, target / name)


def _prepare_render_smoke_dir(out: Path, source_harness: Path, candidate: Path | None = None) -> Path | None:
    local_render = out / "render_smoke"
    if source_harness == out and local_render.exists() and local_render.is_dir():
        return local_render
    if candidate is not None:
        candidate_render = candidate.parent / "render_smoke"
        if candidate_render.exists() and candidate_render.is_dir() and (candidate_render / "report.json").is_file():
            return candidate_render
    source_render = source_harness.parent / "render_smoke"
    target_render = out.parent / "render_smoke"
    if not source_render.exists() or not source_render.is_dir():
        return target_render if target_render.exists() and target_render.is_dir() else None
    if source_render.resolve(strict=False) == target_render.resolve(strict=False):
        return source_render
    target_render.mkdir(parents=True, exist_ok=True)
    for stale in target_render.iterdir():
        if stale.is_file():
            stale.unlink()
    for path in source_render.iterdir():
        if path.is_file():
            shutil.copy2(path, target_render / path.name)
    return target_render


def _resolve_candidate(out: Path, source_harness: Path, candidate: Path | None) -> Path | None:
    if candidate is not None and candidate.exists():
        return candidate
    for report_dir in (out, source_harness):
        for report_name in ("artifact_identity.json", "status.json", "output_text_report.json"):
            report_path = report_dir / report_name
            if not report_path.exists():
                continue
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for key in ("candidate_path", "candidate"):
                value = payload.get(key)
                if value and Path(str(value)).exists():
                    return Path(str(value))
    pipeline_candidate = out.parent / "pipeline_gate" / "thesis.docx"
    return pipeline_candidate if pipeline_candidate.exists() else None


def _infer_sample_mode(out: Path, source_harness: Path, render_dir: Path | None) -> str:
    report_dirs = [out, source_harness]
    for report_dir in report_dirs:
        for report_name in ("model_validation_report.json", "output_text_report.json", "output_text_post_finalize_report.json"):
            sample_mode = _sample_mode_from_json(report_dir / report_name)
            if sample_mode:
                return sample_mode
    if render_dir is not None:
        sample_mode = _sample_mode_from_json(render_dir / "report.json")
        if sample_mode:
            return sample_mode
    return "full"


def _sample_mode_from_json(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = str(payload.get("sample_mode", "")).strip().lower()
    return value if value in {"full", "truncated"} else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate harness reports into progress artifacts.")
    parser.add_argument("--out", type=Path, default=Path("output/harness"))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--sample-mode", choices=("full", "truncated"), default=None)
    args = parser.parse_args(argv)
    packet = run_doctor(out_dir=args.out, candidate=args.candidate, sample_mode=args.sample_mode)
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
