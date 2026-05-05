"""Release command: bump version, commit, push, create GitHub Release."""

import os
import sys
import time

from ..config import should_tag
from ..lock import acquire_lock, release_lock
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


def parse_porcelain_paths(porcelain_output):
    """Parse file paths from `git status --porcelain` output.

    Handles the case where run() strips stdout, potentially removing a
    leading space from the first line. Uses lstrip().split(None, 1) to
    robustly extract the status code and path regardless.

    Returns a set of file paths found in the output.
    """
    dirty_files = set()
    for line in porcelain_output.splitlines():
        parts = line.lstrip().split(None, 1)
        if len(parts) < 2:
            continue
        # Handle rename notation: "R old -> new"
        file_path = parts[1].split(" -> ")[-1]
        dirty_files.add(file_path)
    return dirty_files


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

    # Derive scope_name from --scope flag for tag_format
    scope = flags.get("scope")
    scope_name = os.path.basename(scope.rstrip("/")) if scope else None

    # Get target instance for tag_format/build/publish
    from ..targets import TARGETS
    target = TARGETS[registry]

    # Determine if this is a scoped (subdir) release
    is_scoped = scope is not None and target.scope == "subdir"

    # Warn if --scope is used with a root-scoped target (it has no effect)
    if scope is not None and target.scope != "subdir":
        print(f"Warning: --scope is ignored for root-scoped target '{target.name}'", file=sys.stderr)

    # Batch mode detection: scope ends with "/" or is a directory with multiple
    # plugin.toml files
    if is_scoped:
        if scope.endswith("/") or (
            os.path.isdir(scope) and not os.path.exists(os.path.join(scope, "plugin.toml"))
        ):
            print("Batch release not yet implemented", file=sys.stderr)
            sys.exit(1)

    # version_dir: where to read/write version (scope path for subdir, "." otherwise)
    version_dir = scope if is_scoped else "."

    # Validate that the scope directory actually exists
    if is_scoped and not os.path.isdir(version_dir):
        print(f"Error: scope directory does not exist: {version_dir}", file=sys.stderr)
        sys.exit(1)

    # Current version
    current_version = reg.read_version(version_dir)
    log(f"Current version: {current_version}")

    # If the current version has never been tagged, release it as-is (bootstrap)
    current_tag = target.tag_format(scope_name, current_version)
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
        tag = target.tag_format(scope_name, new_version)
        log(f"New version: {new_version} ({bump_type})")

    # Check tag doesn't already exist
    tag_output = run("git", ["tag", "-l", tag])
    if len(tag_output) > 0:
        print(f'Error: tag "{tag}" already exists.', file=sys.stderr)
        sys.exit(1)

    # Validate changelog entry -- for scoped releases, check scope dir first
    if is_scoped:
        scoped_changelog = os.path.join(scope, "CHANGELOG.md")
        if os.path.exists(scoped_changelog):
            changelog_path = scoped_changelog
        else:
            changelog_path = os.path.join(".", "CHANGELOG.md")
    else:
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
    pre_release_script = os.path.join(".", ".rlsbl", "hooks", "pre-release.sh")
    if os.path.exists(pre_release_script):
        log("Running pre-release hook...")
        try:
            env = os.environ.copy()
            env["RLSBL_VERSION"] = new_version
            run("bash", [pre_release_script], env=env)
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
        if is_scoped:
            log(f"Scope:     {scope}")
        # Show other version files that would be synced (skip for scoped releases)
        if not is_scoped:
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

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        _run_release_mutating(
            registry, reg, flags, quiet, log, new_version, current_version,
            bump_type, tag, branch, changelog_entry, target,
            is_scoped=is_scoped, version_dir=version_dir, scope=scope,
        )
    finally:
        release_lock()


