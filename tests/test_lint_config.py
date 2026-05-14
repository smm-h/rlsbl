"""Tests for lint config migration from old lint.toml format and parser selection."""

import json

from rlsbl.lint import lint_library
from rlsbl.lint.config import (
    LanguageLintConfig,
    _load_old_lint_toml,
    apply_old_ignore_shim,
)


class TestOldConfigMigration:
    """Old-format .rlsbl/lint.toml with 'ignore' key triggers deprecation shim."""

    def test_deprecation_warning_printed(self, tmp_path, capsys):
        """Old-format lint.toml emits a deprecation warning to stderr."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["argparse"]\n')
        (tmp_path / "lib.py").write_text("import os\n")

        lint_library(str(tmp_path))

        captured = capsys.readouterr()
        assert "deprecated" in captured.err
        assert ".rlsbl/lint/<language>.toml" in captured.err

    def test_ignored_module_suppressed(self, tmp_path):
        """An ignored module name is removed from forbidden_imports."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["argparse"]\n')
        (tmp_path / "lib.py").write_text("import argparse\n")

        results = lint_library(str(tmp_path))
        # argparse should no longer be flagged
        forbidden = [r for r in results if r.rule == "forbidden-import"]
        assert forbidden == []

    def test_ignored_print_suppressed(self, tmp_path):
        """'print' in ignore list suppresses print() stdout detection."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["print"]\n')
        (tmp_path / "lib.py").write_text('print("hello")\n')

        results = lint_library(str(tmp_path))
        stdout = [r for r in results if r.rule == "stdout"]
        assert stdout == []

    def test_ignored_logging_suppressed(self, tmp_path):
        """'logging' in ignore list suppresses logging detection."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["logging"]\n')
        (tmp_path / "lib.py").write_text(
            "import logging\nlogging.info('x')\n"
        )

        results = lint_library(str(tmp_path))
        stdout = [r for r in results if r.rule == "stdout"]
        assert stdout == []

    def test_ignored_entry_point_suppressed(self, tmp_path):
        """Unknown ignore entries are treated as entry point names."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["mycli"]\n')
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "example"\n\n'
            '[project.scripts]\nmycli = "example:main"\n'
        )

        results = lint_library(str(tmp_path))
        entry_points = [r for r in results if r.rule == "entry-point"]
        assert entry_points == []

    def test_new_format_no_warning(self, tmp_path, capsys):
        """New-format lint.toml with only 'parser' key emits no warning."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('parser = "ast"\n')
        (tmp_path / "lib.py").write_text("import os\n")

        lint_library(str(tmp_path))

        captured = capsys.readouterr()
        assert "deprecated" not in captured.err

    def test_no_lint_toml_no_warning(self, tmp_path, capsys):
        """No lint.toml at all emits no warning."""
        (tmp_path / "lib.py").write_text("import os\n")

        lint_library(str(tmp_path))

        captured = capsys.readouterr()
        assert "deprecated" not in captured.err

    def test_mixed_old_format_all_types(self, tmp_path):
        """Old format with module, stdout, and entry point ignore entries."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text(
            'ignore = ["argparse", "print", "logging", "mycli"]\n'
        )
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "example"\n\n'
            '[project.scripts]\nmycli = "example:main"\n'
        )
        (tmp_path / "lib.py").write_text(
            "import argparse\n"
            "import logging\n"
            'print("hello")\n'
            'logging.info("x")\n'
        )

        results = lint_library(str(tmp_path))
        # All violations should be suppressed
        assert results == []


class TestApplyOldIgnoreShim:
    """Unit tests for apply_old_ignore_shim()."""

    def test_removes_forbidden_import(self):
        config = LanguageLintConfig(forbidden_imports=["argparse", "flask"])
        apply_old_ignore_shim(config, ["argparse"])
        assert "argparse" not in config.forbidden_imports
        assert "flask" in config.forbidden_imports

    def test_adds_to_stdout_ignore(self):
        config = LanguageLintConfig()
        apply_old_ignore_shim(config, ["print", "sys", "logging"])
        assert set(config.stdout_ignore) == {"print", "sys", "logging"}

    def test_adds_to_entry_point_ignore(self):
        config = LanguageLintConfig(forbidden_imports=["argparse"])
        apply_old_ignore_shim(config, ["mycli"])
        assert "mycli" in config.entry_point_ignore

    def test_no_duplicates(self):
        config = LanguageLintConfig(stdout_ignore=["print"])
        apply_old_ignore_shim(config, ["print"])
        assert config.stdout_ignore.count("print") == 1


class TestLoadOldLintToml:
    """Unit tests for _load_old_lint_toml()."""

    def test_returns_ignore_list(self, tmp_path):
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["argparse", "print"]\n')
        result = _load_old_lint_toml(str(tmp_path))
        assert result == ["argparse", "print"]

    def test_returns_none_for_new_format(self, tmp_path):
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('parser = "ast"\n')
        result = _load_old_lint_toml(str(tmp_path))
        assert result is None

    def test_returns_none_when_missing(self, tmp_path):
        result = _load_old_lint_toml(str(tmp_path))
        assert result is None


class TestParserSelection:
    """Verify parser = 'regex' selects the regex backend."""

    def test_regex_parser_detects_in_comments(self, tmp_path):
        """Regex backend matches patterns even in comments (AST would not)."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('parser = "regex"\n')
        # A line starting with 'import argparse' inside a docstring comment
        # is detected by regex but not by AST
        (tmp_path / "lib.py").write_text(
            '"""\nimport argparse\n"""\n'
        )
        results = lint_library(str(tmp_path))
        # Regex backend sees the line-level pattern
        forbidden = [r for r in results if r.rule == "forbidden-import"]
        assert len(forbidden) == 1

    def test_ast_parser_ignores_in_comments(self, tmp_path):
        """AST backend does NOT match patterns inside string literals."""
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('parser = "ast"\n')
        (tmp_path / "lib.py").write_text(
            '"""\nimport argparse\n"""\n'
        )
        results = lint_library(str(tmp_path))
        forbidden = [r for r in results if r.rule == "forbidden-import"]
        assert len(forbidden) == 0


class TestMultiLanguageProject:
    """Projects with both pyproject.toml and package.json run both linters."""

    def test_python_and_npm_violations(self, tmp_path):
        """Both Python and npm violations are reported in combined results."""
        # Python project marker + violation
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "example"\n'
        )
        (tmp_path / "lib.py").write_text("import argparse\n")

        # npm project marker + violation
        pkg = {"name": "example", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "index.js").write_text(
            "const express = require('express');\n"
        )

        results = lint_library(str(tmp_path))

        # Should have violations from both languages
        python_results = [
            r for r in results
            if r.file.endswith(".py") or r.file.endswith("pyproject.toml")
        ]
        npm_results = [
            r for r in results
            if r.file.endswith(".js") or r.file.endswith("package.json")
        ]
        assert len(python_results) >= 1, f"Expected Python violations, got: {results}"
        assert len(npm_results) >= 1, f"Expected npm violations, got: {results}"

    def test_both_clean(self, tmp_path):
        """Clean multi-language project returns empty results."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "example"\n'
        )
        (tmp_path / "lib.py").write_text("import os\n")

        pkg = {"name": "example", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "index.js").write_text("const x = 1;\n")

        results = lint_library(str(tmp_path))
        assert results == []
