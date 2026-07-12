from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.rapid_latex_adapter import recognize_formula  # noqa: E402


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RapidLaTeXOCR JSON adapter for one formula image.")
    parser.add_argument("image", type=Path)
    namespace = parser.parse_args(args)
    try:
        payload, logs = recognize_formula(namespace.image)
    except Exception as exc:
        print(f"rapid_latex_ocr_adapter: {exc}", file=sys.stderr)
        return 2
    if logs:
        print(logs, file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
