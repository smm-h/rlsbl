"""Tests for the changelog add/validate/generate subcommands."""

import json
import os
import subprocess
import time
from unittest import mock

import pytest

from rlsbl.changelog.files import (
    append_entry,
    get_changes_dir,
    read_unreleased,
)
from rlsbl.changelog.schema import ChangelogEntry
from rlsbl.commands.changelog_cmd import cmd_add, cmd_generate, cmd_validate


def _run_git(repo, *args):
    """Run a git command in the given repo directory."""
    subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def _git_head(repo):
    """Get HEAD hash."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_commit(repo, filename="file.txt", message="change"):
    """Make a commit and return its hash."""
    filepath = repo / filename
    filepath.write_text(f"content-{time.monotonic_ns()}\n")
    _run_git(repo, "add", filename)
    _run_git(repo, "commit", "-q", "-m", message)
    return _git_head(repo)


@pytest.fixture
def rlsbl_repo(tmp_path, monkeypatch):
    """Create a git repo with .rlsbl/ scaffolding and a fake origin/main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@test.local")
    _run_git(repo, "config", "user.name", "Test")

    # Initial commit
    (repo / "README.md").write_text("# test\n")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-q", "-m", "initial")

    # Fake origin/main ref
    initial_sha = _git_head(repo)
    refs_dir = repo / ".git" / "refs" / "remotes" / "origin"
    refs_dir.mkdir(parents=True)
    (refs_dir / "main").write_text(initial_sha + "\n")

    # Set up .rlsbl/changes
    changes = repo / ".rlsbl" / "changes"
    changes.mkdir(parents=True)

    return repo


# ---------------------------------------------------------------------------
# cmd_add tests
# ---------------------------------------------------------------------------


class TestCmdAdd:
    """Tests for cmd_add."""

    def test_valid_entry(self, rlsbl_repo):
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha[:12],
            "description": "New feature",
            "type": "feature",
            "no-user-facing": False,
        }
        cmd_add(flags)

        entries = read_unreleased(get_changes_dir("."))
        assert len(entries) == 1
        assert entries[0].user_facing is True
        assert entries[0].description == "New feature"
        assert entries[0].type == "feature"
        # Should be resolved to full 40-char hash
        assert len(entries[0].commits[0]) == 40

    def test_non_user_facing(self, rlsbl_repo):
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha,
            "description": "",
            "type": "",
            "no-user-facing": True,
        }
        cmd_add(flags)

        entries = read_unreleased(get_changes_dir("."))
        assert len(entries) == 1
        assert entries[0].user_facing is False
        assert entries[0].description is None
        assert entries[0].type is None

    def test_invalid_commit_hash(self, rlsbl_repo):
        flags = {
            "commits": "deadbeefdeadbeef",
            "description": "Stuff",
            "type": "fix",
            "no-user-facing": False,
        }
        with pytest.raises(SystemExit) as exc_info:
            cmd_add(flags)
        assert exc_info.value.code == 1

    def test_missing_commits(self, rlsbl_repo):
        flags = {
            "commits": "",
            "description": "Stuff",
            "type": "fix",
            "no-user-facing": False,
        }
        with pytest.raises(SystemExit) as exc_info:
            cmd_add(flags)
        assert exc_info.value.code == 1

    def test_missing_description_for_user_facing(self, rlsbl_repo):
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha,
            "description": "",
            "type": "fix",
            "no-user-facing": False,
        }
        with pytest.raises(SystemExit) as exc_info:
            cmd_add(flags)
        assert exc_info.value.code == 1

    def test_multiple_commits(self, rlsbl_repo):
        sha1 = _make_commit(rlsbl_repo, "a.txt")
        sha2 = _make_commit(rlsbl_repo, "b.txt")
        flags = {
            "commits": f"{sha1[:8]},{sha2[:8]}",
            "description": "Multi-commit change",
            "type": "feature",
            "no-user-facing": False,
        }
        cmd_add(flags)

        entries = read_unreleased(get_changes_dir("."))
        assert len(entries) == 1
        assert len(entries[0].commits) == 2

    def test_add_auto_commits(self, rlsbl_repo):
        """After adding an entry, commit_files is called with correct args."""
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha[:12],
            "description": "New feature",
            "type": "feature",
            "no-user-facing": False,
        }
        with mock.patch("rlsbl.commands.changelog_cmd.commit_files") as mock_commit:
            cmd_add(flags)
            mock_commit.assert_called_once()
            call_args = mock_commit.call_args
            assert call_args[0][0] == "changelog: New feature"
            unreleased_path = os.path.join(get_changes_dir("."), "unreleased.jsonl")
            assert call_args[0][1] == [unreleased_path]
            assert call_args[1]["allow_failure"] is True

    def test_add_no_commit_flag(self, rlsbl_repo):
        """With --no-commit, commit_files is NOT called."""
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha[:12],
            "description": "New feature",
            "type": "feature",
            "no-user-facing": False,
            "no-commit": True,
        }
        with mock.patch("rlsbl.commands.changelog_cmd.commit_files") as mock_commit:
            cmd_add(flags)
            mock_commit.assert_not_called()

    def test_add_non_user_facing_commit_message(self, rlsbl_repo):
        """Non-user-facing entries use a generic commit message."""
        sha = _make_commit(rlsbl_repo)
        flags = {
            "commits": sha,
            "description": "",
            "type": "",
            "no-user-facing": True,
        }
        with mock.patch("rlsbl.commands.changelog_cmd.commit_files") as mock_commit:
            cmd_add(flags)
            mock_commit.assert_called_once()
            assert mock_commit.call_args[0][0] == "changelog: non-user-facing entry"


