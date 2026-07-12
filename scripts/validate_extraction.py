from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.extract.harness import validate_extraction_model  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate extracted thesis model before LaTeX rendering.")
    parser.add_argument("model", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--sample-mode", default="full")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-missing-metadata", action="store_true")
    namespace = parser.parse_args(args)

    model = json.loads(namespace.model.read_text(encoding="utf-8"))
    result = validate_extraction_model(
        model,
        source_path=namespace.source,
        out_dir=namespace.out,
        sample_mode=namespace.sample_mode,
        allow_missing_metadata=namespace.allow_missing_metadata,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
