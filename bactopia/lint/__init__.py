"""Bactopia pipeline linter."""

from bactopia.lint.models import LintResult
from bactopia.lint.runner import run_lint

__all__ = ["LintResult", "run_lint"]
