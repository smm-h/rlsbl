"""Undo command: revert the last release."""

import sys

from ..utils import run, run_silent, check_gh_installed, check_gh_auth


def run_cmd(registry, args, flags):
    check_gh_installed()
    check_gh_auth()

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

    # Delete GitHub Release
    try:
        run("gh", ["release", "delete", tag, "--yes"])
        print(f"Deleted GitHub Release: {tag}")
    except Exception as e:
        print(f"Warning: could not delete GitHub Release: {e}")

    # Delete remote tag
    try:
        run("git", ["push", "origin", f":{tag}"])
        print(f"Deleted remote tag: {tag}")
    except Exception as e:
        print(f"Warning: could not delete remote tag: {e}")

    # Delete local tag
    try:
        run("git", ["tag", "-d", tag])
        print(f"Deleted local tag: {tag}")
    except Exception as e:
        print(f"Warning: could not delete local tag: {e}")

    # Revert the version bump commit (should be HEAD)
    try:
        head_msg = run("git", ["log", "-1", "--format=%s"])
        if head_msg == tag:
            run("git", ["revert", "--no-edit", "HEAD"])
            print(f"Reverted commit: {head_msg}")
        else:
            print(f"Warning: HEAD commit ({head_msg}) doesn't match tag ({tag}). Skipping revert.")
    except Exception as e:
        print(f"Warning: could not revert commit: {e}")

    print(f"\nUndo complete. Run 'git push' to sync the revert.")
