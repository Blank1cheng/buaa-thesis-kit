from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.frontmatter_render.validate_render import validate_render_frontmatter
from buaa_thesis_kit.frontmatter_render.layout_spec import RenderValidationConfig, normalize_frontmatter_pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render and validate BUAA thesis front matter.")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("output/render_diff"))
    parser.add_argument(
        "--pages",
        default="cover,spine,taskbook,declaration,abstract_cn,abstract_en,toc",
        help="Comma-separated front matter pages to validate.",
    )
    parser.add_argument(
        "--sample-mode",
        choices=("full", "truncated"),
        default="full",
        help="Use truncated for debug samples so body completeness is not a validation failure.",
    )
    args = parser.parse_args(argv)
    config = RenderValidationConfig(sample_mode=args.sample_mode)
    pages = normalize_frontmatter_pages(args.pages.split(","))
    result = validate_render_frontmatter(args.reference, args.candidate, args.out, config=config, pages=pages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"pass", "needs_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
