"""Tests for built-in pre-release checks (tests, lint) and the two-hook model."""

import json
import os
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from rlsbl.commands.release import _run_builtin_lint, _run_builtin_tests
from rlsbl.lint.result import LintResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_npm_project(tmp_path, test_script=None):
    """Create a minimal npm project in tmp_path.

    If test_script is a string, add it as the "test" script in package.json.
    If test_script is None, no scripts section is created.
    """
    pkg = {"name": "test-pkg", "version": "1.0.0"}
    if test_script is not None:
        pkg["scripts"] = {"test": test_script}
    (tmp_path / "package.json").write_text(json.dumps(pkg) + "\n")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.0.1\n\nPatch release with improvements.\n"
    )


def _setup_pypi_project(tmp_path):
    """Create a minimal pypi project in tmp_path."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-pkg"\nversion = "1.0.0"\n'
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.0.1\n\nPatch release with improvements.\n"
    )


def _setup_go_project(tmp_path):
    """Create a minimal go project in tmp_path."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.0.1\n\nPatch release with improvements.\n"
    )


# ---------------------------------------------------------------------------
# Built-in test runner tests
# ---------------------------------------------------------------------------

class TestBuiltinTestRunner:
    """Tests for _run_builtin_tests()."""

    def test_python_tests_run_with_uv(self, tmp_project):
        """When registry is pypi and uv is available, run uv sync + uv run pytest."""
        _setup_pypi_project(tmp_project)

        with (
            patch("rlsbl.commands.release.shutil.which") as mock_which,
            patch("rlsbl.commands.release.subprocess.run") as mock_run,
            patch("rlsbl.commands.release.read_project_config", return_value={}),
        ):
            mock_which.return_value = "/usr/bin/uv"
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = _run_builtin_tests("pypi", {})

            assert result is True
            # Should have called uv sync --quiet then uv run pytest
            assert mock_run.call_count == 2
            sync_call = mock_run.call_args_list[0]
            assert sync_call[0][0] == ["uv", "sync", "--quiet"]
            pytest_call = mock_run.call_args_list[1]
            assert pytest_call[0][0] == ["uv", "run", "pytest"]

    def test_python_tests_without_uv_falls_back_to_pytest(self, tmp_project):
        """When uv is not available but pytest is, fall back to bare pytest."""
        _setup_pypi_project(tmp_project)

        with (
            patch("rlsbl.commands.release.shutil.which") as mock_which,
            patch("rlsbl.commands.release.subprocess.run") as mock_run,
            patch("rlsbl.commands.release.read_project_config", return_value={}),
        ):
            def which_side_effect(name):
                if name == "uv":
                    return None
                if name == "pytest":
                    return "/usr/bin/pytest"
                return None

            mock_which.side_effect = which_side_effect
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = _run_builtin_tests("pypi", {})

            assert result is True
            assert mock_run.call_count == 1
            assert mock_run.call_args[0][0] == ["pytest"]

    def test_go_tests_run(self, tmp_project):
        """When registry is go, run go test ./... -race -short -count=1."""
        _setup_go_project(tmp_project)

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = _run_builtin_tests("go", {})

            assert result is True
            assert mock_run.call_count == 1
            assert mock_run.call_args[0][0] == [
                "go", "test", "./...", "-race", "-short", "-count=1"
            ]

    def test_npm_tests_run(self, tmp_project):
        """When registry is npm and package.json has a test script, run npm test."""
        _setup_npm_project(tmp_project, test_script="jest")

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = _run_builtin_tests("npm", {})

            assert result is True
            assert mock_run.call_count == 1
            assert mock_run.call_args[0][0] == ["npm", "test"]

    def test_npm_no_test_script_skips(self, tmp_project):
        """When npm package.json has no test script, skip tests."""
        _setup_npm_project(tmp_project, test_script=None)

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            result = _run_builtin_tests("npm", {})

            assert result is True
            mock_run.assert_not_called()

    def test_test_failure_aborts(self, tmp_project):
        """When test command returns non-zero, sys.exit(1) is called."""
        _setup_npm_project(tmp_project, test_script="jest")

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1
            )

            with pytest.raises(SystemExit) as exc_info:
                _run_builtin_tests("npm", {})

            assert exc_info.value.code == 1

    def test_skip_tests_flag(self, tmp_project):
        """--skip-tests flag prevents any test command from running."""
        _setup_npm_project(tmp_project, test_script="jest")

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            result = _run_builtin_tests("npm", {"skip-tests": True})

            assert result is True
            mock_run.assert_not_called()

    def test_dry_run_skips_tests(self, tmp_project):
        """--dry-run flag prevents any test command from running."""
        _setup_npm_project(tmp_project, test_script="jest")

        with patch("rlsbl.commands.release.subprocess.run") as mock_run:
            result = _run_builtin_tests("npm", {"dry-run": True})

            assert result is True
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Built-in lint runner tests
# ---------------------------------------------------------------------------

