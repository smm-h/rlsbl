"""Pre-push-check command that verifies CHANGELOG.md contains an entry for the current version before allowing a git push to proceed."""

import fnmatch
import os
import subprocess
import sys

from ..changelog import changes_dir_exists, get_changes_dir, read_unreleased, resolve_hashes
from ..changelog.validate import _RELEASE_MSG_RE, _get_commit_message, _is_release_commit
from ..targets import TARGETS
from ..workspace import find_workspace_root, load_workspace


def _detect_version(dir_path="."):
    """Detect version using registry adapters.

    Returns (version_string, registry_name) or (None, None) if undetectable.
    """
    for name in ("go", "npm", "pypi"):
        reg = TARGETS[name]
        if reg.check_project_exists(dir_path):
            return reg.read_version(dir_path), name
    return None, None



def _check_jsonl_changelog(dir_path, refs):
    """Check JSONL changelog coverage for commits being pushed.

    Verifies that every commit in the push range exists in at least one
    unreleased.jsonl entry's commits list.

    Returns None on success, or an error message string on failure.
    """
    changes_dir = get_changes_dir(dir_path)
    entries = read_unreleased(changes_dir)

    # Get pushed commits from the refs
    pushed_commits = _get_pushed_commits(refs)
    if pushed_commits is None:
        return None  # Could not determine pushed commits -- skip

    # If any pushed commit is a version bump (message matches vX.Y.Z),
    # this is a release push -- validation already ran during rlsbl release.
    for sha in pushed_commits:
        if _is_release_commit(sha):
            msg = _get_commit_message(sha)
            if msg and _RELEASE_MSG_RE.match(msg):
                return None

    # Filter out release infrastructure commits (changelog finalization,
    # etc.) -- these are structural and don't need JSONL coverage.
    non_release_commits = {sha for sha in pushed_commits if not _is_release_commit(sha)}
    if not non_release_commits:
        return None

    if not entries:
        return "unreleased.jsonl has no entries"

    # Collect all hashes from entries and resolve them
    all_hashes = []
    for entry in entries:
        all_hashes.extend(entry.commits)
    resolved = resolve_hashes(all_hashes)
    covered_shas = {full for full in resolved.values() if full is not None}

    missing = []
    for sha in non_release_commits:
        if sha not in covered_shas:
            missing.append(sha[:12])

    if missing:
        return f"JSONL changelog missing coverage for {len(missing)} commit(s): {', '.join(missing[:5])}"

    return None


