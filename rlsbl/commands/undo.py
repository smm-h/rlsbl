"""Undo command: revert the last release."""

import sys

from ..utils import run, check_gh_installed, check_gh_auth, get_push_timeout, get_current_branch, push_if_needed, is_clean_tree

# Status constants for step results
OK = "OK"
FAILED = "FAILED"
SKIPPED = "SKIPPED"


def _print_summary(results):
    """Print a summary table of step results. Only called when at least one step failed."""
    # Calculate column widths
    step_width = max(len(r[0]) for r in results)
    status_width = max(len(r[1]) for r in results)

    header = f"{'Step':<{step_width}}  {'Status':<{status_width}}  Remediation"
    print(f"\n{header}")
    print("-" * len(header))
    for step_name, status, remediation in results:
        print(f"{step_name:<{step_width}}  {status:<{status_width}}  {remediation}")


def run_cmd(registry, args, flags):
    if not check_gh_installed():
        print("Error: gh CLI is not installed.", file=sys.stderr)
        sys.exit(1)
    if not check_gh_auth():
        print("Error: gh CLI is not authenticated.", file=sys.stderr)
        sys.exit(1)

    if not is_clean_tree():
        print("Error: working tree is not clean. Commit your changes first.", file=sys.stderr)
        sys.exit(1)

    # Find the latest tag
    try:
        tag = run("git", ["describe", "--tags", "--abbrev=0"])
    except Exception:
        print("Error: no tags found. Nothing to undo.", file=sys.stderr)
        sys.exit(1)

    print(f"This will undo release {tag}:")
    print(f"  - Delete git tag {tag} (local + remote)")
    print(f"  - Revert the version bump commit")
    print(f"  - Delete the GitHub Release for {tag}")

    if not flags.get("yes"):
        try:
            answer = input("\nThis is destructive. Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    # Collect (step_name, status, remediation) for each step
    results = []

    # Delete GitHub Release
    try:
        run("gh", ["release", "delete", tag, "--yes"])
        results.append(("Delete GitHub Release", OK, "-"))
    except Exception:
        results.append(("Delete GitHub Release", FAILED, f"gh release delete {tag} --yes"))

    # Delete remote tag
    try:
        run("git", ["push", "origin", f":{tag}"], timeout=get_push_timeout())
        results.append(("Delete remote tag", OK, "-"))
    except Exception:
        results.append(("Delete remote tag", FAILED, f"git push origin :{tag}"))

    # Delete local tag
    try:
        run("git", ["tag", "-d", tag])
        results.append(("Delete local tag", OK, "-"))
    except Exception:
        results.append(("Delete local tag", FAILED, f"git tag -d {tag}"))

    # Revert the version bump commit (should be HEAD)
    reverted = False
    try:
        head_msg = run("git", ["log", "-1", "--format=%s"])
        if head_msg == tag:
            run("git", ["revert", "--no-edit", "HEAD"])
            reverted = True
            results.append(("Revert commit", OK, "-"))
        else:
            results.append(("Revert commit", SKIPPED, f"HEAD ({head_msg}) does not match tag ({tag})"))
    except Exception:
        results.append(("Revert commit", FAILED, "git revert --no-edit HEAD"))

    # Push the revert commit to remote
    if reverted:
        should_push = flags.get("yes")
        if not should_push:
            try:
                answer = input("\nPush revert to remote? [y/N] ").strip().lower()
                should_push = answer == "y"
            except (EOFError, KeyboardInterrupt):
                should_push = False

        if should_push:
            try:
                branch = get_current_branch()
                push_if_needed(branch)
                results.append(("Push", OK, "-"))
            except Exception:
                results.append(("Push", FAILED, "git push"))

    # Print summary: table only if something failed, otherwise a simple success message
    has_failure = any(status == FAILED for _, status, _ in results)
    if has_failure:
        _print_summary(results)
    else:
        print("\nUndo complete.")
