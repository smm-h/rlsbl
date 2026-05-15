"""Tests for the full run_cmd flow of rlsbl.commands.pre_push_check."""

import json
import subprocess

import pytest

from rlsbl.commands.pre_push_check import (
    _check_jsonl_changelog,
    run_cmd,
)


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


@pytest.fixture
def jsonl_git_repo(tmp_path, monkeypatch):
    """Create a git repo with .rlsbl/changes/ for JSONL changelog testing."""
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

    # Create a baseline version tag
    _run_git(repo, "tag", "v0.0.0")

    # Set up .rlsbl/changes with empty unreleased.jsonl
    changes = repo / ".rlsbl" / "changes"
    changes.mkdir(parents=True)
    (changes / "unreleased.jsonl").write_text("")

    return repo


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


class TestRunCmdWithoutJsonl:
    """run_cmd warns and exits 0 when JSONL changelog is not set up."""

    def test_warns_no_jsonl(self, tmp_project, capsys):
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"})
        )
        (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 0.9.0\n\n- Old stuff\n")

        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "JSONL changelog not set up" in captured.err

    def test_no_changelog_exits_zero(self, tmp_project, capsys):
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


class TestJsonlReleaseCommitSkipping:
    """Release infrastructure commits should be skipped in JSONL coverage checks."""

    def test_version_bump_commit_skipped(self, jsonl_git_repo):
        """A commit with message 'vX.Y.Z' (version bump) passes with empty JSONL."""
        repo = jsonl_git_repo
        # Create a version bump commit (message matches release tag pattern)
        (repo / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
        _run_git(repo, "add", "pyproject.toml")
        _run_git(repo, "commit", "-q", "-m", "v1.0.0")
        sha = _git_head(repo)

        zero = "0" * 40
        refs = [(sha, zero)]  # New branch push
        error = _check_jsonl_changelog(str(repo), refs)
        assert error is None

    def test_finalize_commit_skipped(self, jsonl_git_repo):
        """A commit with 'chore: finalize changelog for ...' passes with empty JSONL."""
        repo = jsonl_git_repo
        changes_dir = repo / ".rlsbl" / "changes"
        (changes_dir / "1.0.0.jsonl").write_text('{"commits":["abc"]}\n')
        _run_git(repo, "add", ".rlsbl/changes/1.0.0.jsonl")
        _run_git(repo, "commit", "-q", "-m", "chore: finalize changelog for 1.0.0")
        sha = _git_head(repo)

        zero = "0" * 40
        refs = [(sha, zero)]
        error = _check_jsonl_changelog(str(repo), refs)
        assert error is None

    def test_release_commits_with_empty_unreleased(self, jsonl_git_repo):
        """Both version bump and finalization commits pass with empty unreleased.jsonl."""
        repo = jsonl_git_repo
        # Version bump commit
        (repo / "package.json").write_text('{"name":"pkg","version":"2.0.0"}\n')
        _run_git(repo, "add", "package.json")
        _run_git(repo, "commit", "-q", "-m", "v2.0.0")

        # Finalization commit
        changes_dir = repo / ".rlsbl" / "changes"
        (changes_dir / "2.0.0.jsonl").write_text('{"commits":["abc"]}\n')
        _run_git(repo, "add", ".rlsbl/changes/2.0.0.jsonl")
        _run_git(repo, "commit", "-q", "-m", "chore: finalize changelog for 2.0.0")
        sha = _git_head(repo)

        zero = "0" * 40
        refs = [(sha, zero)]
        error = _check_jsonl_changelog(str(repo), refs)
        assert error is None

    def test_version_bump_skips_entire_check(self, jsonl_git_repo):
        """A push containing a version bump commit skips the entire check (release push)."""
        repo = jsonl_git_repo
        # Regular code commit (would normally need coverage)
        (repo / "src.py").write_text("x = 1\n")
        _run_git(repo, "add", "src.py")
        _run_git(repo, "commit", "-q", "-m", "feat: add feature")

        # Version bump commit (release -- validation already ran during rlsbl release)
        (repo / "package.json").write_text('{"name":"pkg","version":"1.0.0"}\n')
        _run_git(repo, "add", "package.json")
        _run_git(repo, "commit", "-q", "-m", "v1.0.0")
        sha = _git_head(repo)

        zero = "0" * 40
        refs = [(sha, zero)]
        error = _check_jsonl_changelog(str(repo), refs)
        # Entire check skipped because this is a release push
        assert error is None

    def test_code_commits_with_jsonl_coverage_pass(self, jsonl_git_repo):
        """Code commits with proper JSONL coverage pass alongside release commits."""
        repo = jsonl_git_repo
        # Regular code commit
        (repo / "src.py").write_text("x = 1\n")
        _run_git(repo, "add", "src.py")
        _run_git(repo, "commit", "-q", "-m", "feat: add feature")
        code_sha = _git_head(repo)

        # Add JSONL entry covering the code commit
        changes_dir = repo / ".rlsbl" / "changes"
        entry = json.dumps({"commits": [code_sha], "user_facing": True,
                            "description": "add feature"})
        (changes_dir / "unreleased.jsonl").write_text(entry + "\n")
        _run_git(repo, "add", ".rlsbl/changes/unreleased.jsonl")
        _run_git(repo, "commit", "-q", "-m", "add changelog entry")

        # Version bump commit
        (repo / "package.json").write_text('{"name":"pkg","version":"1.0.0"}\n')
        _run_git(repo, "add", "package.json")
        _run_git(repo, "commit", "-q", "-m", "v1.0.0")
        sha = _git_head(repo)

        zero = "0" * 40
        refs = [(sha, zero)]
        error = _check_jsonl_changelog(str(repo), refs)
        assert error is None