def _get_pushed_commits(refs):
    """Get the set of commit SHAs being pushed.

    Returns a set of full 40-char SHAs, or None on error.
    """
    zero_sha = "0" * 40
    commits = set()

    for local_sha, remote_sha in refs:
        if local_sha == zero_sha:
            continue  # Branch deletion

        try:
            if remote_sha == zero_sha:
                # New branch: commits not on any remote
                result = subprocess.run(
                    ["git", "log", "--format=%H", local_sha, "--not", "--remotes"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                result = subprocess.run(
                    ["git", "log", "--format=%H", f"{remote_sha}..{local_sha}"],
                    capture_output=True, text=True, timeout=30,
                )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line:
                        commits.add(line)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    return commits


def _parse_stdin_refs():
    """Parse pre-push hook stdin to extract (local_sha, remote_sha) pairs.

    Each line is: <local ref> <local sha> <remote ref> <remote sha>
    Returns a list of (local_sha, remote_sha) tuples, or None if stdin
    is not readable or empty.
    """
    try:
        if sys.stdin.isatty():
            return None
    except (AttributeError, OSError):
        return None

    lines = sys.stdin.read().strip()
    if not lines:
        return None

    refs = []
    for line in lines.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            local_sha = parts[1]
            remote_sha = parts[3]
            refs.append((local_sha, remote_sha))
    return refs if refs else None


def _get_changed_files(refs):
    """Get the list of files changed across all pushed refs.

    Returns a set of file paths relative to the repo root.
    """
    zero_sha = "0" * 40
    changed = set()

    for local_sha, remote_sha in refs:
        if local_sha == zero_sha:
            # Branch being deleted -- nothing to check
            continue

        try:
            if remote_sha == zero_sha:
                # New branch: get files in commits not yet on any remote
                result = subprocess.run(
                    ["git", "log", "--name-only", "--pretty=format:", local_sha,
                     "--not", "--remotes"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                result = subprocess.run(
                    ["git", "diff", "--name-only", f"{remote_sha}..{local_sha}"],
                    capture_output=True, text=True, timeout=30,
                )
            if result.returncode == 0:
                for f in result.stdout.strip().splitlines():
                    f = f.strip()
                    if f:
                        changed.add(f)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If git fails, fall back to single-project behavior
            return None

    return changed


def _file_matches_project(filepath, project):
    """Check whether a file path belongs to a project.

    A file belongs to a project if:
    - It starts with the project's path prefix, OR
    - It matches any of the project's watch globs
    """
    proj_path = project["path"]
    # Normalize: ensure prefix ends with /
    prefix = proj_path.rstrip("/") + "/"
    if filepath == proj_path or filepath.startswith(prefix):
        return True

    for glob_pattern in project.get("watch", []):
        if fnmatch.fnmatch(filepath, glob_pattern):
            return True

    return False


def _affected_projects(changed_files, projects):
    """Determine which projects are affected by the changed files.

    Returns a list of project dicts that have at least one changed file.
    """
    affected = []
    for proj in projects:
        for f in changed_files:
            if _file_matches_project(f, proj):
                affected.append(proj)
                break
    return affected


def _run_monorepo_check(workspace_root, projects, changed_files, refs=None):
    """Check changelogs for all affected monorepo projects.

    Returns exit code 0 on success, 1 if any project fails.
    """
    affected = _affected_projects(changed_files, projects)
    if not affected:
        sys.exit(0)

    failures = []
    for proj in affected:
        proj_dir = os.path.join(workspace_root, proj["path"])

        if not changes_dir_exists(proj_dir):
            continue  # JSONL not set up for this project -- skip
        if refs is None:
            continue  # No refs available -- skip
        error = _check_jsonl_changelog(proj_dir, refs)

        if error:
            version, _ = _detect_version(proj_dir)
            failures.append((proj["name"], version or "?", error))

    if not failures:
        sys.exit(0)

    for name, version, error in failures:
        print(f"Error: {name}: {error}.", file=sys.stderr)
        print(f"Add JSONL changelog entries covering all pushed commits for {name}.",
              file=sys.stderr)
    sys.exit(1)


def run_cmd(registry, args, flags):
    """Check that CHANGELOG.md has an entry for the current project version.

    In monorepo mode (when a workspace root is detected), parses the pushed
    ref range from stdin to determine which projects are affected, then checks
    each affected project's changelog independently.

    In single-project mode, checks the current directory's changelog.

    Exits 1 if any changelog entry is missing; exits 0 silently on success.
    """
    # Detect monorepo context
    workspace_root = find_workspace_root(".")
    if workspace_root:
        refs = _parse_stdin_refs()
        if refs is not None:
            changed_files = _get_changed_files(refs)
            if changed_files is not None:
                projects = load_workspace(workspace_root)
                _run_monorepo_check(workspace_root, projects, changed_files, refs=refs)
                # _run_monorepo_check always calls sys.exit, so this is unreachable

    # Single-project fallback
    if not changes_dir_exists("."):
        # JSONL changelog not set up -- warn but don't block
        print("Warning: JSONL changelog not set up. Run 'rlsbl scaffold --update' to create .rlsbl/changes/", file=sys.stderr)
        sys.exit(0)

    # JSONL mode: check commit coverage
    refs = _parse_stdin_refs()
    if refs is not None:
        error = _check_jsonl_changelog(".", refs)
        if error is None:
            sys.exit(0)
        print(f"Error: {error}.", file=sys.stderr)
        print("Add JSONL changelog entries covering all pushed commits.", file=sys.stderr)
        sys.exit(1)
    # No refs available (not called from pre-push hook) -- skip
    sys.exit(0)
