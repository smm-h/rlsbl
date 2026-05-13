"""Tests for rlsbl.lint -- AST-based library boundary linting."""

from rlsbl.lint import LintResult, lint_library


class TestForbiddenImport:
    """Detect forbidden module imports."""

    def test_import_argparse(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text("import argparse\n")
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        r = results[0]
        assert r.rule == "forbidden-import"
        assert r.severity == "error"
        assert "argparse" in r.message

    def test_from_flask_import(self, tmp_path):
        src = tmp_path / "app.py"
        src.write_text("from flask import Flask\n")
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        r = results[0]
        assert r.rule == "forbidden-import"
        assert r.severity == "error"
        assert "flask" in r.message

    def test_import_os_allowed(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text("import os\n")
        results = lint_library(str(tmp_path))
        assert results == []

    def test_import_json_allowed(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text("import json\n")
        results = lint_library(str(tmp_path))
        assert results == []


class TestStdoutDetection:
    """Detect print(), sys.stdout/stderr.write(), and logging calls."""

    def test_print_call(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text('print("hello")\n')
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        r = results[0]
        assert r.rule == "stdout"
        assert r.severity == "error"
        assert "print()" in r.message

    def test_sys_stdout_write(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text('import sys\nsys.stdout.write("x")\n')
        results = lint_library(str(tmp_path))
        # One forbidden-import? No -- sys is not forbidden. One stdout violation.
        assert len(results) == 1
        r = results[0]
        assert r.rule == "stdout"
        assert r.severity == "error"
        assert "sys.stdout" in r.message

    def test_logging_info(self, tmp_path):
        src = tmp_path / "lib.py"
        src.write_text('import logging\nlogging.info("x")\n')
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        r = results[0]
        assert r.rule == "stdout"
        assert r.severity == "warning"
        assert "logging" in r.message


class TestEntryPoint:
    """Detect CLI entry point declarations in pyproject.toml."""

    def test_scripts_section(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "example"\n\n'
            '[project.scripts]\nmycli = "example:main"\n'
        )
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        r = results[0]
        assert r.rule == "entry-point"
        assert r.severity == "error"
        assert "mycli" in r.message
        assert r.line == 0

    def test_no_scripts(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "example"\n')
        results = lint_library(str(tmp_path))
        assert results == []


class TestTestFileExclusion:
    """Test files should be excluded from linting."""

    def test_tests_dir_excluded(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text('print("in test")\n')
        results = lint_library(str(tmp_path))
        assert results == []

    def test_src_file_not_excluded(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text('print("in src")\n')
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        assert results[0].rule == "stdout"


class TestIgnoreList:
    """The .rlsbl/lint.toml ignore list suppresses specific violations."""

    def test_ignore_argparse(self, tmp_path):
        # Set up ignore list
        rlsbl_dir = tmp_path / ".rlsbl"
        rlsbl_dir.mkdir()
        (rlsbl_dir / "lint.toml").write_text('ignore = ["argparse"]\n')
        # Source with argparse import
        (tmp_path / "lib.py").write_text("import argparse\n")
        results = lint_library(str(tmp_path))
        assert results == []

    def test_no_ignore_argparse(self, tmp_path):
        (tmp_path / "lib.py").write_text("import argparse\n")
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        assert "argparse" in results[0].message


class TestDirectoryExclusion:
    """Files in excluded directories (e.g., .venv) should not be linted."""

    def test_venv_excluded(self, tmp_path):
        venv_dir = tmp_path / ".venv" / "somepkg"
        venv_dir.mkdir(parents=True)
        (venv_dir / "bad.py").write_text("import flask\n")
        results = lint_library(str(tmp_path))
        assert results == [], f"Expected no findings from .venv, got: {results}"

    def test_node_modules_excluded(self, tmp_path):
        nm_dir = tmp_path / "node_modules" / "somepkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "bad.py").write_text("import flask\n")
        results = lint_library(str(tmp_path))
        assert results == []

    def test_egg_info_excluded(self, tmp_path):
        egg_dir = tmp_path / "mypkg.egg-info"
        egg_dir.mkdir()
        (egg_dir / "bad.py").write_text("import flask\n")
        results = lint_library(str(tmp_path))
        assert results == []

    def test_source_still_linted(self, tmp_path):
        """Non-excluded directories are still linted normally."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "lib.py").write_text("import flask\n")
        results = lint_library(str(tmp_path))
        assert len(results) == 1
        assert results[0].rule == "forbidden-import"


class TestCleanLibrary:
    """A project with no violations returns an empty list."""

    def test_clean(self, tmp_path):
        (tmp_path / "lib.py").write_text("import os\nimport json\n\ndef add(a, b):\n    return a + b\n")
        results = lint_library(str(tmp_path))
        assert results == []
