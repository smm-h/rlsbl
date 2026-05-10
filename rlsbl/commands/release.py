"""Release command: bump version, commit, push, create GitHub Release."""

import os
import sys
import time

from ..config import read_json_config, should_tag
from ..lock import acquire_lock, release_lock
from ..targets import TARGETS
from ..tagging import ensure_github_topic, ensure_npm_keyword, ensure_pypi_keyword
from ..workspace import find_workspace_root, load_workspace, resolve_project
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


def resolve_release_targets(primary, flags):
    """Compute the effective set of secondary target names for this release.

    Precedence:
      1. Start with the baseline from .rlsbl/config.json "release_targets" list.
         If absent, fall back to auto-detect (all targets that detect(".")).
      2. Apply --include to add targets, --exclude to remove targets.
      3. The primary target is always excluded from the secondary set
         (it's handled separately by the main release flow).

    Returns a set of target name strings.
    """
    from ..targets import TARGETS as ALL_TARGETS

    config = read_json_config(os.path.join(".rlsbl", "config.json"))
    configured = config.get("release_targets")

    if configured is not None:
        # Baseline from config -- only include targets that actually exist
        baseline = {t for t in configured if t in ALL_TARGETS}
    else:
        # Auto-detect: all targets that are present
        baseline = {
            name for name, t in ALL_TARGETS.items()
            if t.detect(".")
        }

    # Apply --include (comma-separated or repeated)
    include_raw = flags.get("include")
    if include_raw:
        for name in include_raw.split(","):
            name = name.strip()
            if name:
                baseline.add(name)

    # Apply --exclude (comma-separated or repeated)
    exclude_raw = flags.get("exclude")
    if exclude_raw:
        for name in exclude_raw.split(","):
            name = name.strip()
            if name:
                baseline.discard(name)

    # Never include the primary target in the secondary set
    baseline.discard(primary)

    return baseline


