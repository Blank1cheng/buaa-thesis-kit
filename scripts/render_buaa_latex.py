from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.latex.render_buaa import empty_demo_model, render_buaa_latex  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a BUAAthesis LaTeX project by filling template variables.")
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--empty-demo", action="store_true")
    parser.add_argument("--buaa-template-path", required=True, type=Path)
    parser.add_argument("--degree-type", default="undergraduate")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--no-compile", action="store_true")
    namespace = parser.parse_args(args)

    if namespace.model is not None:
        model = json.loads(namespace.model.read_text(encoding="utf-8"))
    elif namespace.empty_demo:
        model = empty_demo_model(namespace.degree_type)
    else:
        parser.error("Provide --model or --empty-demo.")

    report = render_buaa_latex(
        model,
        template_path=namespace.buaa_template_path,
        degree_type=namespace.degree_type,
        out_dir=namespace.out,
        compile_pdf=not namespace.no_compile,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
