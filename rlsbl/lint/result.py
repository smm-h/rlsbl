"""Lint result dataclass shared across all linter implementations, carrying severity, file location, rule identifier, and message text."""

from collections import namedtuple

LintResult = namedtuple("LintResult", ["file", "line", "rule", "severity", "message"])
