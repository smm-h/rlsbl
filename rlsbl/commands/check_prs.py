"""Check-prs command: list open PRs for awareness."""

import shutil
import subprocess
import sys


def run_cmd(registry, args, flags):
    """List open pull requests in the current repository.

    Exits silently if gh CLI is not available. Always exits 0 (informational only).
    """
    if not shutil.which("gh"):
        sys.exit(0)

    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "20"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(result.stdout.strip())
    except Exception:
        pass

    sys.exit(0)
