"""Release command: bump version, commit, push, create GitHub Release."""

import os
import sys
import time

from ..registries import REGISTRIES
from ..utils import (
    bump_version,
    check_gh_auth,
    check_gh_installed,
    extract_changelog_entry,
    find_commit_tool,
    get_current_branch,
    is_clean_tree,
    push_if_needed,
    run,
)

VALID_BUMP_TYPES = ("patch", "minor", "major")


def run_cmd(registry, args, flags):
    """Release command handler.

    Bumps version, commits, pushes, and creates a GitHub Release.
    """
    quiet = flags.get("quiet", False)

    def log(msg):
        if not quiet:
            print(msg)

    reg = REGISTRIES[registry]

    # Check prerequisites
    if not check_gh_installed():
        print("Error: gh CLI is not installed. Install it from https://cli.github.com", file=sys.stderr)
        sys.exit(1)
    if not check_gh_auth():
        print('Error: gh CLI is not authenticated. Run "gh auth login" first.', file=sys.stderr)
        sys.exit(1)

    # Clean working tree
    if not is_clean_tree():
        print("Error: working tree is not clean. Commit your changes first.", file=sys.stderr)
        sys.exit(1)

    # Branch check
    branch = get_current_branch()
    if branch not in ("main", "master"):
        print(f'Warning: you are on branch "{branch}", not main/master.', file=sys.stderr)

    # Current version
    current_version = reg.read_version(".")
    log(f"Current version: {current_version}")

    # Bump type
    bump_type = args[0] if args else "patch"
    if bump_type not in VALID_BUMP_TYPES:
        print(
            f'Error: invalid bump type "{bump_type}". Use: {", ".join(VALID_BUMP_TYPES)}',
            file=sys.stderr,
        )
        sys.exit(1)

    # Compute new version
    new_version = bump_version(current_version, bump_type)
    tag = f"v{new_version}"
    log(f"New version: {new_version} ({bump_type})")

    # Check tag doesn't already exist
    tag_output = run("git", ["tag", "-l", tag])
    if len(tag_output) > 0:
        print(f'Error: tag "{tag}" already exists.', file=sys.stderr)
        sys.exit(1)

    # Validate changelog entry
    changelog_path = os.path.join(".", "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        print(
            f"Error: CHANGELOG.md not found. Create one with a ## {new_version} section.",
            file=sys.stderr,
        )
        sys.exit(1)
    changelog_entry = extract_changelog_entry(changelog_path, new_version)
    if not changelog_entry:
        print(
            f"Error: no changelog entry found for version {new_version} in CHANGELOG.md.",
            file=sys.stderr,
        )
        print(f'Add a "## {new_version}" section describing the changes.', file=sys.stderr)
        sys.exit(1)
    if len(changelog_entry.strip()) < 10:
        print(
            f"Warning: changelog entry for {new_version} is very short. Consider adding more detail.",
            file=sys.stderr,
        )

    # Run pre-release hook if present
    pre_release_script = os.path.join(".", "scripts", "pre-release.sh")
    if os.path.exists(pre_release_script):
        log("Running pre-release hook...")
        try:
            run("bash", [pre_release_script])
        except Exception:
            print("Error: pre-release hook failed. Fix the issues and try again.", file=sys.stderr)
            sys.exit(1)

    # Dry run: print summary and return
    if flags.get("dry-run", False):
        log("\n--- Dry run summary ---")
        log(f"Registry:  {registry}")
        log(f"Bump:      {current_version} -> {new_version} ({bump_type})")
        log(f"Tag:       {tag}")
        log(f"Branch:    {branch}")
        # Show other version files that would be synced
        other_files = []
        for name, other_reg in REGISTRIES.items():
            if name == registry:
                continue
            if other_reg.check_project_exists("."):
                other_files.append(other_reg.get_version_file())
        if other_files:
            log(f"Sync to:   {', '.join(other_files)}")
        log(f"Changelog:\n{changelog_entry}")
        log("--- No changes made ---")
        return

    # Write new version to the primary registry file
    version_file = reg.get_version_file()
    reg.write_version(".", new_version)
    log(f"Updated version in {version_file}")

    # Sync version to all other recognized version files
    files_to_commit = [version_file]
    for name, other_reg in REGISTRIES.items():
        if name == registry:
            continue
        if other_reg.check_project_exists("."):
            other_reg.write_version(".", new_version)
            other_file = other_reg.get_version_file()
            files_to_commit.append(other_file)
            log(f"Synced version to {other_file}")

    # Commit all bumped version files together
    commit_tool = find_commit_tool()
    if commit_tool == "safegit":
        run(commit_tool, ["commit", "-m", tag, "--", *files_to_commit])
    else:
        run("git", ["add", *files_to_commit])
        run("git", ["commit", "-m", tag])
    log(f"Committed: {tag}")

    # Create local git tag
    run("git", ["tag", tag])
    log(f"Tagged: {tag}")

    # Push commits and tag
    push_if_needed(branch)
    run("git", ["push", "origin", tag])
    log(f"Pushed to origin/{branch}")

    # Create GitHub Release using a temp notes file
    notes_file = f".rlsbl-notes-{int(time.time() * 1000)}.tmp"
    writing_file = notes_file + ".writing"
    try:
        with open(writing_file, "w", encoding="utf-8") as f:
            f.write(changelog_entry)
        os.rename(writing_file, notes_file)
        run("gh", ["release", "create", tag, "--title", tag, "--notes-file", notes_file])
        log(f"Created GitHub Release: {tag}")
    finally:
        # Clean up temp files even if gh release fails
        for tmp in (notes_file, writing_file):
            if os.path.exists(tmp):
                os.unlink(tmp)

    log(f"\nRelease {new_version} complete!")
