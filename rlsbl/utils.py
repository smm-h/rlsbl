"""Git helpers, version bump, changelog extraction, and other shared utilities."""

import os
import re
import shutil
import subprocess
import sys


def run(cmd, args=None, timeout=120):
    """Run a command with args, return trimmed stdout. Raise on failure."""
    full_cmd = [cmd] + (args or [])
    result = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=timeout)
    return result.stdout.strip()


def run_silent(cmd, args=None, timeout=30):
    """Run a command suppressing stderr. Return trimmed stdout. Raise on failure."""
    full_cmd = [cmd] + (args or [])
    result = subprocess.run(
        full_cmd, capture_output=True, text=True, check=True, timeout=timeout,
    )
    return result.stdout.strip()


def is_clean_tree():
    """Returns True if the git working tree is clean (no uncommitted changes)."""
    status = run("git", ["status", "--porcelain"])
    return len(status) == 0


def get_current_branch():
    """Returns the current git branch name."""
    return run("git", ["rev-parse", "--abbrev-ref", "HEAD"])


def get_push_timeout():
    """Return the push timeout in seconds, from RLSBL_PUSH_TIMEOUT or default 120."""
    raw = os.environ.get("RLSBL_PUSH_TIMEOUT")
    if raw is None:
        return 120
    try:
        val = int(raw)
        if val <= 0:
            raise ValueError
        return val
    except ValueError:
        print(f'Warning: invalid RLSBL_PUSH_TIMEOUT="{raw}", using default 120s', file=sys.stderr)
        return 120


def push_if_needed(branch):
    """Push the branch to origin if local is ahead of remote."""
    timeout = get_push_timeout()
    local = run("git", ["rev-parse", branch])
    try:
        remote = run("git", ["rev-parse", f"origin/{branch}"])
    except subprocess.CalledProcessError:
        # Remote branch doesn't exist yet; push it
        run("git", ["push", "-u", "origin", branch], timeout=timeout)
        return

    if local != remote:
        run("git", ["push", "origin", branch], timeout=timeout)


def extract_changelog_entry(changelog_path, version):
    """Extract a changelog entry for a specific version.

    Looks for a heading like '## 1.2.3' and captures everything
    until the next heading or EOF.
    """
    with open(changelog_path, "r", encoding="utf-8") as f:
        content = f.read()

    escaped_version = re.escape(version)
    header_pattern = re.compile(r"^## " + escaped_version + r"\s*$", re.MULTILINE)
    match = header_pattern.search(content)
    if not match:
        return None

    # Start after the matched header line
    start_idx = match.end()
    # Find the next "## " heading or use end of string
    next_heading_idx = content.find("\n## ", start_idx)
    end_idx = len(content) if next_heading_idx == -1 else next_heading_idx
    entry = content[start_idx:end_idx].strip()
    return entry or None


def check_gh_installed():
    """Check that the gh CLI is installed."""
    try:
        run("gh", ["--version"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_gh_auth():
    """Check that the gh CLI is authenticated."""
    try:
        run("gh", ["auth", "status"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def find_commit_tool():
    """Detect safegit or fall back to git for committing.

    Returns "safegit" if available on PATH, otherwise "git".
    """
    if shutil.which("safegit"):
        return "safegit"
    return "git"


def bump_version(version, bump_type):
    """Bump a semver version string by the given type (patch, minor, major).

    Returns the new version string.
    """
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f'Invalid semver version: "{version}"')
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f'Invalid semver version: "{version}"')

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f'Invalid bump type: "{bump_type}". Use patch, minor, or major.')
