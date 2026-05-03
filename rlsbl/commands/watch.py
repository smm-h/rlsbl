"""Watch command: monitor CI runs for a commit and report results."""

import json
import shutil
import subprocess
import sys
import time

from ..utils import run


def _notify(title, body):
    """Send a desktop notification. Non-fatal if unavailable."""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{body}" with title "{title}"'],
                timeout=5, capture_output=True,
            )
        elif shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", "-u", "normal", title, body],
                timeout=5, capture_output=True,
            )
    except Exception:
        pass


def run_cmd(registry, args, flags):
    """Watch all CI runs for a commit until they complete.

    Usage: rlsbl watch [<commit-sha>]
    Defaults to HEAD if no commit SHA is provided.
    """
    try:
        # Get commit SHA
        if args:
            commit_sha = args[0]
        else:
            try:
                commit_sha = run("git", ["rev-parse", "HEAD"])
            except Exception:
                print("Error: not a git repository and no commit SHA provided.", file=sys.stderr)
                sys.exit(1)

        # Get repo info for display and URLs
        try:
            repo_info = run("gh", ["repo", "view", "--json", "nameWithOwner,name"])
            info = json.loads(repo_info)
            repo_slug = info.get("nameWithOwner", "")
            repo_name = info.get("name", "")
        except Exception:
            print("Error: could not get repo info. Is gh installed and authenticated?", file=sys.stderr)
            sys.exit(1)

        # Try to find a tag for this commit for nicer display
        try:
            tag = run("git", ["describe", "--tags", "--exact-match", commit_sha])
        except Exception:
            tag = commit_sha[:12]

        label = f"{repo_name} {tag}" if repo_name else tag

        # Poll until at least one run appears (retry up to 30s)
        runs = []
        for _ in range(15):
            try:
                raw = run("gh", ["run", "list", "--commit", commit_sha,
                                 "--json", "databaseId,name,status"])
                parsed = json.loads(raw)
                if parsed:
                    runs = parsed
                    break
            except Exception:
                pass
            time.sleep(2)

        if not runs:
            print(f"rlsbl: {label}: no CI runs found after 30s", file=sys.stderr)
            sys.exit(1)

        print(f"rlsbl: {label}: found {len(runs)} CI run(s), watching...", file=sys.stderr)

        # Watch each run sequentially, collecting results
        any_failed = False
        for ci_run in runs:
            run_id = str(ci_run["databaseId"])
            workflow_name = ci_run.get("name", f"run {run_id}")

            try:
                # gh run watch blocks until the run completes;
                # --exit-status makes it exit 1 on failure; check=True raises
                # CalledProcessError so we can distinguish pass from fail
                subprocess.run(
                    ["gh", "run", "watch", run_id, "--exit-status"],
                    capture_output=True, text=True, timeout=3600, check=True,
                )
                print(f"rlsbl: {label}: {workflow_name} passed", file=sys.stderr)
            except subprocess.CalledProcessError:
                any_failed = True
                print(f"rlsbl: {label}: {workflow_name} FAILED", file=sys.stderr)
                if repo_slug:
                    print(f"rlsbl: https://github.com/{repo_slug}/actions/runs/{run_id}",
                          file=sys.stderr)
            except subprocess.TimeoutExpired:
                any_failed = True
                print(f"rlsbl: {label}: {workflow_name} timed out after 1h", file=sys.stderr)

        # Desktop notification for overall result
        if any_failed:
            _notify(f"{label}: CI FAILED", "One or more workflows failed")
        else:
            _notify(f"{label}: CI passed", "All workflows passed")

        sys.exit(1 if any_failed else 0)
    except KeyboardInterrupt:
        print("\nWatch cancelled.", file=sys.stderr)
        sys.exit(130)
