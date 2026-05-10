"""Doctor command: diagnose and repair release state."""

import os
import subprocess
import sys

from ..lock import is_stale
from ..targets import TARGETS, detect_targets
from ..targets.utils import normalize_go, normalize_npm, normalize_pypi
from ..utils import (
    check_gh_auth,
    check_gh_installed,
    extract_changelog_entry,
    get_current_branch,
    run,
)


def _check_stale_lock():
    """Check for stale lock files."""
    if is_stale():
        return ("WARN", "stale lock file exists at .rlsbl/lock")
    return ("PASS", "no lock file")


def _check_version_consistency():
    """Check that all detected targets report the same version."""
    target_names = detect_targets(".")
    if not target_names:
        return ("WARN", "no targets detected")

    versions = {}
    for name in target_names:
        target = TARGETS[name]
        try:
            v = target.read_version(".")
            versions[name] = v
        except Exception:
            versions[name] = None

    unique = set(v for v in versions.values() if v is not None)
    if len(unique) == 0:
        return ("WARN", "no targets reported a version")
    if len(unique) > 1:
        detail = ", ".join(f"{n}={v}" for n, v in versions.items() if v is not None)
        return ("FAIL", f"version mismatch: {detail}")

    version = unique.pop()
    return ("PASS", f"{version} across {len(target_names)} target(s)")


def _normalize_name(target_name, raw_name):
    """Normalize a package name using the appropriate target normalizer."""
    normalizers = {
        "npm": normalize_npm,
        "pypi": normalize_pypi,
        "go": normalize_go,
    }
    normalizer = normalizers.get(target_name, str.lower)
    return normalizer(raw_name)


def _check_name_consistency():
    """Check that all detected targets report the same package name."""
    target_names = detect_targets(".")
    if not target_names:
        return ("WARN", "no targets detected")

    names = {}
    for name in target_names:
        target = TARGETS[name]
        try:
            n = target.read_name(".")
            names[name] = n
        except Exception:
            names[name] = None

    # Targets that returned a name
    have_name = {k: v for k, v in names.items() if v is not None}
    if not have_name:
        return ("WARN", "no targets reported a name")

    # Warn about targets that couldn't provide a name
    missing = [k for k, v in names.items() if v is None]

    normalized = {k: _normalize_name(k, v) for k, v in have_name.items()}
    unique = set(normalized.values())

    if len(unique) == 1:
        raw_name = next(iter(have_name.values()))
        msg = f"{raw_name} across {len(target_names)} target(s)"
        if missing:
            msg += f" (no name from: {', '.join(missing)})"
        return ("PASS", msg)

    detail = ", ".join(f"{k}={v}" for k, v in have_name.items())
    return ("WARN", f"name mismatch: {detail}")


def _check_license_consistency():
    """Check that all detected targets report the same license."""
    target_names = detect_targets(".")
    if not target_names:
        return ("PASS", "no targets declare a license")

    licenses = {}
    for name in target_names:
        target = TARGETS[name]
        try:
            meta = target.read_metadata(".")
            if "license" in meta:
                licenses[name] = meta["license"]
        except Exception:
            pass

    if len(licenses) == 0:
        return ("PASS", "no targets declare a license")
    if len(licenses) < 2:
        return ("PASS", f"only {len(licenses)} target(s) declare a license")

    unique = set(v.lower() for v in licenses.values())
    if len(unique) == 1:
        license_val = next(iter(licenses.values()))
        return ("PASS", f"{license_val} across {len(licenses)} target(s)")

    detail = ", ".join(f"{k}={v}" for k, v in licenses.items())
    return ("WARN", f"license mismatch: {detail}")


def _check_description_consistency():
    """Check that all detected targets report the same description."""
    target_names = detect_targets(".")
    if not target_names:
        return ("PASS", "no targets declare a description")

    descriptions = {}
    for name in target_names:
        target = TARGETS[name]
        try:
            meta = target.read_metadata(".")
            if "description" in meta:
                descriptions[name] = meta["description"]
        except Exception:
            pass

    if len(descriptions) == 0:
        return ("PASS", "no targets declare a description")
    if len(descriptions) < 2:
        return ("PASS", f"only {len(descriptions)} target(s) declare a description")

    unique = set(descriptions.values())
    if len(unique) == 1:
        desc_val = next(iter(descriptions.values()))
        return ("PASS", f"{desc_val} across {len(descriptions)} target(s)")

    detail = ", ".join(f"{k}={v}" for k, v in descriptions.items())
    return ("WARN", f"description mismatch: {detail}")


