"""Unreleased command: list commits since last tag and check changelog coverage."""

import json
import os
import re
import subprocess
import sys


def _get_last_tag():
    """Get the most recent tag. Returns None if no tags exist."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _get_commits_since(tag):
    """Get commits since the given tag (or all commits if tag is None).

    Returns a list of dicts with keys: hash, subject, author, date.
    Uses NUL as field separator for safe parsing.
    """
    # Format: hash<NUL>subject<NUL>author<NUL>ISO-date
    fmt = "%H%x00%s%x00%an%x00%aI"
    if tag:
        range_spec = f"{tag}..HEAD"
    else:
        range_spec = "HEAD"

    try:
        result = subprocess.run(
            ["git", "log", range_spec, f"--format={fmt}"],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    lines = result.stdout.strip().split("\n")
    commits = []
    for line in lines:
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) != 4:
            continue
        commits.append({
            "hash": parts[0],
            "subject": parts[1],
            "author": parts[2],
            "date": parts[3],
        })
    return commits


def _get_unreleased_changelog_text(changelog_path):
    """Extract changelog text that covers unreleased changes.

    Looks for an "## Unreleased" section first, then falls back to the first
    section in the file (the one above the last released version).
    Returns the text content or empty string if nothing found.
    """
    if not os.path.isfile(changelog_path):
        return ""

    with open(changelog_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Look for an explicit "## Unreleased" section (case-insensitive)
    unreleased_match = re.search(
        r"^## [Uu]nreleased\s*$", content, re.MULTILINE
    )
    if unreleased_match:
        start = unreleased_match.end()
        next_heading = content.find("\n## ", start)
        end = len(content) if next_heading == -1 else next_heading
        return content[start:end].strip()

    # Fall back: grab the first ## section (which is typically the next release)
    # Only if it doesn't match an already-tagged version
    first_heading = re.search(r"^## (.+)$", content, re.MULTILINE)
    if first_heading:
        start = first_heading.end()
        next_heading = content.find("\n## ", start)
        end = len(content) if next_heading == -1 else next_heading
        # Return the section header + body for keyword matching
        return first_heading.group(0) + "\n" + content[start:end].strip()

    return ""


def _extract_keywords(subject):
    """Extract significant keywords from a commit subject for matching.

    Strips conventional-commit prefixes (fix:, feat:, etc.) and common
    noise words, returns lowercase keywords of length >= 3.
    """
    # Remove conventional commit prefix
    cleaned = re.sub(r"^[a-z]+(\([^)]*\))?:\s*", "", subject, flags=re.IGNORECASE)
    # Split into words, lowercase, filter short/noise words
    noise = {"the", "and", "for", "with", "from", "into", "that", "this", "not", "are"}
    words = re.findall(r"[a-zA-Z0-9_-]+", cleaned.lower())
    return [w for w in words if len(w) >= 3 and w not in noise]


def _is_covered(subject, changelog_text):
    """Check if a commit subject is covered by changelog text.

    Uses keyword matching: if any significant keyword from the subject
    appears in the changelog text, we consider it covered.
    """
    if not changelog_text:
        return False

    changelog_lower = changelog_text.lower()

    # Direct substring match of the full subject (minus prefix)
    cleaned = re.sub(r"^[a-z]+(\([^)]*\))?:\s*", "", subject, flags=re.IGNORECASE)
    if cleaned.lower() in changelog_lower:
        return True

    # Keyword matching: require at least 2 keywords to match (or 1 if only 1 keyword)
    keywords = _extract_keywords(subject)
    if not keywords:
        return False

    matched = sum(1 for kw in keywords if kw in changelog_lower)
    threshold = min(2, len(keywords))
    return matched >= threshold


def run_cmd(registry, args, flags):
    """List unreleased commits and their changelog coverage.

    Usage: rlsbl unreleased [--json]
    """
    tag = _get_last_tag()
    commits = _get_commits_since(tag)

    if not commits:
        if flags.get("json"):
            print(json.dumps({"tag": tag, "commits": [], "coverage": {"covered": 0, "total": 0}}))
        else:
            print("No unreleased commits.")
        sys.exit(0)

    # Read changelog for coverage checking
    changelog_path = os.path.join(os.getcwd(), "CHANGELOG.md")
    changelog_text = _get_unreleased_changelog_text(changelog_path)

    # Cross-reference each commit
    for commit in commits:
        commit["covered"] = _is_covered(commit["subject"], changelog_text)

    covered_count = sum(1 for c in commits if c["covered"])
    total = len(commits)

    if flags.get("json"):
        output = {
            "tag": tag,
            "commits": commits,
            "coverage": {"covered": covered_count, "total": total},
        }
        print(json.dumps(output, indent=2))
    else:
        tag_display = tag or "(no tags)"
        print(f"Unreleased commits since {tag_display} ({total} commits):\n")
        for commit in commits:
            short_hash = commit["hash"][:7]
            status = "[COVERED]" if commit["covered"] else "[MISSING]"
            # Truncate long subjects to keep output aligned
            subject = commit["subject"]
            if len(subject) > 50:
                subject = subject[:47] + "..."
            print(f"  {short_hash}  {subject:<50}  {status}")

        print(f"\nCoverage: {covered_count}/{total} commits have changelog entries.")

    sys.exit(0)
