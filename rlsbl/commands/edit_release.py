"""Edit-release command: update GitHub Release notes from CHANGELOG.md."""

import os
import sys
import time

from ..targets import TARGETS, detect_targets
from ..utils import check_gh_auth, check_gh_installed, extract_changelog_entry, run


def run_cmd(args, flags):
    """Update GitHub Release notes from the changelog entry for a version.

    If no version is given, detects the current version from the project's
    primary target. Reads the changelog entry and updates the GitHub Release.
    """
    dry_run = flags.get("dry-run", False)

    if not check_gh_installed():
        print("Error: gh CLI is not installed.", file=sys.stderr)
        sys.exit(1)
    if not check_gh_auth():
        print("Error: gh CLI is not authenticated.", file=sys.stderr)
        sys.exit(1)

    # Detect primary target
    entries = detect_targets(".")
    if not entries:
        print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
        sys.exit(1)
    primary = entries[0]
    target = TARGETS[primary.name]

    # Resolve version
    if args:
        raw_version = args[0]
    else:
        raw_version = target.read_version(primary.path)

    # Normalize: strip leading "v" for changelog lookup
    version = raw_version.lstrip("v")
    tag = target.tag_format(version)

    # Extract changelog entry
    changelog_path = os.path.join(".", "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        print("Error: CHANGELOG.md not found.", file=sys.stderr)
        sys.exit(1)

    changelog_entry = extract_changelog_entry(changelog_path, version)
    if not changelog_entry:
        print(
            f"Error: no changelog entry found for version {version} in CHANGELOG.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check that the GitHub Release exists
    try:
        run("gh", ["release", "view", tag])
    except Exception:
        print(f"Error: GitHub Release for {tag} not found.", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"Would update GitHub Release notes for {tag}")
        print(f"Changelog entry:\n{changelog_entry}")
        return

    # Write notes to a temp file to avoid shell escaping issues
    notes_file = f".rlsbl-notes-{int(time.time() * 1000)}.tmp"
    writing_file = notes_file + ".writing"
    try:
        with open(writing_file, "w", encoding="utf-8") as f:
            f.write(changelog_entry)
        os.rename(writing_file, notes_file)
        run("gh", ["release", "edit", tag, "--notes-file", notes_file])
    finally:
        for tmp in (notes_file, writing_file):
            if os.path.exists(tmp):
                os.unlink(tmp)

    print(f"Updated GitHub Release notes for {tag}")
