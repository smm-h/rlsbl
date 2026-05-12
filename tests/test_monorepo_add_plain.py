"""Tests for monorepo add with --target flag (plain and explicit targets)."""

import json
import os

import pytest

from rlsbl.commands.monorepo import _cmd_init, _cmd_add
from rlsbl.workspace import load_workspace


class TestAddTargetPlain:
    def test_plain_target_succeeds_on_bare_directory(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "mydir")
        os.makedirs(bare_dir)
        _cmd_add(["mydir"], {"target": "plain"})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 1
        assert projects[0]["path"] == "mydir"
        assert projects[0]["name"] == "mydir"
        captured = capsys.readouterr()
        assert "Added project 'mydir' at mydir" in captured.out

    def test_plain_target_creates_version_file(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "mydir")
        os.makedirs(bare_dir)
        _cmd_add(["mydir"], {"target": "plain"})
        version_path = os.path.join(str(mock_git_repo), "mydir", "VERSION")
        assert os.path.exists(version_path)
        with open(version_path) as f:
            assert f.read().strip() == "0.1.0"

    def test_plain_target_does_not_overwrite_existing_version(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "mydir")
        os.makedirs(bare_dir)
        version_path = os.path.join(bare_dir, "VERSION")
        with open(version_path, "w") as f:
            f.write("1.0.0\n")
        _cmd_add(["mydir"], {"target": "plain"})
        with open(version_path) as f:
            assert f.read().strip() == "1.0.0"

    def test_plain_project_in_workspace(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "mydir")
        os.makedirs(bare_dir)
        _cmd_add(["mydir"], {"target": "plain"})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 1
        assert projects[0]["name"] == "mydir"
        assert projects[0]["path"] == "mydir"

    def test_bare_directory_without_target_flag_errors(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "empty-dir")
        os.makedirs(bare_dir)
        with pytest.raises(SystemExit):
            _cmd_add(["empty-dir"], {})
        captured = capsys.readouterr()
        assert "No release target detected" in captured.err


class TestAddExplicitTarget:
    def test_explicit_npm_target_skips_auto_detection(self, mock_git_repo, capsys):
        """--target npm works on a directory with package.json."""
        _cmd_init({})
        proj_dir = os.path.join(str(mock_git_repo), "mypkg")
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, "package.json"), "w") as f:
            json.dump({"name": "mypkg", "version": "1.0.0"}, f)
        _cmd_add(["mypkg"], {"target": "npm"})
        projects = load_workspace(str(mock_git_repo))
        assert len(projects) == 1
        assert projects[0]["name"] == "mypkg"

    def test_unknown_target_errors(self, mock_git_repo, capsys):
        _cmd_init({})
        proj_dir = os.path.join(str(mock_git_repo), "mydir")
        os.makedirs(proj_dir)
        with pytest.raises(SystemExit):
            _cmd_add(["mydir"], {"target": "nonexistent"})
        captured = capsys.readouterr()
        assert "Unknown target" in captured.err

    def test_plain_target_with_name_flag(self, mock_git_repo, capsys):
        _cmd_init({})
        bare_dir = os.path.join(str(mock_git_repo), "libs/docs")
        os.makedirs(bare_dir, exist_ok=True)
        _cmd_add(["libs/docs"], {"target": "plain", "name": "my-docs"})
        projects = load_workspace(str(mock_git_repo))
        assert projects[0]["name"] == "my-docs"
