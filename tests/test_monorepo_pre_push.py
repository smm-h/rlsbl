"""Tests for monorepo-aware pre-push changelog check."""

import json
import os
import subprocess
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

from rlsbl.commands.pre_push_check import (
    run_cmd,
    _detect_version,
    _check_changelog,
    _parse_stdin_refs,
    _get_changed_files,
    _file_matches_project,
    _affected_projects,
    _run_monorepo_check,
)
from rlsbl.workspace import WORKSPACE_DIR, WORKSPACE_FILE


# -- Helpers ------------------------------------------------------------------


def _make_workspace(root, projects):
    """Create a .rlsbl-monorepo/workspace.toml with the given project list."""
    ws_dir = root / WORKSPACE_DIR
    ws_dir.mkdir(exist_ok=True)
    lines = []
    for proj in projects:
        lines.append("[[projects]]")
        lines.append(f'path = "{proj["path"]}"')
        lines.append(f'name = "{proj["name"]}"')
        if "watch" in proj:
            watch_items = ", ".join(f'"{w}"' for w in proj["watch"])
            lines.append(f"watch = [{watch_items}]")
        lines.append("")
    (ws_dir / WORKSPACE_FILE).write_text("\n".join(lines))


def _make_npm_project(root, subdir, version="1.0.0", changelog_version=None):
    """Create a minimal npm project with package.json and CHANGELOG.md."""
    proj_dir = root / subdir
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "package.json").write_text(
        json.dumps({"name": f"test-{subdir}", "version": version})
    )
    if changelog_version is not None:
        (proj_dir / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## {changelog_version}\n\n- Changes\n"
        )


def _stdin_line(local_sha="abc1234", remote_sha="def5678"):
    """Build a single pre-push stdin line."""
    return f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"


# -- Unit tests for helpers ---------------------------------------------------


class TestFileMatchesProject:
    def test_file_inside_project_path(self):
        proj = {"path": "pkg-a", "name": "pkg-a"}
        assert _file_matches_project("pkg-a/src/main.js", proj)

    def test_file_is_project_root(self):
        proj = {"path": "pkg-a", "name": "pkg-a"}
        assert _file_matches_project("pkg-a", proj)

    def test_file_outside_project(self):
        proj = {"path": "pkg-a", "name": "pkg-a"}
        assert not _file_matches_project("pkg-b/src/main.js", proj)

    def test_file_with_similar_prefix(self):
        """pkg-ab should not match pkg-a (no partial prefix match)."""
        proj = {"path": "pkg-a", "name": "pkg-a"}
        assert not _file_matches_project("pkg-ab/src/main.js", proj)

    def test_watch_glob_match(self):
        proj = {"path": "pkg-a", "name": "pkg-a", "watch": ["shared/**"]}
        assert _file_matches_project("shared/utils.js", proj)

    def test_watch_exact_file_match(self):
        proj = {"path": "pkg-a", "name": "pkg-a", "watch": ["Package.swift"]}
        assert _file_matches_project("Package.swift", proj)

    def test_watch_no_match(self):
        proj = {"path": "pkg-a", "name": "pkg-a", "watch": ["shared/**"]}
        assert not _file_matches_project("other/file.js", proj)


class TestAffectedProjects:
    def test_single_project_affected(self):
        projects = [
            {"path": "pkg-a", "name": "a"},
            {"path": "pkg-b", "name": "b"},
        ]
        changed = {"pkg-a/src/main.js"}
        result = _affected_projects(changed, projects)
        assert len(result) == 1
        assert result[0]["name"] == "a"

    def test_both_projects_affected(self):
        projects = [
            {"path": "pkg-a", "name": "a"},
            {"path": "pkg-b", "name": "b"},
        ]
        changed = {"pkg-a/src/main.js", "pkg-b/lib/index.js"}
        result = _affected_projects(changed, projects)
        assert len(result) == 2
        names = {p["name"] for p in result}
        assert names == {"a", "b"}

    def test_no_projects_affected(self):
        projects = [
            {"path": "pkg-a", "name": "a"},
            {"path": "pkg-b", "name": "b"},
        ]
        changed = {"README.md", "docs/guide.md"}
        result = _affected_projects(changed, projects)
        assert result == []

    def test_watch_triggers_affected(self):
        projects = [
            {"path": "pkg-a", "name": "a", "watch": ["shared/**"]},
        ]
        changed = {"shared/utils.js"}
        result = _affected_projects(changed, projects)
        assert len(result) == 1
        assert result[0]["name"] == "a"


class TestParseStdinRefs:
    def test_normal_input(self):
        stdin_data = "refs/heads/main abc123 refs/heads/main def456\n"
        with patch("sys.stdin", StringIO(stdin_data)):
            with patch("sys.stdin.isatty", return_value=False):
                refs = _parse_stdin_refs()
        assert refs == [("abc123", "def456")]

    def test_multiple_refs(self):
        stdin_data = (
            "refs/heads/main abc123 refs/heads/main def456\n"
            "refs/heads/feat xyz789 refs/heads/feat 000111\n"
        )
        with patch("sys.stdin", StringIO(stdin_data)):
            with patch("sys.stdin.isatty", return_value=False):
                refs = _parse_stdin_refs()
        assert len(refs) == 2

    def test_empty_stdin(self):
        with patch("sys.stdin", StringIO("")):
            with patch("sys.stdin.isatty", return_value=False):
                refs = _parse_stdin_refs()
        assert refs is None

    def test_tty_stdin(self):
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with patch("sys.stdin", mock_stdin):
            refs = _parse_stdin_refs()
        assert refs is None


