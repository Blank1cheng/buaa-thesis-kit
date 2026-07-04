"""Executable harness for BUAA thesis requirement classification and validation."""

from .roles import classify_text
from .validators import (
    run_role_quiz,
    validate_model_file,
    validate_output_text_file,
    validate_render_file,
)

__all__ = [
    "classify_text",
    "run_role_quiz",
    "validate_model_file",
    "validate_output_text_file",
    "validate_render_file",
]
