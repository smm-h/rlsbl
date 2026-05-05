"""Tests for scope-aware release flow (subdir targets like codehome)."""

import os
from io import StringIO
from unittest.mock import patch

from rlsbl.commands.release import run_cmd


class TestScopedReleaseDryRun:
    """Verify scoped release dry-run reads the correct version and plans the right tag."""

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_scoped_dry_run_reads_version_from_scope_dir(
        self, _gh_inst, _gh_auth, _branch, _clean, mock_run, tmp_path, monkeypatch
    ):
        """Scoped release reads plugin.toml from the scope path and plans a namespaced tag."""
        monkeypatch.chdir(tmp_path)

        # Create plugin directory with plugin.toml
        plugin_dir = tmp_path / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.toml").write_text(
            '[plugin]\nname = "test-plugin"\nversion = "0.1.0"\n'
        )

        # Create CHANGELOG.md in the scope directory (first release uses current version)
        (plugin_dir / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.0\n\n- Initial release of test-plugin\n"
        )

        # mock_run is called for git tag -l checks; return empty (no existing tags)
        mock_run.return_value = ""

        # Capture stdout to verify dry-run output
        output = StringIO()
        with patch("sys.stdout", output):
            run_cmd(
                "codehome",
                ["patch"],
                {
                    "scope": "plugins/test-plugin",
                    "dry-run": True,
                    "yes": True,
                },
            )

        printed = output.getvalue()

        # Should read version 0.1.0 from plugins/test-plugin/plugin.toml
        assert "Current version: 0.1.0" in printed
        # First release (tag doesn't exist), so it releases as-is
        assert "test-plugin@v0.1.0" in printed

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_scoped_dry_run_bumps_version_when_tag_exists(
        self, _gh_inst, _gh_auth, _branch, _clean, mock_run, tmp_path, monkeypatch
    ):
        """When the current tag exists, scoped release bumps and plans the new tag."""
        monkeypatch.chdir(tmp_path)

        # Create plugin directory with plugin.toml
        plugin_dir = tmp_path / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.toml").write_text(
            '[plugin]\nname = "test-plugin"\nversion = "0.1.0"\n'
        )

        # Create CHANGELOG.md with the bumped version entry
        (plugin_dir / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.1\n\n- Fixed a bug in hook registration\n"
        )

        # First call: git tag -l test-plugin@v0.1.0 -> exists
        # Second call: git tag -l test-plugin@v0.1.1 -> doesn't exist
        mock_run.side_effect = ["test-plugin@v0.1.0", ""]

        output = StringIO()
        with patch("sys.stdout", output):
            run_cmd(
                "codehome",
                ["patch"],
                {
                    "scope": "plugins/test-plugin",
                    "dry-run": True,
                    "yes": True,
                },
            )

        printed = output.getvalue()

        # Should show bump from 0.1.0 to 0.1.1
        assert "0.1.0" in printed
        assert "0.1.1" in printed
        assert "test-plugin@v0.1.1" in printed
        assert "Scope:" in printed
        assert "plugins/test-plugin" in printed

    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_scoped_changelog_falls_back_to_root(
        self, _gh_inst, _gh_auth, _branch, _clean, mock_run, tmp_path, monkeypatch
    ):
        """When no CHANGELOG.md in scope dir, falls back to root CHANGELOG.md."""
        monkeypatch.chdir(tmp_path)

        # Create plugin directory with plugin.toml but NO CHANGELOG.md
        plugin_dir = tmp_path / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.toml").write_text(
            '[plugin]\nname = "test-plugin"\nversion = "0.1.0"\n'
        )

        # Create root CHANGELOG.md
        (tmp_path / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.0\n\n- Initial release of test-plugin\n"
        )

        # No existing tags
        mock_run.return_value = ""

        output = StringIO()
        with patch("sys.stdout", output):
            run_cmd(
                "codehome",
                [],
                {
                    "scope": "plugins/test-plugin",
                    "dry-run": True,
                    "yes": True,
                },
            )

        printed = output.getvalue()
        # Should succeed using root changelog
        assert "test-plugin@v0.1.0" in printed

    def test_batch_scope_exits_with_message(self, tmp_path, monkeypatch, capsys):
        """A trailing-slash scope (batch mode) prints an error and exits."""
        monkeypatch.chdir(tmp_path)

        # Create the plugins directory (no plugin.toml directly in it)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        import pytest

        with patch("rlsbl.commands.release.check_gh_installed", return_value=True), \
             patch("rlsbl.commands.release.check_gh_auth", return_value=True), \
             patch("rlsbl.commands.release.is_clean_tree", return_value=True), \
             patch("rlsbl.commands.release.get_current_branch", return_value="main"):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(
                    "codehome",
                    ["patch"],
                    {
                        "scope": "plugins/",
                        "dry-run": True,
                        "yes": True,
                    },
                )
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Batch release not yet implemented" in captured.err
