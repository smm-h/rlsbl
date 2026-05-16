"""Tests for the 'rlsbl monorepo lint' command."""

import os

import pytest

from conftest import run_git, git_head, make_commit, make_workspace
from rlsbl.commands.monorepo import _cmd_lint
from rlsbl.workspace import WORKSPACE_DIR, WORKSPACE_FILE


class TestMonorepoLint:
    def test_clean_workspace_exits_zero(self, monorepo_fixture, capsys):
        """All projects registered, no stale entries -> exits 0, no output."""
        # monorepo_fixture has python/ (pyproject.toml) and go/ (no manifest in
        # the recognized list, only a VERSION file). We need to add a manifest
        # to go/ so it counts as a project, OR just test that registered paths
        # with manifests pass cleanly.
        # Actually go/ has no recognized manifest (VERSION isn't in the list),
        # so it won't show as unregistered. But it IS registered, so it will
        # show as stale. Let's add a go.mod to it.
        root = monorepo_fixture.root
        (root / "go" / "go.mod").write_text("module example.com/mygolib\n\ngo 1.21\n")
        _cmd_lint({})
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_unregistered_project_exits_one(self, monorepo_fixture, capsys):
        """Directory with manifest not in workspace.toml -> exits 1, reports it."""
        root = monorepo_fixture.root
        # Add go.mod to go/ so it doesn't appear stale
        (root / "go" / "go.mod").write_text("module example.com/mygolib\n\ngo 1.21\n")
        # Create an unregistered project
        unregistered = root / "newpkg"
        unregistered.mkdir()
        (unregistered / "package.json").write_text('{"name": "newpkg", "version": "0.1.0"}')

        with pytest.raises(SystemExit) as exc_info:
            _cmd_lint({})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Unregistered projects:" in captured.out
        assert "newpkg" in captured.out

    def test_stale_entry_missing_dir_exits_one(self, monorepo_fixture, capsys):
        """Workspace entry whose directory doesn't exist -> exits 1, reports it."""
        root = monorepo_fixture.root
        # Add go.mod to go/ so go is not stale
        (root / "go" / "go.mod").write_text("module example.com/mygolib\n\ngo 1.21\n")
        # Add a stale entry for a non-existent directory
        make_workspace(root, [
            {"path": "python", "name": "mypylib"},
            {"path": "go", "name": "mygolib"},
            {"path": "phantom", "name": "phantom"},
        ])

        with pytest.raises(SystemExit) as exc_info:
            _cmd_lint({})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Stale entries:" in captured.out
        assert "phantom" in captured.out

    def test_stale_entry_no_manifest_exits_one(self, monorepo_fixture, capsys):
        """Workspace entry whose directory has no manifest -> exits 1, reports it."""
        root = monorepo_fixture.root
        # go/ has no recognized manifest (only VERSION), so it will be stale
        # python/ has pyproject.toml, so it's fine
        # Don't add go.mod this time -- go/ should appear stale
        with pytest.raises(SystemExit) as exc_info:
            _cmd_lint({})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Stale entries:" in captured.out
        assert "go" in captured.out

    def test_both_issues_exits_one(self, monorepo_fixture, capsys):
        """Both unregistered and stale -> exits 1, reports both."""
        root = monorepo_fixture.root
        # go/ has no manifest -> stale
        # Create an unregistered project
        extra = root / "extra"
        extra.mkdir()
        (extra / "Cargo.toml").write_text('[package]\nname = "extra"\nversion = "0.1.0"\n')

        with pytest.raises(SystemExit) as exc_info:
            _cmd_lint({})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Unregistered projects:" in captured.out
        assert "extra" in captured.out
        assert "Stale entries:" in captured.out
        assert "go" in captured.out

    def test_hidden_dirs_skipped(self, monorepo_fixture, capsys):
        """Hidden directories (starting with .) are not scanned."""
        root = monorepo_fixture.root
        # Add go.mod to go/ so it's not stale
        (root / "go" / "go.mod").write_text("module example.com/mygolib\n\ngo 1.21\n")
        # Create a hidden directory with a manifest -- should be ignored
        hidden = root / ".hidden"
        hidden.mkdir()
        (hidden / "package.json").write_text('{"name": "hidden"}')

        _cmd_lint({})
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_workspace_exits_with_error(self, mock_git_repo, capsys):
        """No workspace found -> exits with error."""
        with pytest.raises(SystemExit) as exc_info:
            _cmd_lint({})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No workspace found" in captured.err