def _check_local_tag(tag):
    """Check if a git tag exists locally."""
    output = run("git", ["tag", "-l", tag])
    if output:
        return ("PASS", f"{tag} exists")
    return ("WARN", f"{tag} not found locally")


def _check_remote_tag(tag):
    """Check if a git tag exists on the remote."""
    output = run("git", ["ls-remote", "--tags", "origin", tag])
    if output:
        return ("PASS", f"{tag} on origin")
    return ("WARN", f"{tag} not found on origin")


def _check_github_release(tag):
    """Check if a GitHub Release exists for the tag."""
    if not check_gh_installed():
        print("Error: gh CLI is not installed.", file=sys.stderr)
        sys.exit(1)
    if not check_gh_auth():
        print("Error: gh CLI is not authenticated. Run 'gh auth login'.", file=sys.stderr)
        sys.exit(1)

    try:
        run("gh", ["release", "view", tag])
        return ("PASS", f"{tag} exists")
    except subprocess.CalledProcessError:
        return ("WARN", f"{tag} not found on GitHub")


def _check_branch_sync():
    """Check if the local branch is in sync with origin."""
    branch = get_current_branch()
    try:
        output = run("git", ["rev-list", "--left-right", "--count",
                              f"origin/{branch}...HEAD"])
    except subprocess.CalledProcessError:
        return ("WARN", f"no remote tracking for {branch}")

    parts = output.split("\t")
    if len(parts) != 2:
        return ("WARN", f"unexpected rev-list output: {output}")

    behind, ahead = int(parts[0]), int(parts[1])
    if behind == 0 and ahead == 0:
        return ("PASS", f"up to date with origin/{branch}")
    if behind == 0 and ahead > 0:
        return ("WARN", f"{ahead} commit(s) ahead of origin/{branch}")
    if behind > 0 and ahead == 0:
        return ("FAIL", f"{behind} commit(s) behind origin/{branch}")
    return ("FAIL", f"{behind} behind, {ahead} ahead of origin/{branch}")


def _check_changelog(version):
    """Check if CHANGELOG.md has an entry for the version."""
    changelog_path = "CHANGELOG.md"
    if not os.path.exists(changelog_path):
        return ("WARN", "CHANGELOG.md not found")

    entry = extract_changelog_entry(changelog_path, version)
    if entry:
        return ("PASS", f"entry for {version}")
    return ("WARN", f"no entry for {version}")


def _apply_fixes(results, tag, version):
    """Apply safe auto-fixes for WARN/FAIL results."""
    fixed = 0

    # Fix stale lock
    status, _ = results["Lock file"]
    if status == "WARN":
        lock_path = os.path.join(".rlsbl", "lock")
        if os.path.exists(lock_path):
            os.unlink(lock_path)
            print("Fixed: removed stale lock file")
            fixed += 1

    # Fix missing remote tag (only if local tag exists)
    local_status, _ = results["Local tag"]
    remote_status, _ = results["Remote tag"]
    if remote_status == "WARN" and local_status == "PASS":
        try:
            run("git", ["push", "origin", tag])
            print(f"Fixed: pushed tag {tag} to origin")
            fixed += 1
        except subprocess.CalledProcessError as e:
            print(f"Could not push tag: {e}", file=sys.stderr)

    # Fix missing GitHub Release (only if remote tag exists after potential fix)
    gh_status, _ = results["GitHub Release"]
    if gh_status == "WARN":
        # Re-check remote tag status (may have been fixed above)
        remote_check = _check_remote_tag(tag)
        if remote_check[0] == "PASS":
            try:
                run("gh", ["release", "create", tag, "--title", tag,
                           "--notes", f"Release {version}"])
                print(f"Fixed: created GitHub Release {tag}")
                fixed += 1
            except subprocess.CalledProcessError as e:
                print(f"Could not create GitHub Release: {e}", file=sys.stderr)

    # Report guidance for unfixable issues
    version_status, _ = results["Version files"]
    if version_status == "FAIL":
        print("Manual fix needed: version mismatch -- update version files to agree")

    branch_status, _ = results["Branch sync"]
    if branch_status == "FAIL":
        print("Manual fix needed: run 'git pull' to sync with origin")

    changelog_status, _ = results["Changelog"]
    if changelog_status == "WARN" and version:
        print(f"Manual fix needed: add a '## {version}' entry to CHANGELOG.md")

    local_tag_status, _ = results["Local tag"]
    if local_tag_status == "WARN" and tag:
        print(f"Manual fix needed: create tag with 'git tag {tag}'")

    return fixed


