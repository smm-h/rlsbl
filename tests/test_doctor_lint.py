"""Tests for doctor --check flag and library-lint integration."""

import json
import os
from unittest.mock import patch

import pytest

from rlsbl.commands.doctor import (
    CHECK_REGISTRY,
    _check_library_lint,
    run_cmd,
)


def _setup_monorepo(root, projects):
    """Create a monorepo workspace with the given project list.

    Each project dict should have 'path', 'name', and optionally 'library'.
    """
    ws_dir = root / ".rlsbl-monorepo"
    ws_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    for proj in projects:
        lines.append("[[projects]]")
        lines.append(f'path = "{proj["path"]}"')
        lines.append(f'name = "{proj["name"]}"')
        if proj.get("library"):
            lines.append("library = true")
        lines.append("")
    (ws_dir / "workspace.toml").write_text("\n".join(lines))

    for proj in projects:
        proj_dir = root / proj["path"]
        proj_dir.mkdir(parents=True, exist_ok=True)


class TestCheckLibraryLint:
    """Tests for the library-lint check via --check flag."""

    def test_library_lint_with_violations(self, tmp_project):
        """--check library-lint in a monorepo with a violating library -> FAIL."""
        projects = [
            {"path": "libs/mylib", "name": "mylib", "library": True},
        ]
        _setup_monorepo(tmp_project, projects)

        # Create a Python file with a violation (print call)
        lib_dir = tmp_project / "libs" / "mylib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "module.py").write_text("def hello():\n    print('hi')\n")

        status, message = _check_library_lint()
        assert status == "FAIL"
        assert "error" in message

    def test_library_lint_clean(self, tmp_project):
        """--check library-lint in a monorepo with a clean library -> PASS."""
        projects = [
            {"path": "libs/mylib", "name": "mylib", "library": True},
        ]
        _setup_monorepo(tmp_project, projects)

        # Create a clean Python file (no violations)
        lib_dir = tmp_project / "libs" / "mylib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "module.py").write_text("def add(a, b):\n    return a + b\n")

        status, message = _check_library_lint()
        assert status == "PASS"
        assert "clean" in message

    def test_library_lint_no_monorepo(self, tmp_project):
        """--check library-lint with no monorepo -> PASS with message."""
        status, message = _check_library_lint()
        assert status == "PASS"
        assert "not in a monorepo" in message

    def test_library_lint_no_library_projects(self, tmp_project):
        """--check library-lint with no library=true projects -> PASS."""
        projects = [
            {"path": "apps/myapp", "name": "myapp"},
        ]
        _setup_monorepo(tmp_project, projects)

        status, message = _check_library_lint()
        assert status == "PASS"
        assert "no library projects" in message

    def test_check_nonexistent(self, mock_git_repo, capsys):
        """--check with unknown name -> error listing valid checks."""
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {"check": "nonexistent"})
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "unknown check 'nonexistent'" in captured.err
        # Should list valid check names
        assert "library-lint" in captured.err
        assert "lock" in captured.err

    def test_doctor_without_check_includes_library_lint(self, mock_git_repo, capsys):
        """Doctor without --check runs all checks including Library lint."""
        pkg = {"name": "test-pkg", "version": "1.0.0"}
        (mock_git_repo / "package.json").write_text(json.dumps(pkg))

        with patch("rlsbl.commands.doctor._check_remote_tag",
                    return_value=("PASS", "v1.0.0 on origin")), \
             patch("rlsbl.commands.doctor._check_github_release",
                    return_value=("PASS", "v1.0.0 exists")), \
             patch("rlsbl.commands.doctor._check_branch_sync",
                    return_value=("PASS", "up to date")):
            run_cmd(None, [], {})

        captured = capsys.readouterr()
        assert "Library lint" in captured.out

    def test_check_registry_has_all_checks(self):
        """Verify all expected check names are registered."""
        expected = {
            "lock", "versions", "names", "license", "description",
            "local-tag", "remote-tag", "github-release", "branch-sync",
            "changelog", "library-lint",
        }
        assert expected == set(CHECK_REGISTRY.keys())

    def test_check_single_pass_exit_0(self, mock_git_repo):
        """--check with a passing check exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {"check": "lock"})
        assert exc_info.value.code == 0

    def test_library_lint_warnings_only(self, tmp_project):
        """Library with only warnings (logging) -> WARN."""
        projects = [
            {"path": "libs/mylib", "name": "mylib", "library": True},
        ]
        _setup_monorepo(tmp_project, projects)

        lib_dir = tmp_project / "libs" / "mylib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "module.py").write_text(
            "import logging\n"
            "def hello():\n"
            "    logging.info('hi')\n"
        )

        status, message = _check_library_lint()
        assert status == "WARN"
        assert "warning" in message
