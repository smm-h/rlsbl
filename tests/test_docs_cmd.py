"""Tests for the docs CLI command (init, build, no-args help)."""

import os
import subprocess
import sys
import tempfile

import pytest


class TestDocsInit:
    """Tests for `rlsbl docs init`."""

    def test_creates_docs_toml(self):
        """docs init should create .rlsbl/docs.toml."""
        with tempfile.TemporaryDirectory() as d:
            # Create a pyproject.toml so project name is detected
            with open(os.path.join(d, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "test-project"\nversion = "1.0.0"\n')
            # Create a source directory
            os.makedirs(os.path.join(d, "src"))

            # Run the init command
            from rlsbl.commands.docs_cmd import _cmd_init
            orig_dir = os.getcwd()
            try:
                os.chdir(d)
                _cmd_init([], {})
            finally:
                os.chdir(orig_dir)

            config_path = os.path.join(d, ".rlsbl", "docs.toml")
            assert os.path.exists(config_path)

            # Verify content is valid TOML with expected structure
            import tomllib
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            assert "source" in config
            assert config["source"]["type"] == "python"
            assert "src/" in config["source"]["paths"]
            assert "output" in config
            assert "deploy" in config

    def test_refuses_if_already_exists(self):
        """docs init should fail if .rlsbl/docs.toml already exists."""
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write("[source]\n")

            from rlsbl.commands.docs_cmd import _cmd_init
            orig_dir = os.getcwd()
            try:
                os.chdir(d)
                with pytest.raises(SystemExit):
                    _cmd_init([], {})
            finally:
                os.chdir(orig_dir)

    def test_detects_package_dir(self):
        """docs init should detect package directory from pyproject.toml name."""
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "my-pkg"\nversion = "0.1.0"\n')
            # Create package dir matching the project name (dashes -> underscores)
            os.makedirs(os.path.join(d, "my_pkg"))
            with open(os.path.join(d, "my_pkg", "__init__.py"), "w") as f:
                f.write("")

            from rlsbl.commands.docs_cmd import _cmd_init
            orig_dir = os.getcwd()
            try:
                os.chdir(d)
                _cmd_init([], {})
            finally:
                os.chdir(orig_dir)

            import tomllib
            config_path = os.path.join(d, ".rlsbl", "docs.toml")
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            assert "my_pkg/" in config["source"]["paths"]


class TestDocsBuild:
    """Tests for `rlsbl docs build`."""

    def test_build_produces_html(self):
        """docs build should produce HTML output files."""
        with tempfile.TemporaryDirectory() as d:
            # Set up .rlsbl/docs.toml
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(
                    '[source]\ntype = "python"\npaths = ["src/"]\n\n'
                    '[output]\ndir = "docs/_build"\n\n'
                    '[deploy]\nprovider = "github-pages"\n'
                )

            # Set up a Python source file
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "example.py"), "w") as f:
                f.write('"""Example module."""\n\ndef hello():\n    """Say hello."""\n    pass\n')

            # Set up pyproject.toml for version detection
            with open(os.path.join(d, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "test-project"\nversion = "1.2.3"\n')

            from rlsbl.commands.docs_cmd import _cmd_build
            orig_dir = os.getcwd()
            try:
                os.chdir(d)
                _cmd_build([], {})
            finally:
                os.chdir(orig_dir)

            # Verify HTML output was created
            output_dir = os.path.join(d, "docs", "_build")
            assert os.path.isdir(output_dir)
            # Should have at least an index.html
            html_files = []
            for root, dirs, files in os.walk(output_dir):
                for fname in files:
                    if fname.endswith(".html"):
                        html_files.append(fname)
            assert len(html_files) > 0

    def test_build_fails_without_config(self):
        """docs build should fail if no docs.toml exists."""
        with tempfile.TemporaryDirectory() as d:
            from rlsbl.commands.docs_cmd import _cmd_build
            orig_dir = os.getcwd()
            try:
                os.chdir(d)
                with pytest.raises(SystemExit):
                    _cmd_build([], {})
            finally:
                os.chdir(orig_dir)


class TestDocsHelp:
    """Tests for `rlsbl docs` with no subcommand."""

    def test_no_subcommand_shows_help(self, capsys):
        """Running `rlsbl docs` with no args should print help text."""
        from rlsbl.commands.docs_cmd import run_cmd
        run_cmd(None, [], {})
        captured = capsys.readouterr()
        assert "Subcommands:" in captured.out
        assert "init" in captured.out
        assert "build" in captured.out
        assert "serve" in captured.out
        assert "deploy" in captured.out

    def test_unknown_subcommand_errors(self):
        """Running `rlsbl docs <unknown>` should exit with error."""
        from rlsbl.commands.docs_cmd import run_cmd
        with pytest.raises(SystemExit):
            run_cmd(None, ["nonexistent"], {})
