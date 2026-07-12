from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.latex.template_manager import inspect_buaa_template  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a BHOSC/BUAAthesis template checkout.")
    parser.add_argument("--buaa-template-path", type=Path, default=None)
    parser.add_argument("--degree-type", default="undergraduate")
    parser.add_argument("--out", type=Path, default=Path("output/latex_pipeline"))
    namespace = parser.parse_args(args)
    out_file = namespace.out / "template_inspection.json"
    inspection = inspect_buaa_template(
        namespace.buaa_template_path,
        degree_type=namespace.degree_type,
        output_path=out_file,
    )
    print(json.dumps(inspection, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