def run_cmd(registry, args, flags):
    """Release command handler.

    Bumps version, commits, pushes, and creates a GitHub Release.
    """
    quiet = flags.get("quiet", False)

    def log(msg):
        if not quiet:
            print(msg)

    reg = TARGETS[registry]

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

    # Remote-ahead check: abort if local branch is behind origin
    if not flags.get("skip-remote-check"):
        try:
            run("git", ["fetch", "origin", "--quiet"])
        except Exception:
            # Network failure or no remote — warn but don't block the release
            print("Warning: could not fetch from origin. Skipping remote-ahead check.", file=sys.stderr)
        else:
            try:
                behind_count = int(run("git", ["rev-list", "--count", f"HEAD..origin/{branch}"]))
            except Exception:
                # Remote branch may not exist yet — not an error
                behind_count = 0
            if behind_count > 0:
                print(
                    f"Error: local branch is {behind_count} commit(s) behind origin/{branch}. Pull before releasing.",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Monorepo context detection
    monorepo_root = find_workspace_root(".")
    monorepo_name = None
    monorepo_project_path = None

    if monorepo_root:
        project = resolve_project(monorepo_root, ".")
        if project is None:
            print("Error: current directory is inside a monorepo but not inside any project.", file=sys.stderr)
            print("Run 'rlsbl monorepo status' to see registered projects.", file=sys.stderr)
            sys.exit(1)
        monorepo_name = project["name"]
        monorepo_project_path = project["path"]
        # Change to monorepo root so all paths (git and filesystem) are
        # relative to the repo root, matching git's expectations.
        os.chdir(monorepo_root)
        log(f"Monorepo project: {monorepo_name} ({monorepo_project_path})")

    # Scoped version directory: project subdir in monorepo, repo root otherwise
    version_dir = monorepo_project_path if monorepo_name else "."

    # Get target instance for tag_format/build/publish
    target = TARGETS[registry]

    # Current version
    current_version = reg.read_version(version_dir)
    log(f"Current version: {current_version}")

    # If the current version has never been tagged, release it as-is (bootstrap)
    if monorepo_name:
        current_tag = target.monorepo_tag_format(monorepo_name, current_version)
    else:
        current_tag = target.tag_format(current_version)
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
        if monorepo_name:
            tag = target.monorepo_tag_format(monorepo_name, new_version)
        else:
            tag = target.tag_format(new_version)
        log(f"New version: {new_version} ({bump_type})")

    # Check tag doesn't already exist
    tag_output = run("git", ["tag", "-l", tag])
    if len(tag_output) > 0:
        print(f'Error: tag "{tag}" already exists.', file=sys.stderr)
        sys.exit(1)

    # Validate changelog entry
    changelog_path = os.path.join(version_dir, "CHANGELOG.md")
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
    pre_release_script = os.path.join(version_dir, ".rlsbl", "hooks", "pre-release.sh")
    if os.path.exists(pre_release_script):
        log("Running pre-release hook...")
        try:
            env = os.environ.copy()
            env["RLSBL_VERSION"] = new_version
            run("bash", [pre_release_script], env=env)
        except Exception:
            print("Error: pre-release hook failed. Fix the issues and try again.", file=sys.stderr)
            sys.exit(1)

    # Commit message: scoped in monorepo mode, plain tag otherwise
    commit_msg = f"{monorepo_name}: release v{new_version}" if monorepo_name else tag

    # Dry run: print summary and return
    if flags.get("dry-run", False):
        log("\n--- Dry run summary ---")
        log(f"Registry:  {registry}")
        if monorepo_name:
            log(f"Project:   {monorepo_name} ({monorepo_project_path})")
        if bump_type:
            log(f"Bump:      {current_version} -> {new_version} ({bump_type})")
        else:
            log(f"Version:   {new_version} (first release)")
        log(f"Tag:       {tag}")
        log(f"Commit:    {commit_msg}")
        log(f"Branch:    {branch}")
        # Show other version files that would be synced
        other_files = []
        for name, other_reg in TARGETS.items():
            if name == registry:
                continue
            if other_reg.check_project_exists(version_dir):
                other_file = other_reg.get_version_file()
                if other_file:
                    other_files.append(other_file)
        if other_files:
            log(f"Sync to:   {', '.join(other_files)}")
        # Show subtree publishing info in dry-run
        if monorepo_name:
            try:
                projects = load_workspace(".")
                proj_dict = next((p for p in projects if p["name"] == monorepo_name), None)
                subtree_remote = proj_dict.get("subtree_remote") if proj_dict else None
            except Exception:
                subtree_remote = None
            if subtree_remote:
                plain_tag = target.tag_format(new_version)
                log(f"Subtree:   {subtree_remote} (tag: {plain_tag})")
        log(f"Changelog:\n{changelog_entry}")
        log("--- No changes made ---")
        return

    # Resolve which secondary targets participate in this release
    secondary_targets = resolve_release_targets(registry, flags)

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        _run_release_mutating(
            registry, reg, flags, quiet, log, new_version, current_version,
            bump_type, tag, branch, changelog_entry, target,
            secondary_targets=secondary_targets,
            monorepo_name=monorepo_name,
            monorepo_project_path=monorepo_project_path,
            version_dir=version_dir,
            commit_msg=commit_msg,
        )
    finally:
        release_lock()


def _run_release_mutating(registry, reg, flags, quiet, log, new_version, current_version,
                          bump_type, tag, branch, changelog_entry, target,
                          secondary_targets=None, monorepo_name=None,
                          monorepo_project_path=None,
                          version_dir=".", commit_msg=None):
    """Inner release logic that runs under the advisory lock (mutating phase)."""
    if commit_msg is None:
        commit_msg = tag

    def vpath(filename):
        """Join filename with version_dir and normalize (e.g. './x' -> 'x')."""
        return os.path.normpath(os.path.join(version_dir, filename))

    # Pre-compute which files will be modified
    version_file = reg.get_version_file()
    files_to_commit = []
    if version_file:
        files_to_commit.append(vpath(version_file))
    # Sync version to other registries
    for name, other_reg in TARGETS.items():
        if name == registry:
            continue
        if other_reg.check_project_exists(version_dir):
            other_file = other_reg.get_version_file()
            if other_file:
                files_to_commit.append(vpath(other_file))

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
            log(f"Updated version in {vpath(version_file)}")

        # Sync version to all other recognized version files
        for name, other_reg in TARGETS.items():
            if name == registry:
                continue
            if other_reg.check_project_exists(version_dir):
                other_file = other_reg.get_version_file()
                if other_file:
                    other_reg.write_version(version_dir, new_version)
                    log(f"Synced version to {vpath(other_file)}")

    # Ecosystem tagging: add keyword to manifests if enabled
    if should_tag(flags):
        try:
            if TARGETS["npm"].check_project_exists(version_dir):
                if ensure_npm_keyword(version_dir, quiet=quiet):
                    pkg_path = vpath("package.json")
                    if pkg_path not in files_to_commit:
                        files_to_commit.append(pkg_path)
        except Exception:
            pass
        try:
            if TARGETS["pypi"].check_project_exists(version_dir):
                if ensure_pypi_keyword(version_dir, quiet=quiet):
                    pyproject_path = vpath("pyproject.toml")
                    if pyproject_path not in files_to_commit:
                        files_to_commit.append(pyproject_path)
        except Exception:
            pass

    # Update .rlsbl/version marker so it's included in the release commit
    rlsbl_version_marker = vpath(os.path.join(".rlsbl", "version"))
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

    # Commit if any of the files we track actually have changes.
    # Don't use is_clean_tree() as a proxy — the advisory lock file (.rlsbl/lock)
    # makes the tree appear dirty even when no release-relevant files changed.
    def has_staged_or_modified(paths):
        """Check if any of the given paths have actual changes vs the index."""
        for p in paths:
            diff = run("git", ["diff", "--name-only", "--", p]) if os.path.exists(p) else ""
            status = run("git", ["status", "--porcelain", "--", p])
            if diff or status:
                return True
        return False

    needs_commit = new_version != current_version or has_staged_or_modified(files_to_commit)
    if files_to_commit and needs_commit:
        commit_tool = find_commit_tool()
        if commit_tool == "safegit":
            run(commit_tool, ["commit", "-m", commit_msg, "--", *files_to_commit])
        else:
            run("git", ["add", *files_to_commit])
            run("git", ["commit", "-m", commit_msg])
        log(f"Committed: {commit_msg}")
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

    # Subtree publishing for monorepo projects with subtree_remote configured
    if monorepo_name and monorepo_project_path:
        try:
            projects = load_workspace(".")
            proj_dict = None
            for p in projects:
                if p["name"] == monorepo_name:
                    proj_dict = p
                    break
            subtree_remote = proj_dict.get("subtree_remote") if proj_dict else None
        except Exception:
            subtree_remote = None

        if subtree_remote:
            plain_tag = target.tag_format(new_version)
            log(f"Publishing subtree to {subtree_remote}...")
            try:
                run("git", ["subtree", "split", f"--prefix={monorepo_project_path}", "-b", "_rlsbl-subtree-tmp"])
                run("git", ["push", subtree_remote, f"_rlsbl-subtree-tmp:refs/tags/{plain_tag}"])
                run("git", ["push", subtree_remote, "_rlsbl-subtree-tmp:refs/heads/main"])
                log(f"Subtree published: {plain_tag} -> {subtree_remote}")
            except Exception as e:
                print(f"Warning: subtree push failed: {e}", file=sys.stderr)
            finally:
                try:
                    run("git", ["branch", "-D", "_rlsbl-subtree-tmp"])
                except Exception:
                    pass

    # Publish step (no-op for npm/pypi/go targets)
    try:
        target.publish(version_dir, new_version)
    except Exception as e:
        print(f"Warning: target publish step failed: {e}", file=sys.stderr)

    # Multi-target: run build/publish for secondary targets resolved earlier
    if secondary_targets:
        from ..targets import TARGETS as ALL_TARGETS
        for sec_name in sorted(secondary_targets):
            sec_target = ALL_TARGETS.get(sec_name)
            if sec_target is None:
                continue
            try:
                sec_target.build(version_dir, new_version)
            except Exception as e:
                print(f"Warning: {sec_name} target build failed: {e}", file=sys.stderr)
            try:
                sec_target.publish(version_dir, new_version)
            except Exception as e:
                print(f"Warning: {sec_name} target publish failed: {e}", file=sys.stderr)

    # Ecosystem tagging: add GitHub topic after release is created
    if should_tag(flags):
        ensure_github_topic(quiet=quiet)

    # Run post-release hook if present (non-fatal: release is already complete)
    post_release_script = os.path.join(version_dir, ".rlsbl", "hooks", "post-release.sh")
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
