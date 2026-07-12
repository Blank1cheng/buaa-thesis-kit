from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.frontmatter_render.capture_reference import capture_reference_frontmatter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture BUAA front-matter render templates from a reference DOCX.")
    parser.add_argument("reference_docx", type=Path)
    parser.add_argument("--out", type=Path, default=Path("templates/front_matter_captured"))
    args = parser.parse_args(argv)
    result = capture_reference_frontmatter(args.reference_docx, args.out)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