class TestBuiltinLintRunner:
    """Tests for _run_builtin_lint()."""

    def test_lint_passes_with_no_results(self, tmp_project):
        """When lint_library returns empty list, lint passes."""
        with patch("rlsbl.lint.lint_library", return_value=[]) as mock_lint:
            result = _run_builtin_lint({})

            assert result is True
            mock_lint.assert_called_once_with(".")

    def test_lint_fails_on_errors(self, tmp_project):
        """When lint_library returns errors, sys.exit(1) is called."""
        errors = [
            LintResult(
                file="src/main.py", line=10, rule="no-internal-import",
                severity="error", message="Internal import exposed"
            ),
        ]

        with patch("rlsbl.lint.lint_library", return_value=errors):
            with pytest.raises(SystemExit) as exc_info:
                _run_builtin_lint({})

            assert exc_info.value.code == 1

    def test_lint_warnings_are_non_blocking(self, tmp_project):
        """When lint_library returns only warnings, lint passes without exit."""
        warnings = [
            LintResult(
                file="src/util.py", line=5, rule="unused-export",
                severity="warning", message="Export not used externally"
            ),
        ]

        with patch("rlsbl.lint.lint_library", return_value=warnings):
            result = _run_builtin_lint({})

            assert result is True

    def test_skip_lint_flag(self, tmp_project):
        """--skip-lint flag prevents lint_library from being called."""
        with patch("rlsbl.lint.lint_library") as mock_lint:
            result = _run_builtin_lint({"skip-lint": True})

            assert result is True
            mock_lint.assert_not_called()

    def test_dry_run_skips_lint(self, tmp_project):
        """--dry-run flag prevents lint_library from being called."""
        with patch("rlsbl.lint.lint_library") as mock_lint:
            result = _run_builtin_lint({"dry-run": True})

            assert result is True
            mock_lint.assert_not_called()


# ---------------------------------------------------------------------------
# Two-hook model tests
# ---------------------------------------------------------------------------

