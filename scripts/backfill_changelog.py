#!/usr/bin/env python3
"""Backfill .rlsbl/changes/ JSONL files from existing CHANGELOG.md and git log.

Parses the CHANGELOG.md to extract bullet points per version, maps them to
commits via keyword matching, and writes x.y.z.jsonl files for each version.

Usage:
    scripts/backfill_changelog.py [--force] [--version X.Y.Z]
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys

# Add project root to path so we can import rlsbl modules.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from rlsbl.changelog.schema import ChangelogEntry, serialize_entry
from rlsbl.utils import extract_changelog_entry


def get_sorted_tags() -> list[str]:
    """Get all version tags sorted by semver ascending."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=version:refname"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
    return tags


def get_commits_in_range(start_ref: str | None, end_ref: str) -> list[dict]:
    """Get commits between two refs as [{"hash": ..., "subject": ...}].

    If start_ref is None, returns all ancestors of end_ref.
    """
    if start_ref is None:
        range_spec = end_ref
    else:
        range_spec = f"{start_ref}..{end_ref}"

    result = subprocess.run(
        ["git", "log", range_spec, "--format=%H %s"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append({"hash": parts[0], "subject": parts[1]})
    return commits


def parse_bullets(changelog_text: str) -> list[str]:
    """Parse a changelog entry into individual bullet point texts.

    Each bullet starts with '- ' at the start of a line. Continuation lines
    (indented text that follows) are merged into the preceding bullet.
    """
    if not changelog_text:
        return []

    lines = changelog_text.split("\n")
    bullets: list[str] = []
    current: list[str] = []

    for line in lines:
        if line.startswith("- "):
            if current:
                bullets.append(" ".join(current))
            current = [line[2:].strip()]
        elif line.startswith("  ") and current:
            # Continuation of previous bullet
            current.append(line.strip())
        else:
            # Non-bullet line (could be sub-list header like ### or blank)
            if current:
                bullets.append(" ".join(current))
                current = []

    if current:
        bullets.append(" ".join(current))

    return bullets


def classify_bullet(text: str) -> str:
    """Determine the type of a changelog bullet: breaking, fix, or feature."""
    lower = text.lower()
    if lower.startswith("**breaking") or "breaking:" in lower:
        return "breaking"
    if lower.startswith("**fix") or "fix:" in lower or lower.startswith("fix "):
        return "fix"
    return "feature"


def extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from text for matching.

    Strips conventional-commit prefixes and common noise words.
    Returns lowercase keywords of length >= 3.
    """
    # Remove conventional commit prefix
    cleaned = re.sub(r"^[a-z]+(\([^)]*\))?:\s*", "", text, flags=re.IGNORECASE)
    noise = {"the", "and", "for", "with", "from", "into", "that", "this", "not",
             "are", "now", "new", "use", "all", "has", "was", "its", "also",
             "when", "only", "each", "per", "via", "set", "run", "add", "added",
             "instead"}
    words = re.findall(r"[a-zA-Z0-9_-]+", cleaned.lower())
    return [w for w in words if len(w) >= 3 and w not in noise]


def score_match(commit_subject: str, bullet_text: str) -> int:
    """Score how well a commit subject matches a changelog bullet.

    Returns the number of matching keywords. 0 means no match.
    """
    commit_kws = extract_keywords(commit_subject)
    if not commit_kws:
        return 0

    bullet_lower = bullet_text.lower()

    # Direct substring match of cleaned subject
    cleaned = re.sub(r"^[a-z]+(\([^)]*\))?:\s*", "", commit_subject, flags=re.IGNORECASE)
    if cleaned.lower() in bullet_lower:
        return len(commit_kws) + 10  # strong match bonus

    return sum(1 for kw in commit_kws if kw in bullet_lower)


def map_commits_to_bullets(
    commits: list[dict],
    bullets: list[str],
) -> tuple[dict[int, list[str]], list[str]]:
    """Map commits to changelog bullets via keyword matching.

    Returns:
        bullet_commits: {bullet_index: [commit_hashes]} for matched bullets
        unmatched_hashes: list of commit hashes not matched to any bullet
    """
    if not bullets:
        return {}, [c["hash"] for c in commits]

    bullet_commits: dict[int, list[str]] = {i: [] for i in range(len(bullets))}
    unmatched_hashes: list[str] = []

    for commit in commits:
        subject = commit["subject"]
        # Skip version-tag commits (e.g., "v0.24.0")
        if re.match(r"^v?\d+\.\d+\.\d+$", subject):
            unmatched_hashes.append(commit["hash"])
            continue

        best_score = 0
        best_idx = -1
        for i, bullet in enumerate(bullets):
            s = score_match(subject, bullet)
            if s > best_score:
                best_score = s
                best_idx = i

        # Require at least 2 keyword matches (or 1 if commit has only 1 keyword)
        commit_kws = extract_keywords(subject)
        threshold = min(2, len(commit_kws)) if commit_kws else 1

        if best_score >= threshold and best_idx >= 0:
            bullet_commits[best_idx].append(commit["hash"])
        else:
            unmatched_hashes.append(commit["hash"])

    return bullet_commits, unmatched_hashes


def is_no_user_facing(changelog_text: str) -> bool:
    """Check if the changelog entry indicates no user-facing changes."""
    if not changelog_text:
        return True
    stripped = changelog_text.strip()
    return stripped in (
        "- No user-facing changes.",
        "No user-facing changes.",
    )


def build_entries(
    commits: list[dict],
    changelog_text: str | None,
) -> list[ChangelogEntry]:
    """Build ChangelogEntry objects for a version.

    Maps commits to changelog bullets, creating user-facing entries for
    matched commits and non-user-facing entries for the rest.
    """
    if not commits:
        return []

    # No changelog entry or "no user-facing changes"
    if not changelog_text or is_no_user_facing(changelog_text):
        return [
            ChangelogEntry(
                commits=[c["hash"] for c in commits],
                user_facing=False,
            )
        ]

    bullets = parse_bullets(changelog_text)
    if not bullets:
        return [
            ChangelogEntry(
                commits=[c["hash"] for c in commits],
                user_facing=False,
            )
        ]

    bullet_commits, unmatched = map_commits_to_bullets(commits, bullets)

    entries: list[ChangelogEntry] = []

    # Create user-facing entries for each bullet that has commits
    for i, bullet in enumerate(bullets):
        hashes = bullet_commits.get(i, [])
        if not hashes:
            # Bullet with no matched commits: assign a synthetic hash
            # (no commits found for this bullet, but it's still user-facing)
            # Use unmatched commits if available, otherwise skip
            continue
        entries.append(ChangelogEntry(
            commits=hashes,
            user_facing=True,
            description=bullet,
            type=classify_bullet(bullet),
        ))

    # Bullets with no matched commits: create entries with borrowed unmatched hashes
    unassigned_bullets = [
        (i, bullet) for i, bullet in enumerate(bullets)
        if not bullet_commits.get(i)
    ]
    if unassigned_bullets and unmatched:
        # Distribute unmatched commits to unassigned bullets round-robin
        for idx, (i, bullet) in enumerate(unassigned_bullets):
            if idx < len(unmatched):
                entries.append(ChangelogEntry(
                    commits=[unmatched[idx]],
                    user_facing=True,
                    description=bullet,
                    type=classify_bullet(bullet),
                ))
        # Remaining unmatched after distribution
        remaining = unmatched[len(unassigned_bullets):]
    else:
        remaining = unmatched

    # Non-user-facing entry for remaining unmatched commits
    if remaining:
        entries.append(ChangelogEntry(
            commits=remaining,
            user_facing=False,
        ))

    return entries


def write_jsonl(path: str, entries: list[ChangelogEntry]) -> None:
    """Write entries to a JSONL file and set it read-only (chmod 444)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(serialize_entry(entry) + "\n")
    os.chmod(path, 0o444)


def backfill(
    project_root: str,
    changelog_path: str,
    *,
    force: bool = False,
    single_version: str | None = None,
) -> dict:
    """Run the backfill process.

    Returns a summary dict with keys: versions_processed, total_commits,
    commits_matched, skipped.
    """
    changes_dir = os.path.join(project_root, ".rlsbl", "changes")
    os.makedirs(changes_dir, exist_ok=True)

    tags = get_sorted_tags()
    if not tags:
        print("No version tags found.")
        return {"versions_processed": 0, "total_commits": 0,
                "commits_matched": 0, "skipped": 0}

    # Build version pairs: (prev_tag_or_None, current_tag)
    pairs: list[tuple[str | None, str]] = []
    pairs.append((None, tags[0]))  # first version: all ancestors
    for i in range(1, len(tags)):
        pairs.append((tags[i - 1], tags[i]))

    versions_processed = 0
    total_commits = 0
    commits_matched = 0
    skipped = 0

    for prev_tag, curr_tag in pairs:
        version = curr_tag.lstrip("v")

        if single_version and version != single_version:
            continue

        jsonl_path = os.path.join(changes_dir, f"{version}.jsonl")
        if os.path.exists(jsonl_path) and not force:
            print(f"  {version}: skipping (already exists)")
            skipped += 1
            continue

        # If file exists and force, remove read-only protection
        if os.path.exists(jsonl_path) and force:
            os.chmod(jsonl_path, 0o644)

        commits = get_commits_in_range(prev_tag, curr_tag)
        changelog_text = extract_changelog_entry(changelog_path, version)

        entries = build_entries(commits, changelog_text)
        write_jsonl(jsonl_path, entries)

        # Count stats
        n_commits = len(commits)
        n_matched = sum(
            len(e.commits) for e in entries if e.user_facing
        )
        total_commits += n_commits
        commits_matched += n_matched
        versions_processed += 1

        print(f"  {version}: {n_commits} commits, {n_matched} matched to changelog")

    return {
        "versions_processed": versions_processed,
        "total_commits": total_commits,
        "commits_matched": commits_matched,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill .rlsbl/changes/ JSONL files from CHANGELOG.md and git log",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing JSONL files",
    )
    parser.add_argument(
        "--version",
        help="Process a single version only (e.g., 0.24.0)",
    )
    args = parser.parse_args()

    # Find project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    changelog_path = os.path.join(project_root, "CHANGELOG.md")

    if not os.path.isfile(changelog_path):
        print(f"Error: CHANGELOG.md not found at {changelog_path}", file=sys.stderr)
        sys.exit(1)

    print("Backfilling .rlsbl/changes/ from CHANGELOG.md and git log...\n")

    summary = backfill(
        project_root,
        changelog_path,
        force=args.force,
        single_version=args.version,
    )

    print(f"\nDone.")
    print(f"  Versions processed: {summary['versions_processed']}")
    print(f"  Versions skipped:   {summary['skipped']}")
    print(f"  Total commits:      {summary['total_commits']}")
    print(f"  Commits matched:    {summary['commits_matched']}")
    if summary["total_commits"] > 0:
        pct = summary["commits_matched"] / summary["total_commits"] * 100
        print(f"  Coverage:           {pct:.1f}%")


if __name__ == "__main__":
    main()
