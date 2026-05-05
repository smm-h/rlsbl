"""Watch command: monitor CI runs for a commit and report results."""

import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..utils import run


def _notify(title, body):
    """Send a desktop notification. Non-fatal if unavailable."""
    try:
        if sys.platform == "darwin":
            # Escape double quotes to prevent AppleScript injection
            escaped_title = title.replace('"', '\\"')
            escaped_body = body.replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{escaped_body}" with title "{escaped_title}"'],
                timeout=5, capture_output=True,
            )
        elif shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", "-u", "normal", title, body],
                timeout=5, capture_output=True,
            )
    except Exception:
        pass


def _watch_single_run(ci_run, label, repo_slug):
    """Watch a single CI run. Returns a dict with name, passed, and message."""
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
        msg = f"rlsbl: {label}: [{workflow_name}] passed"
        print(msg, file=sys.stderr)
        return {"name": workflow_name, "passed": True}
    except subprocess.CalledProcessError:
        msg = f"rlsbl: {label}: [{workflow_name}] FAILED"
        print(msg, file=sys.stderr)
        if repo_slug:
            print(f"rlsbl: https://github.com/{repo_slug}/actions/runs/{run_id}",
                  file=sys.stderr)
        return {"name": workflow_name, "passed": False}
    except subprocess.TimeoutExpired:
        msg = f"rlsbl: {label}: [{workflow_name}] timed out after 1h"
        print(msg, file=sys.stderr)
        return {"name": workflow_name, "passed": False}
    except Exception as exc:
        msg = f"rlsbl: {label}: [{workflow_name}] error: {exc}"
        print(msg, file=sys.stderr)
        return {"name": workflow_name, "passed": False}


def _watch_runs(runs, label, repo_slug):
    """Watch all runs in parallel (or directly if only one). Returns list of result dicts."""
    if len(runs) == 1:
        # No need for threads when there's only one run
        return [_watch_single_run(runs[0], label, repo_slug)]

    results = []
    with ThreadPoolExecutor(max_workers=len(runs)) as executor:
        futures = {
            executor.submit(_watch_single_run, ci_run, label, repo_slug): ci_run
            for ci_run in runs
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                # Should not happen since _watch_single_run catches all exceptions,
                # but guard against unexpected failures in the future machinery
                ci_run = futures[future]
                workflow_name = ci_run.get("name", f"run {ci_run['databaseId']}")
                print(f"rlsbl: {label}: [{workflow_name}] thread error: {exc}",
                      file=sys.stderr)
                results.append({"name": workflow_name, "passed": False})
    return results


def run_cmd(registry, args, flags):
    """Watch all CI runs for a commit until they complete.

    Usage: rlsbl watch [<commit-sha>]
    Defaults to HEAD if no commit SHA is provided.
    """
    try:
        # Get commit SHA (resolve short SHAs -- gh requires full 40-char)
        if args:
            try:
                commit_sha = run("git", ["rev-parse", args[0]])
            except Exception:
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

        # Watch runs in parallel (or directly if only one)
        results = _watch_runs(runs, label, repo_slug)

        # Desktop notification with aggregated results
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        if failed:
            body = f"{passed}/{len(results)} passed, {failed} failed"
            _notify(f"{label}: CI FAILED", body)
        else:
            body = f"{len(results)}/{len(results)} passed"
            _notify(f"{label}: CI passed", body)

        sys.exit(1 if failed else 0)
    except KeyboardInterrupt:
        print("\nWatch cancelled.", file=sys.stderr)
        sys.exit(130)
