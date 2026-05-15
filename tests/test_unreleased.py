"""Tests for rlsbl.commands.unreleased."""

import json
import subprocess

import pytest

from rlsbl.commands.unreleased import (
    _get_commits_since,
    _get_last_tag,
    run_cmd,
)


class TestGetLastTag:
    """Tests for _get_last_tag."""

    def test_returns_tag_when_exists(self, mock_git_repo):
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=str(mock_git_repo), check=True,
        )
        assert _get_last_tag() == "v1.0.0"

    def test_returns_none_when_no_tags(self, mock_git_repo):
        assert _get_last_tag() is None

    def test_returns_latest_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        # Make a new commit and tag it
        (mock_git_repo / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "second"],
            cwd=str(mock_git_repo), check=True,
        )
        subprocess.run(["git", "tag", "v1.1.0"], cwd=str(mock_git_repo), check=True)
        assert _get_last_tag() == "v1.1.0"


class TestGetCommitsSince:
    """Tests for _get_commits_since."""

    def test_returns_commits_since_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        # Add a commit after the tag
        (mock_git_repo / "new.txt").write_text("new")
        subprocess.run(["git", "add", "new.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: add new feature"],
            cwd=str(mock_git_repo), check=True,
        )
        commits = _get_commits_since("v1.0.0")
        assert len(commits) == 1
        assert commits[0]["subject"] == "feat: add new feature"
        assert len(commits[0]["hash"]) == 40
        assert commits[0]["author"] == "Test"
        assert commits[0]["date"]  # non-empty ISO date

    def test_returns_empty_when_no_commits_since_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        commits = _get_commits_since("v1.0.0")
        assert commits == []

    def test_returns_all_commits_when_tag_is_none(self, mock_git_repo):
        # When tag is None, should get HEAD (just one commit in our fixture)
        commits = _get_commits_since(None)
        assert len(commits) == 1
        assert commits[0]["subject"] == "initial"


class TestRunCmd:
    """Tests for the unreleased run_cmd function."""

    def test_no_unreleased_commits(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No unreleased commits." in captured.out

    def test_errors_without_jsonl_setup(self, mock_git_repo, capsys):
        """Without .rlsbl/changes/, exits with error."""
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        (mock_git_repo / "a.txt").write_text("a")
        subprocess.run(["git", "add", "a.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: add widget"],
            cwd=str(mock_git_repo), check=True,
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "JSONL changelog not set up" in captured.err

    def test_json_output_no_commits(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {"json": True})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["tag"] == "v1.0.0"
        assert data["commits"] == []
        assert data["coverage"] == {"covered": 0, "total": 0}
