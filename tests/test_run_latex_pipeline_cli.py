from __future__ import annotations

import io

from scripts.run_latex_pipeline import _print_json_report


def test_print_json_report_reconfigures_legacy_console_to_utf8() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="gbk")

    _print_json_report({"private_use_character": "\uf028"}, stream=stream)
    stream.flush()

    rendered = raw.getvalue().decode("utf-8")
    assert '"private_use_character": "\uf028"' in rendered
