from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.latex_renderer import render_latex  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a parallel BUAA LaTeX/PDF spike from thesis model.json."
    )
    parser.add_argument("model", type=Path, help="Input thesis model.json.")
    parser.add_argument("--out", required=True, type=Path, help="Output directory.")
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=None,
        help="Directory containing main.tex.template.",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Generate thesis.tex and report.json without running XeLaTeX.",
    )
    parser.add_argument(
        "--degree",
        choices=("bachelor", "master"),
        default="bachelor",
        help="BUAA thesis profile. bachelor is the undergraduate path; master is graduate.",
    )
    parser.add_argument(
        "--backend",
        choices=("bhosc", "lightweight"),
        default="bhosc",
        help="Template backend. bhosc follows BHOSC/BUAAthesis project layout.",
    )
    namespace = parser.parse_args(args)

    report = render_latex(
        namespace.model,
        namespace.out,
        template_dir=namespace.template_dir,
        compile_pdf=not namespace.no_compile,
        degree=namespace.degree,
        backend=namespace.backend,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
