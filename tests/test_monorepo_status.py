"""Tests for monorepo status subcommand and monorepo-aware rlsbl status."""

import json
import os
import subprocess

import pytest

from rlsbl.commands.monorepo import _cmd_init, _cmd_add, _cmd_status
from rlsbl.workspace import load_workspace


def _make_npm_project(base_path, subdir, version="0.1.0"):
    """Create a minimal npm project (package.json) so detect_targets finds it."""
    proj_dir = os.path.join(str(base_path), subdir)
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "package.json"), "w") as f:
        json.dump({"name": "test-" + subdir.replace("/", "-"), "version": version}, f)
    return subdir


class TestMonorepoStatus:
    """Tests for the 'rlsbl monorepo status' subcommand."""

    def test_status_empty_workspace(self, mock_git_repo, capsys):
        _cmd_init({})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "No projects in workspace." in captured.out

    def test_status_with_projects(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a", version="1.0.0")
        _cmd_add(["pkg-a"], {})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        # Header
        assert "Project" in captured.out
        assert "Path" in captured.out
        assert "Target" in captured.out
        assert "Version" in captured.out
        assert "Tag" in captured.out
        assert "Status" in captured.out
        # Project row
        assert "pkg-a" in captured.out
        assert "npm" in captured.out
        assert "1.0.0" in captured.out

    def test_status_shows_unreleased(self, mock_git_repo, capsys):
        """Project with no tag or version > latest tag shows 'unreleased'."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "mylib", version="0.2.0")
        _cmd_add(["mylib"], {})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "unreleased" in captured.out
        assert "(none)" in captured.out

    def test_status_shows_released(self, mock_git_repo, capsys):
        """Project with a tag matching its version shows 'released'."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "mylib", version="1.0.0")
        _cmd_add(["mylib"], {})
        # Create a matching tag
        subprocess.run(
            ["git", "tag", "mylib@v1.0.0"],
            cwd=str(mock_git_repo),
            check=True,
        )
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "released" in captured.out
        assert "mylib@v1.0.0" in captured.out

    def test_status_no_workspace(self, mock_git_repo, capsys):
        """Without an initialized workspace, status should error."""
        with pytest.raises(SystemExit):
            _cmd_status({})

    def test_status_multiple_projects(self, mock_git_repo, capsys):
        """Status displays all projects in the workspace."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "alpha", version="1.0.0")
        _make_npm_project(mock_git_repo, "beta", version="2.0.0")
        _cmd_add(["alpha"], {})
        _cmd_add(["beta"], {})
        # Tag only alpha
        subprocess.run(
            ["git", "tag", "alpha@v1.0.0"],
            cwd=str(mock_git_repo),
            check=True,
        )
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        # Header + 2 project rows
        assert len(lines) == 3
        assert "alpha" in captured.out
        assert "beta" in captured.out


class TestStatusMonorepoAware:
    """Tests for monorepo awareness in 'rlsbl status'."""

    def test_status_shows_monorepo_hint(self, mock_git_repo, capsys):
        """When inside a monorepo project, status output includes the hint."""
        # Set up monorepo workspace
        _cmd_init({})
        _make_npm_project(mock_git_repo, "core", version="1.0.0")
        _cmd_add(["core"], {})
        capsys.readouterr()

        # Change into the project directory
        os.chdir(str(mock_git_repo / "core"))

        from rlsbl.commands.status import run_cmd
        run_cmd("npm", [], {})
        captured = capsys.readouterr()

        assert "Part of monorepo" in captured.out
        assert "rlsbl monorepo status" in captured.out
        assert "core@v1.0.0" in captured.out

    def test_status_standalone_unchanged(self, mock_git_repo, capsys):
        """When NOT in a monorepo, no hint shown."""
        # Create a standalone npm project (no monorepo init)
        with open(str(mock_git_repo / "package.json"), "w") as f:
            json.dump({"name": "standalone", "version": "1.0.0"}, f)

        from rlsbl.commands.status import run_cmd
        run_cmd("npm", [], {})
        captured = capsys.readouterr()

        assert "Part of monorepo" not in captured.out
        assert "Mono tag" not in captured.out
        # Normal status output still works
        assert "Package:" in captured.out
        assert "standalone" in captured.out

    def test_status_monorepo_root_shows_hint_only(self, mock_git_repo, capsys):
        """At monorepo root (not inside a project), show hint without scoped tag."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "core", version="1.0.0")
        _cmd_add(["core"], {})
        capsys.readouterr()

        # Create a package.json at root so status command works
        with open(str(mock_git_repo / "package.json"), "w") as f:
            json.dump({"name": "monorepo-root", "version": "0.0.1"}, f)

        from rlsbl.commands.status import run_cmd
        run_cmd("npm", [], {})
        captured = capsys.readouterr()

        assert "Part of monorepo" in captured.out
        # Root is not a registered project, so no mono tag
        assert "Mono tag" not in captured.out
