"""Lint result type shared across all linter implementations."""

from collections import namedtuple

LintResult = namedtuple("LintResult", ["file", "line", "rule", "severity", "message"])
