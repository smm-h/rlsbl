"""Tests for the full run_cmd flow of rlsbl.commands.pre_push_check."""

import json

import pytest

from rlsbl.commands.pre_push_check import run_cmd


class TestRunCmdEntryExists:
    """run_cmd exits 0 when CHANGELOG.md has a matching version heading."""

    def test_exits_zero(self, tmp_project):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- Initial release\n")

        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})

        assert exc_info.value.code == 0


class TestRunCmdEntryMissing:
    """run_cmd exits 1 with error when CHANGELOG.md lacks a version heading."""

    def test_exits_one_with_error(self, tmp_project, capsys):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 0.9.0\n\n- Old stuff\n")

        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "1.0.0" in captured.err
        assert "CHANGELOG.md" in captured.err


class TestRunCmdNoChangelog:
    """run_cmd exits 0 silently when no CHANGELOG.md exists."""

    def test_exits_zero(self, tmp_project):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )

        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})

        assert exc_info.value.code == 0


class TestRunCmdNoProjectFiles:
    """run_cmd exits 0 silently when no project files exist."""

    def test_exits_zero(self, tmp_project):
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})

        assert exc_info.value.code == 0