def _check_workflows_synced(root, projects):
    """Check that each project has a synced CI workflow at the repo root."""
    missing = []
    for proj in projects:
        name = proj["name"]
        workflow = os.path.join(root, ".github", "workflows", f"{name}-ci.yml")
        if not os.path.isfile(workflow):
            missing.append(name)
    if missing:
        return ("WARN", f"missing workflows: {', '.join(missing)}")
    return ("PASS", f"all {len(projects)} project(s) have synced workflows")


def _check_router_exists(root):
    """Check that ci-router.yml exists at the repo root."""
    router = os.path.join(root, ".github", "workflows", "ci-router.yml")
    if os.path.isfile(router):
        return ("PASS", "ci-router.yml exists")
    return ("WARN", "ci-router.yml not found")


def _check_project_targets(projects):
    """Check that each project has at least one detectable target."""
    missing = []
    for proj in projects:
        targets = detect_targets(proj["path"])
        if not targets:
            missing.append(proj["name"])
    if missing:
        return ("WARN", f"no targets detected: {', '.join(missing)}")
    return ("PASS", f"all {len(projects)} project(s) have targets")


def run_cmd(registry, args, flags):
    """Run diagnostic checks on the release state."""
    target_names = detect_targets(".")
    if not target_names:
        print("Warning: no targets detected.", file=sys.stderr)
        version = None
        tag = None
    else:
        target = TARGETS[target_names[0]]
        try:
            version = target.read_version(".")
        except Exception:
            version = None
        if version:
            tag = target.tag_format(version)
        else:
            tag = None

    # Run checks
    results = {}
    results["Lock file"] = _check_stale_lock()
    results["Version files"] = _check_version_consistency()
    results["Package names"] = _check_name_consistency()
    results["License"] = _check_license_consistency()
    results["Description"] = _check_description_consistency()

    if tag:
        results["Local tag"] = _check_local_tag(tag)
        results["Remote tag"] = _check_remote_tag(tag)
        results["GitHub Release"] = _check_github_release(tag)
    else:
        results["Local tag"] = ("WARN", "no version detected")
        results["Remote tag"] = ("WARN", "no version detected")
        results["GitHub Release"] = ("WARN", "no version detected")

    results["Branch sync"] = _check_branch_sync()

    if version:
        results["Changelog"] = _check_changelog(version)
    else:
        results["Changelog"] = ("WARN", "no version detected")

    # Print aligned table
    label_width = max(len(label) for label in results)
    issues = 0
    for label, (status, message) in results.items():
        padded_label = f"{label}:".ljust(label_width + 1)
        print(f"{padded_label}  {status} -- {message}")
        if status in ("WARN", "FAIL"):
            issues += 1

    # Summary
    print()
    if issues == 0:
        print("All checks passed.")
    else:
        print(f"{issues} issue(s) found.")

    # Monorepo workspace checks
    try:
        from ..workspace import find_workspace_root, load_workspace

        ws_root = find_workspace_root(".")
        if ws_root:
            projects = load_workspace(ws_root)
            print()
            print("Monorepo:")
            mono_results = {}
            mono_results["CI router"] = _check_router_exists(ws_root)
            mono_results["Synced workflows"] = _check_workflows_synced(
                ws_root, projects
            )
            mono_results["Project targets"] = _check_project_targets(projects)

            mono_label_width = max(len(label) for label in mono_results)
            for label, (status, message) in mono_results.items():
                padded_label = f"{label}:".ljust(mono_label_width + 1)
                print(f"{padded_label}  {status} -- {message}")
                if status in ("WARN", "FAIL"):
                    issues += 1
    except Exception:
        pass  # not in a monorepo, skip

    # Auto-fix if requested
    if flags.get("fix") and issues > 0 and tag and version:
        print()
        _apply_fixes(results, tag, version)