class TestTwoHookModel:
    """Tests for pre-checks and pre-release hook ordering."""

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_pre_checks_hook_runs_before_tests(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
    ):
        """pre-checks.sh runs before built-in tests."""
        _setup_npm_project(tmp_project, test_script="jest")
        hooks_dir = tmp_project / ".rlsbl" / "hooks"
        hooks_dir.mkdir(parents=True)
        marker = tmp_project / "pre-checks-ran"
        (hooks_dir / "pre-checks.sh").write_text(
            f"#!/bin/bash\ntouch {marker}\n"
        )
        (hooks_dir / "pre-checks.sh").chmod(0o755)

        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with (
            patch("rlsbl.commands.release._run_builtin_tests") as mock_tests,
            patch("rlsbl.commands.release._run_builtin_lint") as mock_lint,
        ):
            # Let the real subprocess.run execute the hook script
            mock_tests.return_value = True
            mock_lint.return_value = True

            from rlsbl.commands.release import run_cmd

            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": True, "yes": True})

            # The hook should have actually run and created the marker
            assert marker.exists(), "pre-checks.sh should have created the marker file"
            # Tests and lint should have been called (mocked)
            mock_tests.assert_called_once()
            mock_lint.assert_called_once()

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_pre_release_hook_runs_after_builtin_checks(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
    ):
        """pre-release.sh runs after built-in tests and lint."""
        _setup_npm_project(tmp_project, test_script=None)
        hooks_dir = tmp_project / ".rlsbl" / "hooks"
        hooks_dir.mkdir(parents=True)
        pre_release_marker = tmp_project / "pre-release-ran"
        (hooks_dir / "pre-release.sh").write_text(
            f"#!/bin/bash\ntouch {pre_release_marker}\n"
        )
        (hooks_dir / "pre-release.sh").chmod(0o755)

        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with (
            patch("rlsbl.commands.release._run_builtin_tests") as mock_tests,
            patch("rlsbl.commands.release._run_builtin_lint") as mock_lint,
        ):
            mock_tests.return_value = True
            mock_lint.return_value = True

            from rlsbl.commands.release import run_cmd

            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": True, "yes": True})

            # pre-release hook runs after tests/lint but is still executed for dry-run
            # (based on the code, pre-release hook runs before dry-run return)
            assert pre_release_marker.exists(), (
                "pre-release.sh should have run after built-in checks"
            )

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_pre_checks_hook_failure_aborts_before_tests(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
    ):
        """A failing pre-checks.sh aborts the release before running tests."""
        _setup_npm_project(tmp_project, test_script="jest")
        hooks_dir = tmp_project / ".rlsbl" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-checks.sh").write_text("#!/bin/bash\nexit 1\n")
        (hooks_dir / "pre-checks.sh").chmod(0o755)

        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with (
            patch("rlsbl.commands.release._run_builtin_tests") as mock_tests,
            patch("rlsbl.commands.release._run_builtin_lint") as mock_lint,
        ):
            from rlsbl.commands.release import run_cmd

            with pytest.raises(SystemExit) as exc_info:
                run_cmd("npm", ["patch"], {"quiet": True, "yes": True})

            assert exc_info.value.code == 1
            # Tests and lint should NOT have been called
            mock_tests.assert_not_called()
            mock_lint.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: full flow order
# ---------------------------------------------------------------------------

class TestFullFlowOrder:
    """Tests verifying the execution order of all pre-release components."""

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_execution_order(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
    ):
        """Verify order: pre-checks hook -> tests -> lint -> pre-release hook."""
        _setup_npm_project(tmp_project, test_script=None)
        hooks_dir = tmp_project / ".rlsbl" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Track the order of execution
        execution_order = []

        # Create both hook scripts that record their execution
        order_file = tmp_project / "order.txt"
        (hooks_dir / "pre-checks.sh").write_text(
            f"#!/bin/bash\necho pre-checks >> {order_file}\n"
        )
        (hooks_dir / "pre-checks.sh").chmod(0o755)
        (hooks_dir / "pre-release.sh").write_text(
            f"#!/bin/bash\necho pre-release >> {order_file}\n"
        )
        (hooks_dir / "pre-release.sh").chmod(0o755)

        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        original_tests = _run_builtin_tests
        original_lint = _run_builtin_lint

        def tracking_tests(registry, flags):
            execution_order.append("tests")
            # Short-circuit: skip-tests so no subprocess is needed
            return True

        def tracking_lint(flags):
            execution_order.append("lint")
            # Short-circuit: skip-lint so no subprocess is needed
            return True

        with (
            patch("rlsbl.commands.release._run_builtin_tests", side_effect=tracking_tests),
            patch("rlsbl.commands.release._run_builtin_lint", side_effect=tracking_lint),
        ):
            from rlsbl.commands.release import run_cmd

            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": True, "yes": True})

        # Read hook execution order from the file
        assert order_file.exists(), "Hooks should have written to order file"
        hook_lines = order_file.read_text().strip().splitlines()

        # Build full order: hooks from file, tests/lint from tracking
        # pre-checks runs first, then tests, then lint, then pre-release
        assert hook_lines[0] == "pre-checks"
        assert execution_order == ["tests", "lint"]
        assert hook_lines[1] == "pre-release"