class TestCheckChangelog:
    def test_changelog_exists_with_version(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- Stuff\n")
        assert _check_changelog(str(tmp_path), "1.0.0") is None

    def test_changelog_exists_without_version(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.9.0\n\n- Stuff\n")
        error = _check_changelog(str(tmp_path), "1.0.0")
        assert error is not None
        assert "1.0.0" in error

    def test_no_changelog(self, tmp_path):
        # No CHANGELOG.md -- skip silently
        assert _check_changelog(str(tmp_path), "1.0.0") is None


# -- Integration tests for run_cmd (single-project, no monorepo) -------------


class TestSingleProjectUnchanged:
    """Existing single-project behavior is preserved."""

    def test_exits_zero_with_matching_changelog(self, tmp_project):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- Initial\n")
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0

    def test_exits_one_with_missing_changelog_entry(self, tmp_project, capsys):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 0.9.0\n\n- Old\n")
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "1.0.0" in captured.err

    def test_exits_zero_with_no_changelog(self, tmp_project):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0

    def test_exits_zero_with_no_project(self, tmp_project):
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0


# -- Integration tests for monorepo pre-push ---------------------------------


class TestMonorepoPrePush:
    """Test monorepo-aware pre-push changelog checking."""

    def _setup_monorepo(self, root, projects_config):
        """Set up workspace + project directories.

        projects_config: list of dicts with keys:
            name, path, version, changelog_version (None to skip changelog),
            watch (optional list of globs)
        """
        ws_projects = []
        for pc in projects_config:
            ws_entry = {"path": pc["path"], "name": pc["name"]}
            if "watch" in pc:
                ws_entry["watch"] = pc["watch"]
            ws_projects.append(ws_entry)

            _make_npm_project(
                root, pc["path"],
                version=pc.get("version", "1.0.0"),
                changelog_version=pc.get("changelog_version"),
            )
        _make_workspace(root, ws_projects)

    def test_touching_project_a_checks_a(self, tmp_project, capsys):
        """Push touching project A checks A's changelog."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
            {"name": "b", "path": "pkg-b", "version": "2.0.0", "changelog_version": "2.0.0"},
        ])

        changed_files = {"pkg-a/src/main.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 0

    def test_touching_a_and_b_checks_both(self, tmp_project, capsys):
        """Push touching A and B checks both changelogs."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
            {"name": "b", "path": "pkg-b", "version": "2.0.0", "changelog_version": "2.0.0"},
        ])

        changed_files = {"pkg-a/src/main.js", "pkg-b/lib/index.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 0

    def test_touching_a_does_not_check_b(self, tmp_project, capsys):
        """Push touching only A does NOT check B's changelog (even if B's is wrong)."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
            {"name": "b", "path": "pkg-b", "version": "2.0.0", "changelog_version": "0.0.1"},
        ])

        changed_files = {"pkg-a/src/main.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            # Should pass because B is not checked
            assert exc_info.value.code == 0

    def test_missing_changelog_skipped(self, tmp_project, capsys):
        """Project with no changelog is skipped silently."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": None},
        ])

        changed_files = {"pkg-a/src/main.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 0

    def test_all_changelogs_valid_exits_zero(self, tmp_project, capsys):
        """All affected projects have valid changelogs -- exit 0."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
            {"name": "b", "path": "pkg-b", "version": "2.0.0", "changelog_version": "2.0.0"},
            {"name": "c", "path": "pkg-c", "version": "3.0.0", "changelog_version": "3.0.0"},
        ])

        changed_files = {"pkg-a/x.js", "pkg-b/y.js", "pkg-c/z.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 0

    def test_one_changelog_missing_exits_one(self, tmp_project, capsys):
        """One project has wrong changelog version -- exit 1 with project name."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
            {"name": "b", "path": "pkg-b", "version": "2.0.0", "changelog_version": "0.0.1"},
        ])

        changed_files = {"pkg-a/x.js", "pkg-b/y.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "b" in captured.err
            assert "2.0.0" in captured.err

    def test_no_stdin_falls_back_to_single_project(self, tmp_project, capsys):
        """When stdin is empty (e.g., called directly), falls back to single-project."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "1.0.0"},
        ])
        # Also put a top-level package.json so single-project logic finds it
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "mono-root", "version": "0.1.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n\n- Root\n")

        # Simulate tty stdin (no hook data)
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with patch("sys.stdin", mock_stdin):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            assert exc_info.value.code == 0

    def test_watch_glob_triggers_check(self, tmp_project, capsys):
        """A change in a watched path triggers the project's changelog check."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0",
             "changelog_version": "0.0.1", "watch": ["shared/**"]},
        ])
        # Also create the watched directory
        (tmp_project / "shared").mkdir()
        (tmp_project / "shared" / "utils.js").write_text("// shared")

        changed_files = {"shared/utils.js"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            # Should fail because the changelog has 0.0.1 not 1.0.0
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "a" in captured.err
            assert "1.0.0" in captured.err

    def test_files_not_in_any_project_ignored(self, tmp_project, capsys):
        """Files outside all project paths are ignored."""
        self._setup_monorepo(tmp_project, [
            {"name": "a", "path": "pkg-a", "version": "1.0.0", "changelog_version": "0.0.1"},
        ])

        # Only root-level files changed, not in any project
        changed_files = {"README.md", "docs/guide.md"}
        stdin_data = _stdin_line()

        with patch("sys.stdin", StringIO(stdin_data)), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("rlsbl.commands.pre_push_check._get_changed_files",
                   return_value=changed_files):
            with pytest.raises(SystemExit) as exc_info:
                run_cmd(None, [], {})
            # No projects affected, so exit 0
            assert exc_info.value.code == 0
