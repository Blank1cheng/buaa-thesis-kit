from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.extract.chunking import chunk_document, parse_ranges  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split a DOCX/PDF into named extraction chunks.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--ranges", default="")
    parser.add_argument("--out", required=True, type=Path)
    namespace = parser.parse_args(args)

    report = chunk_document(namespace.input, parse_ranges(namespace.ranges), namespace.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
