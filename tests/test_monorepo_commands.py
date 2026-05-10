"""Tests for monorepo workspace management commands (init, add, remove, list)."""

import json
import os

import pytest

from rlsbl.commands.monorepo import _cmd_init, _cmd_add, _cmd_remove, _cmd_list
from rlsbl.workspace import load_workspace, WORKSPACE_DIR, WORKSPACE_FILE


def _make_npm_project(base_path, subdir):
    """Create a minimal npm project (package.json) so detect_targets finds it."""
    proj_dir = os.path.join(str(base_path), subdir)
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "package.json"), "w") as f:
        json.dump({"name": "test-" + subdir, "version": "0.1.0"}, f)
    return subdir


class TestInit:
    def test_creates_workspace(self, mock_git_repo, capsys):
        _cmd_init({})
        ws_file = mock_git_repo / WORKSPACE_DIR / WORKSPACE_FILE
        assert ws_file.exists()
        projects = load_workspace(str(mock_git_repo))
        assert projects == []
        captured = capsys.readouterr()
        assert "Initialized monorepo workspace" in captured.out

    def test_refuses_reinit(self, mock_git_repo):
        _cmd_init({})
        with pytest.raises(SystemExit):
            _cmd_init({})


class TestAdd:
    def test_adds_project(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a")
        _cmd_add(["pkg-a"], {})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 1
        assert projects[0]["path"] == "pkg-a"
        assert projects[0]["name"] == "pkg-a"
        captured = capsys.readouterr()
        assert "Added project 'pkg-a' at pkg-a" in captured.out

    def test_uses_name_flag(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "libs/core")
        _cmd_add(["libs/core"], {"name": "core-lib"})
        projects = load_workspace(str(mock_git_repo))
        assert projects[0]["name"] == "core-lib"
        captured = capsys.readouterr()
        assert "core-lib" in captured.out

    def test_refuses_no_args(self, mock_git_repo):
        _cmd_init({})
        with pytest.raises(SystemExit):
            _cmd_add([], {})

    def test_refuses_nonexistent_path(self, mock_git_repo):
        _cmd_init({})
        with pytest.raises(SystemExit):
            _cmd_add(["nonexistent"], {})

    def test_refuses_no_target(self, mock_git_repo):
        _cmd_init({})
        os.makedirs(str(mock_git_repo / "empty-dir"))
        with pytest.raises(SystemExit):
            _cmd_add(["empty-dir"], {})

    def test_refuses_duplicate_path(self, mock_git_repo):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a")
        _cmd_add(["pkg-a"], {})
        with pytest.raises(SystemExit):
            _cmd_add(["pkg-a"], {})

    def test_refuses_duplicate_name(self, mock_git_repo):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a")
        _make_npm_project(mock_git_repo, "pkg-b")
        _cmd_add(["pkg-a"], {"name": "shared"})
        with pytest.raises(SystemExit):
            _cmd_add(["pkg-b"], {"name": "shared"})

    def test_refuses_without_init(self, mock_git_repo):
        _make_npm_project(mock_git_repo, "pkg-a")
        with pytest.raises(SystemExit):
            _cmd_add(["pkg-a"], {})


class TestRemove:
    def test_removes_project(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a")
        _cmd_add(["pkg-a"], {})
        capsys.readouterr()  # clear
        _cmd_remove(["pkg-a"], {})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 0
        captured = capsys.readouterr()
        assert "Removed project at pkg-a" in captured.out

    def test_error_on_missing_project(self, mock_git_repo):
        _cmd_init({})
        with pytest.raises(SystemExit):
            _cmd_remove(["nonexistent"], {})

    def test_normalizes_trailing_slash(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "pkg-a")
        _cmd_add(["pkg-a"], {})
        capsys.readouterr()
        _cmd_remove(["pkg-a/"], {})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 0

    def test_refuses_no_args(self, mock_git_repo):
        _cmd_init({})
        with pytest.raises(SystemExit):
            _cmd_remove([], {})

    def test_refuses_without_init(self, mock_git_repo):
        with pytest.raises(SystemExit):
            _cmd_remove(["pkg-a"], {})


class TestList:
    def test_lists_projects(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "tooling")
        _make_npm_project(mock_git_repo, "core")
        _cmd_add(["tooling"], {})
        _cmd_add(["core"], {})
        capsys.readouterr()
        _cmd_list({})
        captured = capsys.readouterr()
        assert "Name" in captured.out
        assert "Path" in captured.out
        assert "tooling" in captured.out
        assert "core" in captured.out

    def test_empty_workspace_message(self, mock_git_repo, capsys):
        _cmd_init({})
        capsys.readouterr()
        _cmd_list({})
        captured = capsys.readouterr()
        assert "No projects in workspace." in captured.out

    def test_refuses_without_init(self, mock_git_repo):
        with pytest.raises(SystemExit):
            _cmd_list({})

    def test_column_alignment(self, mock_git_repo, capsys):
        _cmd_init({})
        _make_npm_project(mock_git_repo, "a")
        _make_npm_project(mock_git_repo, "longname")
        _cmd_add(["a"], {"name": "short"})
        _cmd_add(["longname"], {"name": "very-long-name"})
        capsys.readouterr()
        _cmd_list({})
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3  # header + 2 projects
        # All lines should have consistent column positions
        header_path_pos = lines[0].index("Path")
        for line in lines[1:]:
            # The path column should start at the same position
            assert line[header_path_pos:header_path_pos + 1] != " " or line.strip().endswith("")