def _run_release_mutating(registry, reg, flags, quiet, log, new_version, current_version,
                          bump_type, tag, branch, changelog_entry, target,
                          is_scoped=False, version_dir=".", scope=None):
    """Inner release logic that runs under the advisory lock (mutating phase)."""
    # Pre-compute which files will be modified
    version_file = reg.get_version_file()
    files_to_commit = []
    if version_file:
        # For scoped releases, prefix the version file with the scope path
        if is_scoped and scope:
            files_to_commit.append(os.path.join(scope, version_file))
        else:
            files_to_commit.append(version_file)
    # Sync version to other registries only for non-scoped releases
    if not is_scoped:
        for name, other_reg in REGISTRIES.items():
            if name == registry:
                continue
            if other_reg.check_project_exists("."):
                other_file = other_reg.get_version_file()
                if other_file:
                    files_to_commit.append(other_file)

    # Confirmation prompt (skip with --yes)
    if not flags.get("yes"):
        bump_label = f" ({bump_type})" if bump_type else ""
        print(f"\nAbout to release {new_version}{bump_label} on {branch}")
        print(f"  Tag: {tag}")
        if files_to_commit:
            print(f"  Files: {', '.join(files_to_commit)}")
        else:
            print("  Files: (none -- version is the git tag)")
        if should_tag(flags):
            print("  Will add 'rlsbl' keyword to project manifests")
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
            reg.write_version(version_dir, new_version)
            if is_scoped and scope:
                log(f"Updated version in {os.path.join(scope, version_file)}")
                # write_version may also modify pyproject.toml (e.g. CodehomeTarget);
                # ensure it's included in files_to_commit
                scoped_pyproject = os.path.join(scope, "pyproject.toml")
                if os.path.exists(scoped_pyproject) and scoped_pyproject not in files_to_commit:
                    files_to_commit.append(scoped_pyproject)
            else:
                log(f"Updated version in {version_file}")

        # Sync version to all other recognized version files (skip for scoped releases)
        if not is_scoped:
            for name, other_reg in REGISTRIES.items():
                if name == registry:
                    continue
                if other_reg.check_project_exists("."):
                    other_file = other_reg.get_version_file()
                    if other_file:
                        other_reg.write_version(".", new_version)
                        log(f"Synced version to {other_file}")

    # Ecosystem tagging: add keyword to manifests if enabled (skip for scoped releases)
    if should_tag(flags) and not is_scoped:
        try:
            if REGISTRIES["npm"].check_project_exists("."):
                if ensure_npm_keyword(".", quiet=quiet):
                    if "package.json" not in files_to_commit:
                        files_to_commit.append("package.json")
        except Exception:
            pass
        try:
            if REGISTRIES["pypi"].check_project_exists("."):
                if ensure_pypi_keyword(".", quiet=quiet):
                    if "pyproject.toml" not in files_to_commit:
                        files_to_commit.append("pyproject.toml")
        except Exception:
            pass

    # Update .rlsbl/version marker so it's included in the release commit
    rlsbl_version_marker = os.path.join(".rlsbl", "version")
    if os.path.exists(os.path.dirname(rlsbl_version_marker)):
        try:
            from .. import __version__ as rlsbl_ver
            with open(rlsbl_version_marker, "w") as f:
                f.write(rlsbl_ver + "\n")
            if rlsbl_version_marker not in files_to_commit:
                files_to_commit.append(rlsbl_version_marker)
        except Exception:
            pass

    # Build step (no-op for npm/pypi/go targets)
    try:
        target.build(version_dir, new_version)
    except Exception as e:
        print(f"Warning: target build step failed: {e}", file=sys.stderr)

    # Re-check working tree: abort if files outside our expected set were modified
    # (guards against concurrent processes dirtying the tree after our initial check)
    dirty_output = run("git", ["status", "--porcelain"])
    if dirty_output:
        dirty_files = parse_porcelain_paths(dirty_output)
        expected_files = set(files_to_commit)
        expected_files.add(os.path.join(".rlsbl", "lock"))
        unexpected = dirty_files - expected_files
        if unexpected:
            unexpected_list = ", ".join(sorted(unexpected))
            print(
                f"Unexpected modified files detected (possible concurrent change): {unexpected_list}. Aborting release.",
                file=sys.stderr,
            )
            sys.exit(1)

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

    # Publish step (no-op for npm/pypi/go targets)
    try:
        target.publish(version_dir, new_version)
    except Exception as e:
        print(f"Warning: target publish step failed: {e}", file=sys.stderr)

    # Ecosystem tagging: add GitHub topic after release is created (skip for scoped)
    if should_tag(flags) and not is_scoped:
        ensure_github_topic(quiet=quiet)

    # Run post-release hook if present (non-fatal: release is already complete)
    post_release_script = os.path.join(".", ".rlsbl", "hooks", "post-release.sh")
    if os.path.exists(post_release_script):
        log("Running post-release hook...")
        try:
            env = os.environ.copy()
            env["RLSBL_VERSION"] = new_version
            run("bash", [post_release_script], env=env)
        except Exception as e:
            print(f"Warning: post-release hook failed: {e}", file=sys.stderr)

    # Hint: how to watch CI for this release
    try:
        commit_sha = run("git", ["rev-parse", "HEAD"])
        log(f"Watch CI: rlsbl watch {commit_sha}")
    except Exception:
        pass

    log(f"\nRelease {new_version} complete!")
