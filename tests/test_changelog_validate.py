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
    _is_changelog_only_commit,
    _is_release_commit,
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
            passed, _ = result["checks"][key]
            assert passed is True

    def test_fails_on_missing_coverage(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _make_commit(git_repo)  # unreleased commit with no entry

        result = validate_unreleased(changes)
        assert result["passed"] is False
        passed, details = result["checks"]["coverage"]
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


class TestValidateUnreleasedReturnStructure:
    """Tests for the validate_unreleased return dict structure."""

    def test_has_passed_and_checks_keys(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        result = validate_unreleased(changes)
        assert "passed" in result
        assert "checks" in result
        assert isinstance(result["passed"], bool)
        assert isinstance(result["checks"], dict)

    def test_checks_values_are_tuples(self, git_repo):
        changes = str(git_repo / ".rlsbl" / "changes")
        _make_commit(git_repo)  # create an unreleased commit
        append_entry(changes, ChangelogEntry(
            commits=[_git_head(git_repo)], user_facing=False,
        ))
        result = validate_unreleased(changes)
        for name, value in result["checks"].items():
            assert isinstance(value, tuple), f"check {name} is not a tuple"
            assert len(value) == 2, f"check {name} tuple length is not 2"
            passed, details = value
            assert isinstance(passed, bool), f"check {name} passed is not bool"
            assert isinstance(details, list), f"check {name} details is not list"


class TestIsChangelogOnlyCommit:
    """Unit tests for _is_changelog_only_commit."""

    def test_changelog_only_files(self, git_repo):
        """Commit touching only .rlsbl/changes/ files is changelog-only."""
        changes_dir = git_repo / ".rlsbl" / "changes"
        unreleased = changes_dir / "unreleased.jsonl"
        unreleased.write_text('{"commits":["abc"],"user_facing":false}\n')
        _run_git(git_repo, "add", ".rlsbl/changes/unreleased.jsonl")
        _run_git(git_repo, "commit", "-q", "-m", "update changelog")
        sha = _git_head(git_repo)
        assert _is_changelog_only_commit(sha) is True

    def test_changelog_md_only(self, git_repo):
        """Commit touching only CHANGELOG.md is changelog-only."""
        (git_repo / "CHANGELOG.md").write_text("## 1.0.0\n- stuff\n")
        _run_git(git_repo, "add", "CHANGELOG.md")
        _run_git(git_repo, "commit", "-q", "-m", "update CHANGELOG.md")
        sha = _git_head(git_repo)
        assert _is_changelog_only_commit(sha) is True

    def test_mixed_commit_not_changelog_only(self, git_repo):
        """Commit touching both code and changelog files is NOT changelog-only."""
        changes_dir = git_repo / ".rlsbl" / "changes"
        unreleased = changes_dir / "unreleased.jsonl"
        unreleased.write_text('{"commits":["abc"],"user_facing":false}\n')
        (git_repo / "code.py").write_text("x = 1\n")
        _run_git(git_repo, "add", ".rlsbl/changes/unreleased.jsonl")
        _run_git(git_repo, "add", "code.py")
        _run_git(git_repo, "commit", "-q", "-m", "mixed commit")
        sha = _git_head(git_repo)
        assert _is_changelog_only_commit(sha) is False

    def test_code_only_commit(self, git_repo):
        """Commit touching only code files is NOT changelog-only."""
        sha = _make_commit(git_repo, "src.py", "code change")
        assert _is_changelog_only_commit(sha) is False

    def test_invalid_sha_returns_false(self, git_repo):
        """Invalid SHA returns False (don't skip what we can't determine)."""
        assert _is_changelog_only_commit("0" * 40) is False

    def test_validated_file_is_changelog_only(self, git_repo):
        """Commit touching .rlsbl/changes/.validated is changelog-only."""
        validated = git_repo / ".rlsbl" / "changes" / ".validated"
        validated.write_text("abc123\n")
        _run_git(git_repo, "add", ".rlsbl/changes/.validated")
        _run_git(git_repo, "commit", "-q", "-m", "update validated cache")
        sha = _git_head(git_repo)
        assert _is_changelog_only_commit(sha) is True


class TestChangelogOnlyCoverage:
    """Integration tests: changelog-only commits are skipped in coverage."""

    def test_changelog_only_commit_skipped_in_coverage(self, git_repo):
        """A changelog-only commit should not require an entry."""
        # Make a code commit and cover it
        sha1 = _make_commit(git_repo, "code.py", "code change")
        entries = [ChangelogEntry(commits=[sha1], user_facing=False)]

        # Make a changelog-only commit (not covered by any entry)
        changes_dir = git_repo / ".rlsbl" / "changes"
        unreleased = changes_dir / "unreleased.jsonl"
        unreleased.write_text('{"commits":["abc"],"user_facing":false}\n')
        _run_git(git_repo, "add", ".rlsbl/changes/unreleased.jsonl")
        _run_git(git_repo, "commit", "-q", "-m", "update unreleased entries")

        passed, details = check_coverage(entries)
        assert passed is True
        assert any("skipped 1 changelog-only" in d for d in details)

    def test_mixed_commit_not_skipped_in_coverage(self, git_repo):
        """A commit touching both code and changelog files must be covered."""
        sha1 = _make_commit(git_repo, "a.py", "first change")

        # Mixed commit: code + changelog
        changes_dir = git_repo / ".rlsbl" / "changes"
        unreleased = changes_dir / "unreleased.jsonl"
        unreleased.write_text('{"commits":["abc"],"user_facing":false}\n')
        (git_repo / "b.py").write_text("y = 2\n")
        _run_git(git_repo, "add", ".rlsbl/changes/unreleased.jsonl")
        _run_git(git_repo, "add", "b.py")
        _run_git(git_repo, "commit", "-q", "-m", "mixed commit")

        entries = [ChangelogEntry(commits=[sha1], user_facing=False)]
        passed, details = check_coverage(entries)
        assert passed is False
        assert any("not covered" in d for d in details)

    def test_changelog_md_only_commit_skipped(self, git_repo):
        """A CHANGELOG.md-only commit should be skipped."""
        sha1 = _make_commit(git_repo, "code.py", "code change")
        entries = [ChangelogEntry(commits=[sha1], user_facing=False)]

        # CHANGELOG.md-only commit
        (git_repo / "CHANGELOG.md").write_text("## 1.0.0\n- stuff\n")
        _run_git(git_repo, "add", "CHANGELOG.md")
        _run_git(git_repo, "commit", "-q", "-m", "update CHANGELOG.md")

        passed, details = check_coverage(entries)
        assert passed is True
        assert any("skipped 1 changelog-only" in d for d in details)

    def test_validate_unreleased_skips_changelog_commit(self, git_repo):
        """Full validate_unreleased should pass with a changelog-only commit."""
        changes = str(git_repo / ".rlsbl" / "changes")
        sha = _make_commit(git_repo, "code.py", "code change")
        append_entry(changes, ChangelogEntry(commits=[sha], user_facing=False))

        # Make a changelog-only commit
        (git_repo / "CHANGELOG.md").write_text("## 1.0.0\n- stuff\n")
        _run_git(git_repo, "add", "CHANGELOG.md")
        _run_git(git_repo, "commit", "-q", "-m", "update CHANGELOG.md")

        result = validate_unreleased(changes)
        assert result["passed"] is True


class TestIsReleaseCommit:
    """Unit tests for _is_release_commit."""

    def test_changelog_only_commit_is_release(self, git_repo):
        """A changelog-only commit is a release commit."""
        (git_repo / "CHANGELOG.md").write_text("## 1.0.0\n- stuff\n")
        _run_git(git_repo, "add", "CHANGELOG.md")
        _run_git(git_repo, "commit", "-q", "-m", "update CHANGELOG.md")
        sha = _git_head(git_repo)
        assert _is_release_commit(sha) is True

    def test_version_tag_message_is_release(self, git_repo):
        """A commit with message matching vX.Y.Z is a release commit."""
        sha = _make_commit(git_repo, "pyproject.toml", "v1.2.3")
        assert _is_release_commit(sha) is True

    def test_finalize_message_is_release(self, git_repo):
        """A commit with 'chore: finalize changelog for ...' is a release commit."""
        sha = _make_commit(git_repo, "changes.jsonl", "chore: finalize changelog for 1.2.3")
        assert _is_release_commit(sha) is True

    def test_regular_commit_is_not_release(self, git_repo):
        """A regular code commit is not a release commit."""
        sha = _make_commit(git_repo, "src.py", "fix: some bug")
        assert _is_release_commit(sha) is False

    def test_version_like_but_wrong_format(self, git_repo):
        """A commit with a version-like but incorrect message is not release."""
        sha = _make_commit(git_repo, "file.txt", "v1.2")
        assert _is_release_commit(sha) is False

    def test_invalid_sha_returns_false(self, git_repo):
        """Invalid SHA returns False."""
        assert _is_release_commit("0" * 40) is False

    def test_rlsbl_version_file_is_changelog_only(self, git_repo):
        """A commit touching only .rlsbl/version is changelog-only (release infra)."""
        version_dir = git_repo / ".rlsbl"
        version_dir.mkdir(exist_ok=True)
        (version_dir / "version").write_text("0.25.0\n")
        _run_git(git_repo, "add", ".rlsbl/version")
        _run_git(git_repo, "commit", "-q", "-m", "update rlsbl version")
        sha = _git_head(git_repo)
        assert _is_changelog_only_commit(sha) is True
        assert _is_release_commit(sha) is True
