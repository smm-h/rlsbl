"""Release command: bump version, commit, push, create GitHub Release."""

import os
import sys
import time

from ..config import should_tag
from ..registries import REGISTRIES
from ..tagging import ensure_github_topic, ensure_npm_keyword, ensure_pypi_keyword
from ..utils import (
    bump_version,
    check_gh_auth,
    check_gh_installed,
    extract_changelog_entry,
    find_commit_tool,
    get_current_branch,
    get_push_timeout,
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

    # If the current version has never been tagged, release it as-is (bootstrap)
    current_tag = f"v{current_version}"
    current_tag_exists = len(run("git", ["tag", "-l", current_tag])) > 0

    if not current_tag_exists:
        new_version = current_version
        bump_type = None
        tag = current_tag
        if args:
            log(f"First release: releasing {new_version} as-is (bump type ignored)")
        else:
            log(f"First release: {new_version}")
    else:
        bump_type = args[0] if args else "patch"
        if bump_type not in VALID_BUMP_TYPES:
            print(
                f'Error: invalid bump type "{bump_type}". Use: {", ".join(VALID_BUMP_TYPES)}',
                file=sys.stderr,
            )
            sys.exit(1)

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
        if bump_type:
            log(f"Bump:      {current_version} -> {new_version} ({bump_type})")
        else:
            log(f"Version:   {new_version} (first release)")
        log(f"Tag:       {tag}")
        log(f"Branch:    {branch}")
        # Show other version files that would be synced
        other_files = []
        for name, other_reg in REGISTRIES.items():
            if name == registry:
                continue
            if other_reg.check_project_exists("."):
                other_file = other_reg.get_version_file()
                if other_file:
                    other_files.append(other_file)
        if other_files:
            log(f"Sync to:   {', '.join(other_files)}")
        log(f"Changelog:\n{changelog_entry}")
        log("--- No changes made ---")
        return

    # Pre-compute which files will be modified
    version_file = reg.get_version_file()
    files_to_commit = []
    if version_file:
        files_to_commit.append(version_file)
    for name, other_reg in REGISTRIES.items():
        if name == registry:
            continue
        if other_reg.check_project_exists("."):
            other_file = other_reg.get_version_file()
            if other_file:
                files_to_commit.append(other_file)

    # Ecosystem tagging: add keyword to manifests if enabled
    if should_tag(flags):
        try:
            if REGISTRIES["npm"].check_project_exists("."):
                if ensure_npm_keyword("."):
                    if "package.json" not in files_to_commit:
                        files_to_commit.append("package.json")
        except Exception:
            pass
        try:
            if REGISTRIES["pypi"].check_project_exists("."):
                if ensure_pypi_keyword("."):
                    if "pyproject.toml" not in files_to_commit:
                        files_to_commit.append("pyproject.toml")
        except Exception:
            pass

    # Confirmation prompt (skip with --yes)
    if not flags.get("yes"):
        bump_label = f" ({bump_type})" if bump_type else ""
        print(f"\nAbout to release {new_version}{bump_label} on {branch}")
        print(f"  Tag: {tag}")
        if files_to_commit:
            print(f"  Files: {', '.join(files_to_commit)}")
        else:
            print("  Files: (none -- version is the git tag)")
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    # Write new version to version files (skip if version didn't change, e.g. first release)
    if new_version != current_version:
        if version_file:
            reg.write_version(".", new_version)
            log(f"Updated version in {version_file}")

        # Sync version to all other recognized version files
        for name, other_reg in REGISTRIES.items():
            if name == registry:
                continue
            if other_reg.check_project_exists("."):
                other_file = other_reg.get_version_file()
                if other_file:
                    other_reg.write_version(".", new_version)
                    log(f"Synced version to {other_file}")

    # Commit if anything was actually modified (version bump or tagging)
    needs_commit = new_version != current_version or not is_clean_tree()
    if files_to_commit and needs_commit:
        commit_tool = find_commit_tool()
        if commit_tool == "safegit":
            run(commit_tool, ["commit", "-m", tag, "--", *files_to_commit])
        else:
            run("git", ["add", *files_to_commit])
            run("git", ["commit", "-m", tag])
        log(f"Committed: {tag}")
    elif not needs_commit:
        log("No changes to commit")

    # Create local git tag
    run("git", ["tag", tag])
    log(f"Tagged: {tag}")

    # Push commits and tag
    push_timeout = get_push_timeout()
    if push_timeout != 120:
        log(f"Push timeout: {push_timeout}s (from RLSBL_PUSH_TIMEOUT)")
    push_if_needed(branch)
    run("git", ["push", "origin", tag], timeout=push_timeout)
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

    # Ecosystem tagging: add GitHub topic after release is created
    if should_tag(flags):
        ensure_github_topic()

    log(f"\nRelease {new_version} complete!")
