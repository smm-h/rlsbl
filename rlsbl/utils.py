"""Git helpers, version bump, changelog extraction, and other shared utilities."""

import os
import re
import shutil
import subprocess
import sys


def run(cmd, args=None, timeout=120, env=None):
    """Run a command with args, return trimmed stdout. Raise on failure."""
    full_cmd = [cmd] + (args or [])
    result = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=timeout, env=env)
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


def spawn_ci_watcher(commit_sha, tag):
    """Spawn a detached background process that watches CI and prints results to stderr.

    The spawned process inherits the parent's stderr so output appears in the
    same terminal/stream -- important for AI agents that read stderr.
    Desktop notifications are sent as a secondary channel when available.
    """
    repo_slug = ""
    try:
        repo_slug = run("gh", ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    except Exception:
        pass

    repo_name = ""
    try:
        repo_name = run("gh", ["repo", "view", "--json", "name", "-q", ".name"])
    except Exception:
        pass

    label = f"{repo_name} {tag}" if repo_name else tag

    # Build the notification snippet based on what's available on this platform
    notify_snippet = _notify_snippet()

    script = f"""
import subprocess, sys, time

commit_sha = {commit_sha!r}
label = {label!r}
repo_slug = {repo_slug!r}

# Find the CI run by commit SHA (retry up to 30s)
run_id = None
for _ in range(15):
    try:
        r = subprocess.run(
            ["gh", "run", "list", "--commit", commit_sha, "--limit", "1",
             "--json", "databaseId", "-q", ".[0].databaseId"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            run_id = r.stdout.strip()
            break
    except Exception:
        pass
    time.sleep(2)

if not run_id:
    sys.exit(0)

# Watch the run until it completes
result = subprocess.run(
    ["gh", "run", "watch", run_id, "--exit-status"],
    capture_output=True, text=True, timeout=3600)

ok = result.returncode == 0

# Extract last non-empty line as summary for desktop notification
summary = ""
for line in reversed(result.stdout.strip().splitlines()):
    if line.strip():
        summary = line.strip()
        break

# Print result to stderr so AI agents and terminal users can see it
if ok:
    print(f"rlsbl: {{label}}: CI passed", file=sys.stderr)
else:
    print(f"rlsbl: {{label}}: CI FAILED", file=sys.stderr)
    if repo_slug and run_id:
        print(f"rlsbl: https://github.com/{{repo_slug}}/actions/runs/{{run_id}}", file=sys.stderr)

# Desktop notification (optional, non-fatal)
title = f"{{label}}: CI passed" if ok else f"{{label}}: CI FAILED"
try:
{notify_snippet}
except Exception:
    pass
"""
    subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )


def _notify_snippet():
    """Return an indented Python code snippet for sending a desktop notification.

    Returns a pass statement if no notification tool is available.
    The snippet is intended to be embedded inside a try/except block.
    """
    indent = "    "
    if sys.platform == "darwin":
        return (
            f'{indent}subprocess.run(["osascript", "-e",\n'
            f'{indent}    f\'display notification "{{summary}}" with title "{{title}}"\'],\n'
            f'{indent}    timeout=5)'
        )
    if shutil.which("notify-send"):
        return (
            f'{indent}urgency = "normal" if ok else "critical"\n'
            f'{indent}subprocess.run(["notify-send", "-u", urgency, title, summary], timeout=5)'
        )
    return f"{indent}pass"


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
