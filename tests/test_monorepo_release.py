"""Tests for monorepo-aware release behavior in rlsbl.commands.release."""

import json
import os
import subprocess
from io import StringIO
from unittest.mock import patch

import pytest

from rlsbl.commands.release import run_cmd
from rlsbl.targets.base import BaseTarget


class TestMonorepoTagFormat:
    """Test that monorepo_tag_format produces correct tags."""

    def test_monorepo_tag_format_basic(self):
        target = BaseTarget()
        assert target.monorepo_tag_format("core", "1.0.0") == "core@v1.0.0"

    def test_monorepo_tag_format_nested_name(self):
        target = BaseTarget()
        assert target.monorepo_tag_format("my-lib", "2.3.4") == "my-lib@v2.3.4"

    def test_tag_format_unchanged(self):
        target = BaseTarget()
        assert target.tag_format("1.0.0") == "v1.0.0"


class TestMonorepoRelease:
    """Test monorepo-aware release behavior via dry-run."""

    def _setup_monorepo(self, repo_root, project_name="tooling", project_path="tooling",
                        version="1.0.0", changelog_version=None):
        """Create a monorepo workspace structure inside repo_root.

        Creates workspace.toml, project subdir with package.json and CHANGELOG.md.
        Returns the absolute project directory path.
        """
        if changelog_version is None:
            changelog_version = version

        # Workspace config
        ws_dir = repo_root / ".rlsbl-monorepo"
        ws_dir.mkdir(exist_ok=True)
        (ws_dir / "workspace.toml").write_text(
            f'[[projects]]\npath = "{project_path}"\nname = "{project_name}"\n'
        )

        # Project subdir with version file and changelog
        proj_dir = repo_root / project_path
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "package.json").write_text(
            json.dumps({"name": project_name, "version": version}, indent=2) + "\n"
        )
        (proj_dir / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## {changelog_version}\n\n"
            "Patch release with bugfixes and improvements.\n"
        )

        # Commit the monorepo structure
        subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add monorepo structure"],
            cwd=str(repo_root), check=True,
        )

        return proj_dir

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_dry_run_shows_monorepo_tag(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Dry-run in a monorepo project shows prefixed tag."""
        proj_dir = self._setup_monorepo(mock_git_repo, "tooling", "tooling")
        os.chdir(str(proj_dir))

        # mock_run side effects:
        # 1. git fetch origin --quiet
        # 2. git rev-list --count HEAD..origin/main -> 0
        # 3. git tag -l for current tag (tooling@v1.0.0) -> "" (first release)
        # 4. git tag -l for new tag (tooling@v1.0.0) -> "" (doesn't exist)
        mock_run.side_effect = ["", "0", "", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "tooling@v1.0.0" in output
        assert "Tag:" in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_dry_run_shows_monorepo_commit_message(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Commit message uses 'name: release v...' format in monorepo mode."""
        proj_dir = self._setup_monorepo(mock_git_repo, "tooling", "tooling")
        os.chdir(str(proj_dir))

        # First release (no existing tag)
        mock_run.side_effect = ["", "0", "", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "tooling: release v1.0.0" in output
        assert "Commit:" in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_dry_run_bump_shows_monorepo_tag(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """When bumping an existing version in monorepo, tag is name@vX.Y.Z."""
        proj_dir = self._setup_monorepo(
            mock_git_repo, "tooling", "tooling", changelog_version="1.0.1",
        )
        os.chdir(str(proj_dir))

        # Current tag exists -> bump
        # 1. git fetch origin --quiet
        # 2. git rev-list --count -> 0
        # 3. git tag -l tooling@v1.0.0 -> exists
        # 4. git tag -l tooling@v1.0.1 -> doesn't exist
        mock_run.side_effect = ["", "0", "tooling@v1.0.0", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "tooling@v1.0.1" in output
        assert "tooling: release v1.0.1" in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_dry_run_shows_project_info(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Dry-run output includes project name and path."""
        proj_dir = self._setup_monorepo(mock_git_repo, "tooling", "tooling")
        os.chdir(str(proj_dir))

        mock_run.side_effect = ["", "0", "", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "Project:   tooling (tooling)" in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_error_when_in_monorepo_root_not_project(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Error when running release from monorepo root (not inside a project)."""
        # Create workspace but stay at the repo root (not inside any project)
        ws_dir = mock_git_repo / ".rlsbl-monorepo"
        ws_dir.mkdir()
        (ws_dir / "workspace.toml").write_text(
            '[[projects]]\npath = "packages/foo"\nname = "foo"\n'
        )
        proj_dir = mock_git_repo / "packages" / "foo"
        proj_dir.mkdir(parents=True)

        subprocess.run(["git", "add", "."], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add workspace"],
            cwd=str(mock_git_repo), check=True,
        )

        # Skip remote check to reduce mock complexity
        mock_run.side_effect = []

        with pytest.raises(SystemExit) as exc_info:
            run_cmd("npm", ["patch"], {
                "dry-run": True, "quiet": True, "skip-remote-check": True,
            })
        assert exc_info.value.code == 1

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_standalone_release_unchanged(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Non-monorepo release still uses plain tag format."""
        # Create a standalone project (no workspace)
        (mock_git_repo / "package.json").write_text(
            json.dumps({"name": "standalone", "version": "2.0.0"}, indent=2) + "\n"
        )
        (mock_git_repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 2.0.1\n\nPatch release with bugfixes and improvements.\n"
        )
        subprocess.run(["git", "add", "."], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add standalone project"],
            cwd=str(mock_git_repo), check=True,
        )

        # 1. git fetch
        # 2. git rev-list -> 0
        # 3. tag -l v2.0.0 -> exists
        # 4. tag -l v2.0.1 -> doesn't exist
        mock_run.side_effect = ["", "0", "v2.0.0", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "Tag:       v2.0.1" in output
        assert "Commit:    v2.0.1" in output
        # No monorepo project info
        assert "Project:" not in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_monorepo_reads_version_from_project_subdir(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Version is read from the project subdirectory, not the repo root."""
        # Create workspace with project at "libs/core"
        proj_dir = self._setup_monorepo(mock_git_repo, "core", "libs/core")

        # Also create a package.json at repo root with a different version
        (mock_git_repo / "package.json").write_text(
            json.dumps({"name": "root", "version": "9.9.9"}, indent=2) + "\n"
        )
        subprocess.run(["git", "add", "."], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add root package.json"],
            cwd=str(mock_git_repo), check=True,
        )

        os.chdir(str(proj_dir))

        mock_run.side_effect = ["", "0", "", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        # Should read 1.0.0 from libs/core/package.json, not 9.9.9 from root
        assert "Current version: 1.0.0" in output

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_monorepo_reads_changelog_from_project_subdir(
        self, _gh_inst, _gh_auth, _clean, _branch, mock_run,
        mock_git_repo, capsys,
    ):
        """Changelog is read from the project subdirectory."""
        proj_dir = self._setup_monorepo(mock_git_repo, "core", "core")

        # Write a distinct changelog entry so we can verify it was read
        (proj_dir / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 1.0.0\n\nInitial release of core component with key features.\n"
        )
        subprocess.run(["git", "add", "."], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "update changelog"],
            cwd=str(mock_git_repo), check=True,
        )

        os.chdir(str(proj_dir))

        # First release -- tag doesn't exist
        mock_run.side_effect = ["", "0", "", ""]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", [], {"dry-run": True, "quiet": False})

        output = mock_out.getvalue()
        assert "Initial release of core component" in output
