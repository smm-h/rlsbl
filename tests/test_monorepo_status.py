"""Tests for monorepo status subcommand and monorepo-aware rlsbl status."""

import json
import os
import subprocess

import pytest

from rlsbl.commands.monorepo import _cmd_init, _cmd_add, _cmd_status
from rlsbl.workspace import load_workspace, save_workspace


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
        assert "Unreleased" in captured.out
        # Project row
        assert "pkg-a" in captured.out
        assert "npm" in captured.out
        assert "1.0.0" in captured.out

    def test_status_shows_unreleased(self, mock_git_repo, capsys):
        """Project with no tag shows (none) for tag and info in Unreleased column."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "mylib", version="0.2.0")
        _cmd_add(["mylib"], {})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
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


class TestMonorepoStatusChangelog:
    """Tests for the Unreleased changelog column in monorepo status."""

    def test_no_changelog_file(self, mock_git_repo, capsys):
        """Project with no CHANGELOG.md shows 'no changelog'."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a", version="0.1.0")
        _cmd_add(["pkg-a"], {})
        # Auto-scaffold creates CHANGELOG.md; remove it to test the missing case
        changelog = os.path.join(str(mock_git_repo), "pkg-a", "CHANGELOG.md")
        if os.path.exists(changelog):
            os.remove(changelog)
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "no changelog" in captured.out

    def test_changelog_with_entries_no_tag(self, mock_git_repo, capsys):
        """Changelog with bullets and no git tag shows entry count."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-b", version="0.1.0")
        _cmd_add(["pkg-b"], {})
        changelog = mock_git_repo / "pkg-b" / "CHANGELOG.md"
        changelog.write_text("## 0.1.0\n- Added X\n- Added Y\n")
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "2 entries" in captured.out

    def test_changelog_entries_above_tagged_version(self, mock_git_repo, capsys):
        """Only bullets above the tagged version heading are counted."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "proj", version="0.2.0")
        _cmd_add(["proj"], {})
        changelog = mock_git_repo / "proj" / "CHANGELOG.md"
        changelog.write_text("## 0.2.0\n- New feature\n## 0.1.0\n- Initial\n")
        # Create tag matching version 0.1.0
        subprocess.run(
            ["git", "tag", "proj@v0.1.0"],
            cwd=str(mock_git_repo),
            check=True,
        )
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "1 entry" in captured.out

    def test_column_header_is_unreleased(self, mock_git_repo, capsys):
        """The column header should be 'Unreleased', not 'Status'."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-c", version="0.1.0")
        _cmd_add(["pkg-c"], {})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        header_line = captured.out.strip().split("\n")[0]
        assert "Unreleased" in header_line


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


class TestMonorepoStatusWatch:
    """Tests for watch path display in monorepo status."""

    def test_status_shows_watch_count(self, mock_git_repo, capsys):
        """Project with watch paths shows count in Watch column."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling", version="1.0.0")
        _cmd_add(["tooling"], {})

        # Add watch paths to workspace
        projects = load_workspace(".")
        for p in projects:
            if p["name"] == "tooling":
                p["watch"] = ["Package.swift", "shared/**"]
        save_workspace(".", projects)

        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "Watch" in captured.out
        assert "2 paths" in captured.out

    def test_status_no_watch_shows_dash(self, mock_git_repo, capsys):
        """Project without watch paths shows '-' when Watch column is present."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling", version="1.0.0")
        _make_npm_project(mock_git_repo, "core", version="1.0.0")
        _cmd_add(["tooling"], {})
        _cmd_add(["core"], {})

        # Add watch only to tooling
        projects = load_workspace(".")
        for p in projects:
            if p["name"] == "tooling":
                p["watch"] = ["Package.swift"]
        save_workspace(".", projects)

        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "Watch" in captured.out
        assert "1 paths" in captured.out
        # core should show "-"
        lines = captured.out.strip().split("\n")
        core_line = [l for l in lines if "core" in l][0]
        assert "-" in core_line

    def test_status_no_watch_column_when_none(self, mock_git_repo, capsys):
        """Watch column is omitted when no project has watch paths."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling", version="1.0.0")
        _cmd_add(["tooling"], {})
        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "Watch" not in captured.out


class TestMonorepoStatusRemote:
    """Tests for subtree_remote display in monorepo status."""

    def test_status_shows_remote_column(self, mock_git_repo, capsys):
        """Project with subtree_remote shows Remote column with URL."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling", version="1.0.0")
        _cmd_add(["tooling"], {})

        # Add subtree_remote to workspace
        projects = load_workspace(".")
        for p in projects:
            if p["name"] == "tooling":
                p["subtree_remote"] = "git@github.com:user/tooling.git"
        save_workspace(".", projects)

        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "Remote" in captured.out
        assert "git@github.com:user/tooling.git" in captured.out

    def test_status_no_remote_shows_dash(self, mock_git_repo, capsys):
        """Project without subtree_remote shows '-' when Remote column is present."""
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling", version="1.0.0")
        _make_npm_project(mock_git_repo, "core", version="1.0.0")
        _cmd_add(["tooling"], {})
        _cmd_add(["core"], {})

        # Add subtree_remote only to tooling
        projects = load_workspace(".")
        for p in projects:
            if p["name"] == "tooling":
                p["subtree_remote"] = "git@github.com:user/tooling.git"
        save_workspace(".", projects)

        capsys.readouterr()
        _cmd_status({})
        captured = capsys.readouterr()
        assert "Remote" in captured.out
        # core should show "-" in the Remote column
        lines = captured.out.strip().split("\n")
        core_line = [l for l in lines if "core" in l and "tooling" not in l][0]
        # The last column should be "-" for core (since it has no remote)
        assert "-" in core_line
