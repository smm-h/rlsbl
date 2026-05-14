"""Validation engine for JSONL changelog entries with caching."""

from __future__ import annotations

import os
import subprocess

from .files import read_unreleased
from .resolve import resolve_hash, resolve_hashes
from .schema import ChangelogEntry, validate_schema


def _git_log_hashes(range_spec: str) -> list[str]:
    """Get commit hashes from git log for a given range spec.

    Returns a list of full 40-char SHAs, or empty list on error.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H", range_spec],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _git_head() -> str | None:
    """Get the current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        sha = result.stdout.strip()
        return sha if len(sha) == 40 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


_CHANGELOG_PATTERNS = (
    ".rlsbl/changes/",
    "CHANGELOG.md",
)


def _is_changelog_only_commit(sha: str) -> bool:
    """Check if a commit only touches changelog-maintenance files.

    Returns True if every file in the commit matches a changelog pattern
    (files under .rlsbl/changes/ or CHANGELOG.md). Merge commits with no
    files are treated as structural and return True. On subprocess errors,
    returns False (don't skip if we can't determine).
    """
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

    files = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]

    # Merge commits with no files listed are structural commits
    if not files:
        return True

    for path in files:
        if not any(
            path.startswith(pat) if pat.endswith("/") else path == pat
            for pat in _CHANGELOG_PATTERNS
        ):
            return False

    return True


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    """Check if ancestor is an ancestor of descendant."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# Validation cache
# ---------------------------------------------------------------------------

def _cache_path(changes_dir: str) -> str:
    """Return path to the .validated cache file."""
    return os.path.join(changes_dir, ".validated")


def _read_cache(changes_dir: str) -> str | None:
    """Read the .validated file. Return the cached HEAD hash or None."""
    path = _cache_path(changes_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            sha = f.read().strip()
        return sha if len(sha) == 40 else None
    except OSError:
        return None


def _write_cache(changes_dir: str) -> None:
    """Write the current HEAD hash to the .validated cache file."""
    head = _git_head()
    if head is None:
        return
    path = _cache_path(changes_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n")


def _is_cache_valid(changes_dir: str) -> bool:
    """Check if the validation cache is still valid.

    Valid when:
    - .validated exists and contains a 40-char SHA
    - That SHA is an ancestor of (or equal to) HEAD
    - unreleased.jsonl's mtime is older than .validated's mtime
    """
    cached_sha = _read_cache(changes_dir)
    if cached_sha is None:
        return False

    head = _git_head()
    if head is None:
        return False

    # Check ancestor relationship (equal counts as ancestor)
    if cached_sha != head and not _is_ancestor(cached_sha, head):
        return False

    # Check mtimes
    cache_file = _cache_path(changes_dir)
    unreleased_file = os.path.join(changes_dir, "unreleased.jsonl")
    if not os.path.isfile(unreleased_file):
        return True  # No unreleased file means nothing to invalidate
    try:
        cache_mtime = os.path.getmtime(cache_file)
        unreleased_mtime = os.path.getmtime(unreleased_file)
        return unreleased_mtime <= cache_mtime
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_hashes_resolve(entries: list[ChangelogEntry]) -> tuple[bool, list[str]]:
    """Check that every hash in every entry resolves via git rev-parse."""
    details: list[str] = []
    all_hashes: list[str] = []
    for entry in entries:
        all_hashes.extend(entry.commits)

    resolved = resolve_hashes(all_hashes)
    for h, full in resolved.items():
        if full is None:
            details.append(f"hash does not resolve: {h}")

    return (len(details) == 0, details)


def check_in_range(entries: list[ChangelogEntry]) -> tuple[bool, list[str]]:
    """Check that every resolved hash is in the unreleased range.

    Unreleased range: commits in origin/main..HEAD.
    """
    details: list[str] = []
    unreleased_commits = set(_git_log_hashes("origin/main..HEAD"))
    if not unreleased_commits:
        # If there are no unreleased commits but there are entries, that's okay
        # if the entries are empty too
        if entries:
            # Check if origin/main exists at all
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", "origin/main"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    details.append("origin/main not found; cannot determine unreleased range")
                    return (False, details)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                details.append("could not verify origin/main")
                return (False, details)

    all_hashes: list[str] = []
    for entry in entries:
        all_hashes.extend(entry.commits)

    resolved = resolve_hashes(all_hashes)
    for h, full in resolved.items():
        if full is not None and full not in unreleased_commits:
            details.append(f"hash not in unreleased range: {h} ({full})")

    return (len(details) == 0, details)


def check_coverage(entries: list[ChangelogEntry]) -> tuple[bool, list[str]]:
    """Check that every unreleased commit appears in at least one entry.

    Commits that only touch changelog files (.rlsbl/changes/*, CHANGELOG.md)
    are automatically skipped -- they can never cover themselves.
    """
    details: list[str] = []
    unreleased_commits = set(_git_log_hashes("origin/main..HEAD"))

    # Collect all resolved hashes from entries
    all_hashes: list[str] = []
    for entry in entries:
        all_hashes.extend(entry.commits)
    resolved = resolve_hashes(all_hashes)
    covered = {full for full in resolved.values() if full is not None}

    skipped = 0
    uncovered = 0
    for commit in sorted(unreleased_commits):
        if commit not in covered:
            if _is_changelog_only_commit(commit):
                skipped += 1
                continue
            uncovered += 1
            details.append(f"unreleased commit not covered: {commit[:12]}")

    if skipped > 0:
        details.append(f"skipped {skipped} changelog-only commit(s)")

    return (uncovered == 0, details)


def check_no_orphans(entries: list[ChangelogEntry]) -> tuple[bool, list[str]]:
    """Flag entries where ALL hashes are unresolvable (stale/rebased entries)."""
    details: list[str] = []
    for i, entry in enumerate(entries):
        if not entry.commits:
            continue
        resolved = resolve_hashes(entry.commits)
        if all(v is None for v in resolved.values()):
            hashes_str = ", ".join(entry.commits[:3])
            if len(entry.commits) > 3:
                hashes_str += ", ..."
            details.append(f"entry {i + 1}: all hashes unresolvable ({hashes_str})")

    return (len(details) == 0, details)


def check_schema(entries: list[ChangelogEntry]) -> tuple[bool, list[str]]:
    """Check that every entry passes schema validation."""
    details: list[str] = []
    for i, entry in enumerate(entries):
        errors = validate_schema(entry)
        for error in errors:
            details.append(f"entry {i + 1}: {error}")

    return (len(details) == 0, details)


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------

def validate_unreleased(changes_dir: str) -> dict:
    """Run all 5 validation checks on unreleased.jsonl.

    Returns a dict with:
    - check names as keys, (passed, details) tuples as values
    - "passed": overall bool (True only if all checks pass)

    Uses validation cache: if the cache is valid and HEAD hasn't changed,
    skips full revalidation.
    """
    entries = read_unreleased(changes_dir)

    # Check cache
    if _is_cache_valid(changes_dir):
        cached_sha = _read_cache(changes_dir)
        head = _git_head()
        if cached_sha == head:
            # Nothing changed since last validation
            return {
                "passed": True,
                "checks": {
                    "hashes_resolve": (True, []),
                    "in_range": (True, []),
                    "coverage": (True, []),
                    "no_orphans": (True, []),
                    "schema": (True, []),
                },
            }
        # Cache is valid but HEAD moved: only validate new entries
        # (entries added since the cached state). Since we can't easily
        # determine which entries are new without more metadata, run full
        # validation but update cache on success.

    checks = {
        "hashes_resolve": check_hashes_resolve(entries),
        "in_range": check_in_range(entries),
        "coverage": check_coverage(entries),
        "no_orphans": check_no_orphans(entries),
        "schema": check_schema(entries),
    }

    overall = all(passed for passed, _ in checks.values())

    if overall:
        _write_cache(changes_dir)

    return {
        "passed": overall,
        "checks": checks,
    }
