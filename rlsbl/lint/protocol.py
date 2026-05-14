"""Abstract protocol for per-language linters."""

from typing import Protocol, runtime_checkable

from .config import LanguageLintConfig
from .result import LintResult


@runtime_checkable
class LanguageLinter(Protocol):
    language: str  # "python", "go", "npm"
    parser_type: str  # "ast" or "regex"

    def lint(self, project_path: str, config: LanguageLintConfig) -> list[LintResult]: ...
