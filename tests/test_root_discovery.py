"""Tests for project root discovery (find_project_root and main() integration)."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from rlsbl.utils import find_project_root


class TestFindProjectRoot:
    """Unit tests for find_project_root()."""

    def test_find_root_in_current_dir(self, tmp_path, monkeypatch):
        """When .rlsbl/ is in cwd, returns cwd."""
        (tmp_path / ".rlsbl").mkdir()
        monkeypatch.chdir(tmp_path)
        assert find_project_root() == str(tmp_path)

    def test_find_root_in_parent(self, tmp_path, monkeypatch):
        """When .rlsbl/ is in parent, returns parent (subdirectory invocation)."""
        (tmp_path / ".rlsbl").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        assert find_project_root() == str(tmp_path)

    def test_find_root_deeply_nested(self, tmp_path, monkeypatch):
        """When .rlsbl/ is three levels up, returns correct ancestor."""
        (tmp_path / ".rlsbl").mkdir()
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        assert find_project_root() == str(tmp_path)

    def test_find_monorepo_root(self, tmp_path, monkeypatch):
        """When only .rlsbl-monorepo/ exists (no .rlsbl/), returns that dir."""
        (tmp_path / ".rlsbl-monorepo").mkdir()
        subdir = tmp_path / "packages" / "foo"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        assert find_project_root() == str(tmp_path)

    def test_prefers_rlsbl_over_monorepo(self, tmp_path, monkeypatch):
        """Sub-project has .rlsbl/, ancestor has .rlsbl-monorepo/: returns sub-project dir."""
        (tmp_path / ".rlsbl-monorepo").mkdir()
        subproject = tmp_path / "packages" / "foo"
        subproject.mkdir(parents=True)
        (subproject / ".rlsbl").mkdir()
        monkeypatch.chdir(subproject)
        assert find_project_root() == str(subproject)

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """No markers anywhere, returns None."""
        # tmp_path has no .rlsbl/ or .rlsbl-monorepo/
        monkeypatch.chdir(tmp_path)
        assert find_project_root() is None

    def test_start_parameter(self, tmp_path):
        """Explicit start parameter overrides cwd."""
        (tmp_path / ".rlsbl").mkdir()
        subdir = tmp_path / "deep" / "nested"
        subdir.mkdir(parents=True)
        assert find_project_root(start=str(subdir)) == str(tmp_path)


class TestMainRootDiscovery:
    """Integration tests for root discovery in main()."""

    def test_main_chdir_for_project_commands(self, tmp_path, monkeypatch):
        """Project-dependent commands chdir to project root from a subdirectory."""
        (tmp_path / ".rlsbl").mkdir()
        (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)

        # Patch sys.argv for a project command and mock the command handler
        monkeypatch.setattr(sys, "argv", ["rlsbl", "status"])
        mock_module = MagicMock()
        with patch("rlsbl._get_command_module", return_value=mock_module):
            with patch("rlsbl.detect_registries", return_value=["npm"]):
                from rlsbl import main
                main()

        # After main(), cwd should be the project root
        assert os.getcwd() == str(tmp_path)

    def test_main_no_chdir_for_independent_commands(self, tmp_path, monkeypatch):
        """Independent commands (discover, check, watch) don't chdir."""
        (tmp_path / ".rlsbl").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        original_cwd = os.getcwd()

        monkeypatch.setattr(sys, "argv", ["rlsbl", "discover"])
        mock_module = MagicMock()
        with patch("rlsbl._get_command_module", return_value=mock_module):
            from rlsbl import main
            main()

        assert os.getcwd() == original_cwd

    def test_main_errors_when_no_root_found(self, tmp_path, monkeypatch):
        """Project commands fail with error when no .rlsbl/ found."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rlsbl", "status"])

        from rlsbl import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_scaffold_stays_in_cwd_for_new_project(self, tmp_path, monkeypatch):
        """Scaffold with no .rlsbl/ stays in cwd (new project init)."""
        (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
        monkeypatch.chdir(tmp_path)
        original_cwd = os.getcwd()

        monkeypatch.setattr(sys, "argv", ["rlsbl", "scaffold"])
        mock_module = MagicMock()
        with patch("rlsbl._get_command_module", return_value=mock_module):
            with patch("rlsbl.detect_registries", return_value=["npm"]):
                with patch("rlsbl.commands.init_cmd.read_project_config", return_value={}):
                    from rlsbl import main
                    main()

        assert os.getcwd() == original_cwd

    def test_scaffold_finds_root_for_update(self, tmp_path, monkeypatch):
        """Scaffold with .rlsbl/ in parent chdirs there (existing project update)."""
        (tmp_path / ".rlsbl").mkdir()
        (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
        subdir = tmp_path / "src"
        subdir.mkdir()
        monkeypatch.chdir(subdir)

        monkeypatch.setattr(sys, "argv", ["rlsbl", "scaffold"])
        mock_module = MagicMock()
        with patch("rlsbl._get_command_module", return_value=mock_module):
            with patch("rlsbl.detect_registries", return_value=["npm"]):
                with patch("rlsbl.commands.init_cmd.read_project_config", return_value={}):
                    from rlsbl import main
                    main()

        assert os.getcwd() == str(tmp_path)
