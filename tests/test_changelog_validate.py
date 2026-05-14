"""Tests for rlsbl.changelog.validate."""

import json
import os
import subprocess
import time

import pytest

from rlsbl.changelog.schema import ChangelogEntry
from rlsbl.changelog.files import append_entry, read_unreleased
from rlsbl.changelog.validate import (
    _is_cache_valid,
    _read_cache,
    _write_cache,
    check_coverage,
    check_hashes_resolve,
    check_in_range,
    check_no_orphans,
    check_schema,
    validate_unreleased,
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
def git_repo(tmp_path, monkeypatch):
    """Create a git repo with an initial commit and a fake origin/main ref."""
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

    # Create a fake origin/main ref pointing to the initial commit
    initial_sha = _git_head(repo)
    refs_dir = repo / ".git" / "refs" / "remotes" / "origin"
    refs_dir.mkdir(parents=True)
    (refs_dir / "main").write_text(initial_sha + "\n")

    # Set up .rlsbl/changes
    changes = repo / ".rlsbl" / "changes"
    changes.mkdir(parents=True)

    return repo


def _make_commit(repo, filename="file.txt", message="change"):
    """Make a commit and return its hash."""
    filepath = repo / filename
    filepath.write_text(f"content-{time.monotonic_ns()}\n")
    _run_git(repo, "add", filename)
    _run_git(repo, "commit", "-q", "-m", message)
    return _git_head(repo)


class TestCheckHashesResolve:
    """Tests for check_hashes_resolve."""

    def test_passes_with_valid_hashes(self, git_repo):
        sha = _make_commit(git_repo)
        entries = [ChangelogEntry(commits=[sha], user_facing=False)]
        passed, details = check_hashes_resolve(entries)
        assert passed is True
        assert details == []

    def test_fails_with_invalid_hash(self, git_repo):
        entries = [ChangelogEntry(commits=["deadbeef" * 5], user_facing=False)]
        passed, details = check_hashes_resolve(entries)
        assert passed is False
        assert len(details) == 1
        assert "does not resolve" in details[0]

    def test_abbreviated_hash(self, git_repo):
        sha = _make_commit(git_repo)
        short = sha[:7]
        entries = [ChangelogEntry(commits=[short], user_facing=False)]
        passed, details = check_hashes_resolve(entries)
        assert passed is True

    def test_empty_entries(self, git_repo):
        passed, details = check_hashes_resolve([])
        assert passed is True
        assert details == []


class TestCheckInRange:
    """Tests for check_in_range."""

    def test_passes_when_hash_in_range(self, git_repo):
        sha = _make_commit(git_repo)
        entries = [ChangelogEntry(commits=[sha], user_facing=False)]
        passed, details = check_in_range(entries)
        assert passed is True
        assert details == []

    def test_fails_when_hash_not_in_range(self, git_repo):
        # The initial commit is origin/main, so it's not in origin/main..HEAD
        initial = _git_head(git_repo)
        _make_commit(git_repo)  # advance HEAD past origin/main
        entries = [ChangelogEntry(commits=[initial], user_facing=False)]
        passed, details = check_in_range(entries)
        assert passed is False
        assert any("not in unreleased range" in d for d in details)


class TestCheckCoverage:
    """Tests for check_coverage."""

    def test_passes_when_all_covered(self, git_repo):
        sha1 = _make_commit(git_repo, "a.txt")
        sha2 = _make_commit(git_repo, "b.txt")
        entries = [
            ChangelogEntry(commits=[sha1], user_facing=False),
            ChangelogEntry(commits=[sha2], user_facing=False),
        ]
        passed, details = check_coverage(entries)
        assert passed is True

    def test_fails_when_commit_not_covered(self, git_repo):
        sha1 = _make_commit(git_repo, "a.txt")
        _make_commit(git_repo, "b.txt")  # not covered
        entries = [ChangelogEntry(commits=[sha1], user_facing=False)]
        passed, details = check_coverage(entries)
        assert passed is False
        assert len(details) == 1
        assert "not covered" in details[0]

    def test_passes_with_no_unreleased_commits(self, git_repo):
        """If HEAD == origin/main, no commits to cover."""
        entries = []
        passed, details = check_coverage(entries)
        assert passed is True

    def test_multi_hash_entry_covers(self, git_repo):
        sha1 = _make_commit(git_repo, "a.txt")
        sha2 = _make_commit(git_repo, "b.txt")
        entries = [ChangelogEntry(commits=[sha1, sha2], user_facing=False)]
        passed, details = check_coverage(entries)
        assert passed is True


class TestCheckNoOrphans:
    """Tests for check_no_orphans."""

    def test_passes_with_valid_entries(self, git_repo):
        sha = _make_commit(git_repo)
        entries = [ChangelogEntry(commits=[sha], user_facing=False)]
        passed, details = check_no_orphans(entries)
        assert passed is True

    def test_fails_with_all_unresolvable(self, git_repo):
        fake = "0" * 40
        entries = [ChangelogEntry(commits=[fake], user_facing=False)]
        passed, details = check_no_orphans(entries)
        assert passed is False
        assert "all hashes unresolvable" in details[0]

    def test_passes_with_partial_resolve(self, git_repo):
        """If at least one hash resolves, entry is not orphaned."""
        sha = _make_commit(git_repo)
        fake = "0" * 40
        entries = [ChangelogEntry(commits=[sha, fake], user_facing=False)]
        passed, details = check_no_orphans(entries)
        assert passed is True

    def test_empty_commits_skipped(self, git_repo):
        entries = [ChangelogEntry(commits=[], user_facing=False)]
        passed, details = check_no_orphans(entries)
        assert passed is True


class TestCheckSchema:
    """Tests for check_schema."""

    def test_passes_valid(self, git_repo):
        entries = [
            ChangelogEntry(commits=["abc"], user_facing=False),
            ChangelogEntry(
                commits=["def"],
                user_facing=True,
                description="Fixed bug",
                type="fix",
            ),
        ]
        passed, details = check_schema(entries)
        assert passed is True

    def test_fails_on_missing_description(self, git_repo):
        entries = [ChangelogEntry(commits=["abc"], user_facing=True, type="fix")]
        passed, details = check_schema(entries)
        assert passed is False
        assert "missing description" in details[0]

    def test_fails_on_empty_commits(self, git_repo):
        entries = [ChangelogEntry(commits=[], user_facing=False)]
        passed, details = check_schema(entries)
        assert passed is False
        assert "commits is empty" in details[0]


class TestValidateUnreleased:
    """Tests for the combined validate_unreleased function."""

    def test_passes_fully_covered(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        sha = _make_commit(git_repo)
        append_entry(changes, ChangelogEntry(commits=[sha], user_facing=False))

        result = validate_unreleased(changes)
        assert result["passed"] is True
        for key in ("hashes_resolve", "in_range", "coverage", "no_orphans", "schema"):
            passed, _ = result[key]
            assert passed is True

    def test_fails_on_missing_coverage(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _make_commit(git_repo)  # unreleased commit with no entry

        result = validate_unreleased(changes)
        assert result["passed"] is False
        passed, details = result["coverage"]
        assert passed is False
        assert len(details) == 1

    def test_empty_unreleased_no_commits(self, git_repo):
        """No unreleased commits and no entries: passes."""
        changes = str(git_repo / ".rlsbl" / "changes")
        result = validate_unreleased(changes)
        assert result["passed"] is True


class TestValidationCache:
    """Tests for validation cache helpers."""

    def test_read_cache_missing(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        assert _read_cache(changes) is None

    def test_write_and_read_cache(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _write_cache(changes)
        cached = _read_cache(changes)
        assert cached is not None
        assert len(cached) == 40

    def test_cache_valid_after_write(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _write_cache(changes)
        assert _is_cache_valid(changes) is True

    def test_cache_invalid_after_unreleased_change(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _write_cache(changes)

        # Touch unreleased.jsonl to make it newer than the cache
        unreleased = os.path.join(changes, "unreleased.jsonl")
        # Need a small delay so mtime differs
        time.sleep(0.05)
        with open(unreleased, "w") as f:
            f.write(json.dumps({"commits": ["abc"], "user_facing": False}) + "\n")

        assert _is_cache_valid(changes) is False

    def test_cache_stays_valid_with_new_commits(self, git_repo):
        """Cache is still valid if HEAD moved forward (ancestor relationship)."""
        changes = str(git_repo / ".rlsbl" / "changes")
        _write_cache(changes)
        _make_commit(git_repo)
        # HEAD moved forward, but cached SHA is an ancestor of new HEAD
        assert _is_cache_valid(changes) is True

    def test_validate_writes_cache_on_success(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        assert _read_cache(changes) is None

        result = validate_unreleased(changes)
        assert result["passed"] is True
        assert _read_cache(changes) is not None

    def test_validate_skips_cache_write_on_failure(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _make_commit(git_repo)  # uncovered commit

        result = validate_unreleased(changes)
        assert result["passed"] is False
        assert _read_cache(changes) is None