# ---------------------------------------------------------------------------
# cmd_validate tests
# ---------------------------------------------------------------------------


class TestCmdValidate:
    """Tests for cmd_validate."""

    def test_all_pass(self, rlsbl_repo):
        sha = _make_commit(rlsbl_repo)
        changes_dir = get_changes_dir(".")
        append_entry(changes_dir, ChangelogEntry(commits=[sha], user_facing=False))

        # Should exit 0 (no exception)
        cmd_validate({})

    def test_failures(self, rlsbl_repo):
        # Make an unreleased commit with no changelog entry -> coverage fail
        _make_commit(rlsbl_repo)

        with pytest.raises(SystemExit) as exc_info:
            cmd_validate({})
        assert exc_info.value.code == 1

    def test_no_changes_dir(self, tmp_path, monkeypatch):
        """Error when .rlsbl/changes/ does not exist."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cmd_validate({})
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_generate tests
# ---------------------------------------------------------------------------


class TestCmdGenerate:
    """Tests for cmd_generate."""

    def test_produces_files(self, rlsbl_repo):
        sha = _make_commit(rlsbl_repo)
        changes_dir = get_changes_dir(".")
        append_entry(
            changes_dir,
            ChangelogEntry(
                commits=[sha],
                user_facing=True,
                description="Added feature X",
                type="feature",
            ),
        )

        cmd_generate({"dry-run": False})

        changelog_path = rlsbl_repo / "CHANGELOG.md"
        assert changelog_path.exists()
        content = changelog_path.read_text()
        assert "Added feature X" in content

    def test_dry_run(self, rlsbl_repo, capsys):
        sha = _make_commit(rlsbl_repo)
        changes_dir = get_changes_dir(".")
        append_entry(
            changes_dir,
            ChangelogEntry(
                commits=[sha],
                user_facing=True,
                description="Feature Y",
                type="feature",
            ),
        )

        cmd_generate({"dry-run": True})

        # Dry-run should NOT write CHANGELOG.md
        changelog_path = rlsbl_repo / "CHANGELOG.md"
        assert not changelog_path.exists()

        # But the preview should be printed
        captured = capsys.readouterr()
        assert "Feature Y" in captured.out
        assert "dry-run" in captured.out

    def test_no_changes_dir(self, tmp_path, monkeypatch):
        """Error when .rlsbl/changes/ does not exist."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cmd_generate({"dry-run": False})
        assert exc_info.value.code == 1
