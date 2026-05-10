"""Init command: scaffold release infrastructure from templates."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from ..config import should_tag, read_project_config, write_project_config
from ..lock import acquire_lock, release_lock
from ..targets import TARGETS
from ..tagging import ensure_tags
from ..utils import find_commit_tool, is_private_repo

HASHES_FILE = os.path.join(".rlsbl", "hashes.json")
BASES_DIR = os.path.join(".rlsbl", "bases")

_NPM_LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")


def _check_npm_lockfile_missing():
    """Check if any npm lockfile exists from cwd up to the git root.

    Returns True if no lockfile is found (i.e., lockfile is missing).
    Prints a warning to stderr when missing.
    """
    current = os.path.abspath(".")
    while True:
        for lockfile in _NPM_LOCKFILES:
            if os.path.exists(os.path.join(current, lockfile)):
                return False
        # Stop if we reached the git root
        if os.path.isdir(os.path.join(current, ".git")):
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    print(
        'Warning: no lockfile found. CI uses "npm ci" which requires package-lock.json.',
        file=sys.stderr,
    )
    return True

# Files owned by the user after initial scaffold -- never overwrite or merge
USER_OWNED = {
    "CHANGELOG.md",
    "LICENSE",
    ".rlsbl/hooks/pre-release.sh",
    ".rlsbl/hooks/post-release.sh",
}

def file_hash(path):
    """SHA-256 hash of a file's contents."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_hashes():
    """Load stored file hashes from .rlsbl/hashes.json."""
    if os.path.exists(HASHES_FILE):
        with open(HASHES_FILE) as f:
            return json.load(f)
    return {}


def save_hashes(hashes):
    """Write file hashes to .rlsbl/hashes.json."""
    os.makedirs(os.path.dirname(HASHES_FILE), exist_ok=True)
    with open(HASHES_FILE, "w") as f:
        json.dump(hashes, f, indent=2)
        f.write("\n")


def _ensure_target_in_config(registry_name):
    """Add registry_name to the targets array in .rlsbl/config.json if not already present."""
    config = read_project_config()
    targets = config.get("targets", [])
    if not isinstance(targets, list):
        targets = []
    if registry_name not in targets:
        targets.append(registry_name)
    write_project_config("targets", targets)


NEXT_STEPS = {
    "npm": [
        "Add an NPM_TOKEN secret to your GitHub repo (Settings > Secrets > Actions)",
        "Push to GitHub to activate the CI workflow",
        "Run rlsbl release [patch|minor|major]",
    ],
    "pypi": [
        "Push to GitHub",
        "Configure Trusted Publishing on pypi.org",
        "Run rlsbl release [patch|minor|major]",
    ],
    "go": [
        "GoReleaser runs in CI via GitHub Actions (no local install needed)",
        "Push to GitHub to activate the CI workflow",
        "Run rlsbl release [patch|minor|major]",
    ],
}


def process_template(template_content, vars_dict):
    """Process a template string by replacing {{varName}} placeholders with values.

    Returns (content, unreplaced) where unreplaced is a list of unmatched var names.
    """
    unreplaced = []

    def replacer(match):
        var_name = match.group(1)
        if var_name in vars_dict:
            return vars_dict[var_name]
        unreplaced.append(var_name)
        return match.group(0)

    content = re.sub(r"\{\{(\w+(?:\.\w+)*)\}\}", replacer, template_content)
    return content, unreplaced


def _save_base(target, content):
    """Save rendered template content as the merge base for future three-way merges."""
    base_path = os.path.join(BASES_DIR, target)
    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    with open(base_path, "w", encoding="utf-8") as f:
        f.write(content)


def _load_base(target):
    """Load the stored merge base for a target file. Returns None if not stored."""
    base_path = os.path.join(BASES_DIR, target)
    if not os.path.exists(base_path):
        return None
    with open(base_path, "r", encoding="utf-8") as f:
        return f.read()


def _three_way_merge(ours_text, base_text, theirs_text):
    """Three-way merge using git merge-file.

    Writes three temp files in the project dir (not /tmp), runs
    `git merge-file -p ours base theirs`, and returns (merged_text, has_conflicts).
    Exit code: 0 = clean merge, positive = number of conflicts, negative = error.
    """
    ours_tmp = theirs_tmp = base_tmp = None
    try:
        ours_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ours", dir=".", delete=False, encoding="utf-8",
        )
        ours_tmp.write(ours_text)
        ours_tmp.close()

        base_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".base", dir=".", delete=False, encoding="utf-8",
        )
        base_tmp.write(base_text)
        base_tmp.close()

        theirs_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".theirs", dir=".", delete=False, encoding="utf-8",
        )
        theirs_tmp.write(theirs_text)
        theirs_tmp.close()

        result = subprocess.run(
            ["git", "merge-file", "-p", ours_tmp.name, base_tmp.name, theirs_tmp.name],
            capture_output=True, text=True,
        )
        merged_text = result.stdout
        # Exit code 0 = clean, positive = number of conflicts, negative = error
        has_conflicts = result.returncode > 0
        if result.returncode < 0:
            # Treat errors as conflicts so the caller knows something went wrong
            has_conflicts = True
        return merged_text, has_conflicts
    finally:
        for tmp in (ours_tmp, base_tmp, theirs_tmp):
            if tmp is not None:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass


def process_mappings(template_dir, mappings, vars_dict, force, update=False,
                     existing_hashes=None):
    """Process a list of template mappings: read each template, apply vars, write target files.

    Uses a universal three-way merge (via git merge-file) for existing files:
    base (last scaffolded version) + ours (user's current file) + theirs (new template).
    USER_OWNED files are never overwritten or merged (except LICENSE year update).

    Returns (created, skipped, warnings, new_hashes).
    created/skipped are lists of (target, status) tuples for unified display.
    """
    if existing_hashes is None:
        existing_hashes = {}
    created = []
    skipped = []
    warnings = []
    new_hashes = {}

    for mapping in mappings:
        template = mapping["template"]
        target = mapping["target"]

        template_path = os.path.join(template_dir, template)
        if not os.path.exists(template_path):
            warnings.append(f"Template not found: {template_path}")
            continue

        with open(template_path, "r", encoding="utf-8") as f:
            raw = f.read()
        theirs, unreplaced = process_template(raw, vars_dict)

        # --- User-owned files: never overwrite (even with --force),
        # except LICENSE gets its copyright year updated on --update.
        if os.path.exists(target) and target in USER_OWNED:
            if update and target == "LICENSE":
                from datetime import datetime
                current_year = str(datetime.now().year)
                with open(target, "r", encoding="utf-8") as f:
                    content = f.read()
                # Match "Copyright (c) YYYY" or "Copyright (c) YYYY-YYYY"
                # Capture the original end-year to report the range in the status
                old_year = None
                def _capture_range(m):
                    nonlocal old_year
                    if m.group(2) == current_year:
                        return m.group(0)
                    old_year = f"{m.group(1).split()[-1]}-{m.group(2)}"
                    return f"{m.group(1)}-{current_year}"
                updated = re.sub(
                    r"(Copyright\s+\(c\)\s+\d{4})-(\d{4})",
                    _capture_range,
                    content,
                )
                if updated == content:
                    # No range found or range already current -- try single year
                    def _capture_single(m):
                        nonlocal old_year
                        if m.group(2) == current_year:
                            return m.group(0)
                        old_year = m.group(2)
                        return f"{m.group(1)}{m.group(2)}-{current_year}"
                    updated = re.sub(
                        r"(Copyright\s+\(c\)\s+)(\d{4})(?![-\d])",
                        _capture_single,
                        content,
                    )
                if updated != content:
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(updated)
                    year_detail = (
                        f"year updated ({old_year} -> {old_year.split('-')[0]}-{current_year})"
                        if old_year and "-" in old_year
                        else f"year updated ({old_year} -> {old_year}-{current_year})"
                    ) if old_year else "year updated"
                    created.append(("LICENSE", year_detail))
                else:
                    skipped.append((target, "user-owned"))
            else:
                skipped.append((target, "user-owned"))
            continue

        # --- New file or force overwrite (non-user-owned): write and save base ---
        if not os.path.exists(target) or force:
            is_overwrite = os.path.exists(target) and force
            target_dir = os.path.dirname(target)
            if target_dir and target_dir != ".":
                os.makedirs(target_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(theirs)
            _save_base(target, theirs)
            new_hashes[target] = file_hash(target)
            status = "overwritten" if is_overwrite else "created"
            created.append((target, status))
            if unreplaced:
                warnings.append(f"{target}: unreplaced vars: {', '.join(unreplaced)}")
            continue

        # --- Three-way merge for all other existing files ---
        with open(target, "r", encoding="utf-8") as f:
            ours = f.read()
        base = _load_base(target)

        if base is None:
            # No base stored (legacy project or first update after migration).
            # Cannot do a three-way merge. Seed the base for next time.
            _save_base(target, theirs)
            if ours == theirs:
                skipped.append((target, "unchanged, base seeded"))
            else:
                warnings.append(
                    f"{target}: no base stored, cannot merge; "
                    "run scaffold --force to reset"
                )
                skipped.append((target, "no base -- run scaffold --force to enable merging"))
            continue

        if ours == base:
            # User did not customize -- clean update: write theirs.
            target_dir = os.path.dirname(target)
            if target_dir and target_dir != ".":
                os.makedirs(target_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(theirs)
            _save_base(target, theirs)
            new_hashes[target] = file_hash(target)
            created.append((target, "updated"))
            if unreplaced:
                warnings.append(f"{target}: unreplaced vars: {', '.join(unreplaced)}")
        elif base == theirs:
            # Template did not change -- nothing to do.
            skipped.append((target, "unchanged"))
        elif ours == theirs:
            # User and template converged to same content -- nothing to do.
            skipped.append((target, "unchanged"))
        else:
            # Both user and template changed -- three-way merge.
            merged, has_conflicts = _three_way_merge(ours, base, theirs)
            target_dir = os.path.dirname(target)
            if target_dir and target_dir != ".":
                os.makedirs(target_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(merged)
            _save_base(target, theirs)
            new_hashes[target] = file_hash(target)
            if has_conflicts:
                created.append((target, "CONFLICTS -- resolve manually"))
                warnings.append(f"{target}: merge conflicts detected, resolve manually")
            else:
                created.append((target, "merged"))
            if unreplaced:
                warnings.append(f"{target}: unreplaced vars: {', '.join(unreplaced)}")

    return created, skipped, warnings, new_hashes


def _finalize_scaffold(existing_hashes, all_hash_dicts, created, skipped, warnings,
                       registry=None, flags=None, registries=None,
                       npm_lockfile_missing=False):
    """Shared post-processing for scaffold: chmod, hooks, version marker, hashes, tagging, summary.

    all_hash_dicts is a list of dicts to merge into existing_hashes.
    flags is the CLI flags dict (used for tagging check).
    registries is a list of registry names (used for tagging).
    npm_lockfile_missing: if True, prepend a lockfile step to npm next steps.
    """
    if flags is None:
        flags = {}
    if registries is None:
        registries = [registry] if registry else []
    # Make all shell scripts in .rlsbl/hooks/ executable
    hooks_dir = os.path.join(".", ".rlsbl", "hooks")
    if os.path.isdir(hooks_dir):
        for entry in os.listdir(hooks_dir):
            if entry.endswith(".sh"):
                os.chmod(os.path.join(hooks_dir, entry), 0o755)

    # Auto-install pre-push hook as a one-liner that delegates to the subcommand
    hook_target = os.path.join(".git", "hooks", "pre-push")
    if os.path.isdir(".git"):
        if not os.path.exists(hook_target):
            hook_content = "#!/usr/bin/env bash\nexec rlsbl pre-push-check \"$@\"\n"
            os.makedirs(os.path.join(".git", "hooks"), exist_ok=True)
            with open(hook_target, "w", encoding="utf-8") as f:
                f.write(hook_content)
            os.chmod(hook_target, 0o755)
            print("Installed pre-push hook (.git/hooks/pre-push)")

    # Write scaffolding version marker so the pre-push hook can detect drift
    from rlsbl import __version__
    marker_dir = os.path.join(".", ".rlsbl")
    os.makedirs(marker_dir, exist_ok=True)
    marker_path = os.path.join(marker_dir, "version")
    with open(marker_path, "w") as f:
        f.write(__version__ + "\n")
    print("Wrote scaffolding version marker (.rlsbl/version)")

    # Persist file hashes for future --update customization detection
    all_new_hashes = {}
    for h in all_hash_dicts:
        all_new_hashes.update(h)
    existing_hashes.update(all_new_hashes)
    save_hashes(existing_hashes)

    # Ecosystem tagging
    if should_tag(flags):
        ensure_tags(registries)

    # Print unified file list with dot-padded status column
    all_files = [(t, s) for t, s in created] + [(t, s) for t, s in skipped]
    if all_files:
        # Sort by target path for stable output
        all_files.sort(key=lambda item: item[0])
        # Compute padding width: longest target path + minimum 4 dots
        max_target_len = max(len(t) for t, _ in all_files)
        pad_width = max_target_len + 4
        print("Files:")
        for target, status in all_files:
            # Fill gap between target and status with dots
            dots = " " + "." * (pad_width - len(target)) + " "
            print(f"  {target}{dots}{status}")

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  {w}")

    # Helpful note when existing CI workflow is preserved
    ci_path = ".github/workflows/ci.yml"
    if any(t == ci_path for t, _ in skipped):
        print("\nNote: Existing CI workflow preserved. Review and merge manually if needed.")

    # Next steps
    if registry:
        steps = NEXT_STEPS.get(registry)
        if steps:
            steps = list(steps)
            if npm_lockfile_missing:
                steps.insert(0, 'Run "npm install" and commit package-lock.json before pushing')
            print("\nNext steps:")
            for i, step in enumerate(steps, 1):
                print(f"  {i}. {step}")

    # Auto-commit scaffold changes unless --no-commit is set
    if flags.get("no-commit"):
        print("Skipping commit (--no-commit).")
        return

    # Collect all files that were created/modified (not "unchanged" or "skipped")
    files_to_commit = [t for t, s in created
                       if s not in ("unchanged", "skipped", "user-owned")]
    # Include .rlsbl/ internal files written during scaffold
    config_file = os.path.join(".rlsbl", "config.json")
    for rlsbl_file in [HASHES_FILE, os.path.join(".rlsbl", "version"), config_file]:
        if os.path.exists(rlsbl_file) and rlsbl_file not in files_to_commit:
            files_to_commit.append(rlsbl_file)
    # Include any base files that were saved for the created targets
    if os.path.isdir(BASES_DIR):
        for target, _ in created:
            base_path = os.path.join(BASES_DIR, target)
            if os.path.exists(base_path) and base_path not in files_to_commit:
                files_to_commit.append(base_path)

    if not files_to_commit:
        return

    # Only attempt commit if we're in a git repo
    if not os.path.isdir(".git"):
        return

    tool = find_commit_tool()
    try:
        if tool == "safegit":
            subprocess.run(
                ["safegit", "commit", "-m", "rlsbl scaffold", "--"] + files_to_commit,
                check=True, capture_output=True, text=True,
            )
        else:
            subprocess.run(
                ["git", "add"] + files_to_commit,
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "rlsbl scaffold"],
                check=True, capture_output=True, text=True,
            )
        print("Committed scaffold changes.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: could not commit scaffold changes: {e}")


def _resolve_private(flags):
    """Determine if this is a private repository.

    Checks --private flag first, then saved config, then auto-detects via GitHub API.
    Returns True/False, or False if detection fails.
    """
    if flags.get("private"):
        return True

    # Check saved config
    config = read_project_config()
    if "private" in config:
        return bool(config["private"])

    # Auto-detect via GitHub API
    detected = is_private_repo()
    if detected is not None:
        return detected

    return False


def _filter_mappings_for_private(mappings):
    """Remove publish template mappings (private repos don't publish to registries)."""
    return [m for m in mappings if "publish" not in m["template"]]


def _replace_post_release_hook_for_private(mappings):
    """Replace the generic post-release hook mapping with the private-specific one."""
    result = []
    for m in mappings:
        if m["target"] == ".rlsbl/hooks/post-release.sh":
            result.append({
                "template": "hooks/post-release-private.sh.tpl",
                "target": ".rlsbl/hooks/post-release.sh",
            })
        else:
            result.append(m)
    return result


def _print_private_summary():
    """Print helpful output for private repository scaffold."""
    print("\nPrivate repository detected. Scaffold configured for private distribution.")
    print("- publish.yml skipped (no public registry)")
    print("- Post-release hook will build and upload artifacts to GitHub Releases")
    print("\nConsumers can install via:")
    print('  Python: uv pip install "pkg @ git+ssh://git@github.com/owner/repo@vX.Y.Z"')
    print("  npm:    npm install git+ssh://git@github.com/owner/repo#vX.Y.Z")
    print("  Go:     go get github.com/owner/repo@vX.Y.Z")


def _trigger_monorepo_sync():
    """If the current directory is inside a monorepo workspace, run sync.

    Uses a subprocess so that sys.exit() calls inside sync don't kill scaffold.
    Failures are silently ignored -- sync is best-effort after scaffold.
    """
    from ..workspace import find_workspace_root

    ws_root = find_workspace_root(".")
    if ws_root:
        try:
            subprocess.run(
                [sys.executable, "-m", "rlsbl", "monorepo", "sync"],
                cwd=ws_root,
                check=False,
            )
        except Exception:
            pass


def run_cmd(registry, args, flags):
    """Init command handler.

    Scaffolds release infrastructure (CI, publish workflows, changelog, etc.)
    from templates.
    """
    reg = TARGETS[registry]

    # Check that a project file exists
    if not reg.check_project_exists("."):
        print(f"Error: no {registry} project found in current directory.", file=sys.stderr)
        print(reg.get_project_init_hint(), file=sys.stderr)
        sys.exit(1)

    # Check for npm lockfile
    npm_lockfile_missing = False
    if registry == "npm":
        npm_lockfile_missing = _check_npm_lockfile_missing()

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        # Register this target in .rlsbl/config.json targets array
        _ensure_target_in_config(registry)

        # Determine if this is a private repository
        private = _resolve_private(flags)
        if private:
            write_project_config("private", True)

        # Gather template variables
        vars_dict = reg.get_template_vars(".")
        from datetime import datetime
        vars_dict["year"] = str(datetime.now().year)

        force = flags.get("force", False)
        update = flags.get("update", False)

        existing_hashes = load_hashes()

        # Process registry-specific templates
        reg_mappings = reg.get_template_mappings()
        if private:
            reg_mappings = _filter_mappings_for_private(reg_mappings)
        reg_created, reg_skipped, reg_warnings, reg_hashes = process_mappings(
            reg.get_template_dir(),
            reg_mappings,
            vars_dict,
            force,
            update,
            existing_hashes,
        )

        # Process shared templates (skip if another registry already handled them)
        shared_created, shared_skipped, shared_warnings, shared_hashes = [], [], [], {}
        if not flags.get("skip-shared"):
            shared_mappings = reg.get_shared_template_mappings()
            if private:
                shared_mappings = _replace_post_release_hook_for_private(shared_mappings)
            shared_created, shared_skipped, shared_warnings, shared_hashes = process_mappings(
                reg.get_shared_template_dir(),
                shared_mappings,
                vars_dict,
                force,
                update,
                existing_hashes,
            )

        created = reg_created + shared_created
        skipped = reg_skipped + shared_skipped
        warnings = reg_warnings + shared_warnings

        # Warn if Go project has main in cmd/ but not at root
        if registry == "go":
            if reg._has_cmd_main(".") and not reg._has_root_main("."):
                print(
                    "Warning: Go project has main package in cmd/ but not at root.\n"
                    "'go install module@latest' won't work. Consider moving main.go "
                    "to the project root.",
                    file=sys.stderr,
                )

        _finalize_scaffold(
            existing_hashes, [reg_hashes, shared_hashes],
            created, skipped, warnings, registry=registry,
            flags=flags, registries=[registry],
            npm_lockfile_missing=npm_lockfile_missing,
        )

        if private:
            _print_private_summary()

        # If inside a monorepo, sync root CI workflows
        _trigger_monorepo_sync()
    finally:
        release_lock()


def _extract_top_level_block(lines, key):
    """Extract a top-level YAML block (e.g., 'permissions:', 'env:') from template lines.

    Returns (block_lines, remaining_lines) where block_lines are the key + its
    indented children, and remaining_lines are everything else.
    """
    block = []
    remaining = []
    in_block = False
    for line in lines:
        if not in_block:
            stripped = line.rstrip()
            if stripped == f"{key}:" or stripped.startswith(f"{key}: "):
                in_block = True
                block.append(line)
                continue
            remaining.append(line)
        else:
            # Still in block if line is blank or starts with whitespace
            stripped = line.rstrip()
            if stripped == "" or line[0] in (" ", "\t"):
                block.append(line)
            else:
                in_block = False
                remaining.append(line)
    return block, remaining


def _parse_permissions(block_lines):
    """Parse permission key-value pairs from a permissions block.

    Returns a dict like {"contents": "write", "id-token": "write"}.
    """
    perms = {}
    for line in block_lines:
        stripped = line.strip()
        if stripped.startswith("permissions") or not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            perms[k.strip()] = v.strip()
    return perms


def _parse_env(block_lines):
    """Parse env key-value pairs from an env block.

    Returns a list of (key, full_line) tuples to preserve formatting.
    Keys are used for deduplication; full lines are used for output.
    """
    entries = []
    for line in block_lines:
        stripped = line.strip()
        if stripped.startswith("env") or not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            k = stripped.split(":", 1)[0].strip()
            entries.append((k, line))
    return entries


def _merge_permissions(perm_dicts):
    """Merge multiple permission dicts, choosing the most permissive value for each key.

    Permission escalation order: read < write.
    """
    merged = {}
    order = {"read": 0, "write": 1}
    for d in perm_dicts:
        for k, v in d.items():
            if k not in merged:
                merged[k] = v
            else:
                # Pick the more permissive value
                if order.get(v, 0) > order.get(merged[k], 0):
                    merged[k] = v
    return merged


def _extract_jobs_section(lines):
    """Extract the content under the 'jobs:' key from template lines.

    Returns lines starting from the first job definition (the indented content
    after 'jobs:'), not including the 'jobs:' line itself.
    """
    in_jobs = False
    job_lines = []
    for line in lines:
        stripped = line.rstrip()
        if not in_jobs:
            if stripped == "jobs:":
                in_jobs = True
                continue
        else:
            job_lines.append(line)
    return job_lines


def _generate_merged_publish(targets, template_vars):
    """Generate a merged publish.yml from individual target publish templates.

    Reads each target's publish.yml.tpl, extracts jobs/permissions/env,
    and composes a single workflow with all jobs merged.
    """
    templates_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

    all_permissions = []
    all_env_entries = []
    all_jobs = []
    seen_env_keys = set()

    for target_name in targets:
        tpl_path = os.path.join(templates_root, target_name, "publish.yml.tpl")
        if not os.path.exists(tpl_path):
            continue

        with open(tpl_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Process template variables
        content, _ = process_template(raw, template_vars)
        lines = content.splitlines(keepends=True)

        # Extract top-level permissions block
        perm_block, lines = _extract_top_level_block(lines, "permissions")
        if perm_block:
            all_permissions.append(_parse_permissions(perm_block))

        # Extract top-level env block
        env_block, lines = _extract_top_level_block(lines, "env")
        if env_block:
            for k, full_line in _parse_env(env_block):
                if k not in seen_env_keys:
                    seen_env_keys.add(k)
                    all_env_entries.append(full_line)

        # Extract jobs section
        job_lines = _extract_jobs_section(lines)
        if not job_lines:
            continue

        # Find the job key name (first non-blank, non-comment line at 2-space indent)
        original_job_key = None
        for jl in job_lines:
            stripped = jl.rstrip()
            if stripped and not stripped.startswith("#"):
                # Should be like "  jobname:" at 2-space indent
                match = re.match(r"^  (\S+):\s*$", stripped)
                if match:
                    original_job_key = match.group(1)
                break

        if original_job_key is None:
            continue

        # Rename the job key to the target name for uniqueness
        renamed_lines = []
        key_replaced = False
        for jl in job_lines:
            if not key_replaced:
                stripped = jl.rstrip()
                if stripped and not stripped.startswith("#"):
                    # Replace original job key with target name
                    jl = jl.replace(f"  {original_job_key}:", f"  {target_name}:", 1)
                    key_replaced = True
            renamed_lines.append(jl)

        all_jobs.append(renamed_lines)

    # Compose the merged workflow
    output_lines = []
    output_lines.append("name: Publish\n")
    output_lines.append("\n")
    output_lines.append("on:\n")
    output_lines.append("  release:\n")
    output_lines.append("    types: [published]\n")

    # Merged permissions
    merged_perms = _merge_permissions(all_permissions)
    if merged_perms:
        output_lines.append("\n")
        output_lines.append("permissions:\n")
        for k in sorted(merged_perms):
            output_lines.append(f"  {k}: {merged_perms[k]}\n")

    # Merged env
    if all_env_entries:
        output_lines.append("\n")
        output_lines.append("env:\n")
        for entry in all_env_entries:
            # Ensure the line is properly indented (should already be 2-space)
            line = entry if entry.endswith("\n") else entry + "\n"
            output_lines.append(line)

    # Jobs
    output_lines.append("\n")
    output_lines.append("jobs:\n")
    for i, job_lines in enumerate(all_jobs):
        # Strip trailing blank lines from previous job
        if i > 0:
            # Add a blank line between jobs
            output_lines.append("\n")
        for jl in job_lines:
            line = jl if jl.endswith("\n") else jl + "\n"
            output_lines.append(line)

    # Remove trailing blank lines
    result = "".join(output_lines)
    result = result.rstrip("\n") + "\n"
    return result


def _merge_template_vars(registries_list, primary, dir_path):
    """Build a merged template vars dict with namespaced keys from all targets.

    The primary target's vars are included un-namespaced (as the base).
    Every target's vars are also included with a namespace prefix:
    ``{target_name}.{key}`` so templates can reference target-specific values
    like ``{{pypi.minRequiredPython}}``.
    """
    merged = {}
    # Primary target's vars as base (un-namespaced)
    primary_target = TARGETS[primary]
    primary_vars = primary_target.get_template_vars(dir_path)
    merged.update(primary_vars)
    # All targets' vars namespaced
    for target_name in registries_list:
        target = TARGETS[target_name]
        target_vars = target.get_template_vars(dir_path)
        for key, value in target_vars.items():
            merged[f"{target_name}.{key}"] = value
    return merged


def run_cmd_multi(registries_list, args, flags):
    """Scaffold for multiple registries with a merged publish workflow.

    Uses the primary registry for template vars and CI, then writes a merged
    publish.yml that contains jobs for all detected registries.
    """
    primary = registries_list[0]
    reg = TARGETS[primary]

    if not reg.check_project_exists("."):
        print(f"Error: no {primary} project found in current directory.", file=sys.stderr)
        sys.exit(1)

    # Check for npm lockfile
    npm_lockfile_missing = False
    if "npm" in registries_list:
        npm_lockfile_missing = _check_npm_lockfile_missing()

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        # Register all targets in .rlsbl/config.json targets array
        for r in registries_list:
            _ensure_target_in_config(r)

        # Determine if this is a private repository
        private = _resolve_private(flags)
        if private:
            write_project_config("private", True)

        print(f"Multiple registries detected: {', '.join(registries_list)}")
        if private:
            print("Scaffolding for private repository (no publish workflow).")
        else:
            print("Scaffolding with merged publish workflow.")

        vars_dict = _merge_template_vars(registries_list, primary, ".")
        from datetime import datetime
        vars_dict["year"] = str(datetime.now().year)

        force = flags.get("force", False)
        update = flags.get("update", False)
        existing_hashes = load_hashes()

        # Process primary registry CI template only (publish will come from merged)
        ci_mappings = [m for m in reg.get_template_mappings() if "publish" not in m["template"]]
        ci_created, ci_skipped, ci_warnings, ci_hashes = process_mappings(
            reg.get_template_dir(),
            ci_mappings,
            vars_dict,
            force,
            update,
            existing_hashes,
        )

        # Generate and write merged publish workflow (skip for private repos)
        merged_created, merged_skipped, merged_warnings, merged_hashes = [], [], [], {}
        if not private:
            publish_target = os.path.join(".github", "workflows", "publish.yml")
            merged_content = _generate_merged_publish(registries_list, vars_dict)

            target_dir = os.path.dirname(publish_target)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

            is_overwrite = os.path.exists(publish_target)
            if not is_overwrite or force:
                with open(publish_target, "w", encoding="utf-8") as f:
                    f.write(merged_content)
                _save_base(publish_target, merged_content)
                merged_hashes[publish_target] = file_hash(publish_target)
                status = "overwritten" if is_overwrite else "created"
                merged_created.append((publish_target, status))
            elif update:
                # Three-way merge for updates
                with open(publish_target, "r", encoding="utf-8") as f:
                    ours = f.read()
                base = _load_base(publish_target)
                if base is None:
                    _save_base(publish_target, merged_content)
                    if ours == merged_content:
                        merged_skipped.append((publish_target, "unchanged, base seeded"))
                    else:
                        merged_warnings.append(
                            f"{publish_target}: no base stored, cannot merge; "
                            "run scaffold --force to reset"
                        )
                        merged_skipped.append((publish_target,
                                               "no base -- run scaffold --force to enable merging"))
                elif ours == base:
                    with open(publish_target, "w", encoding="utf-8") as f:
                        f.write(merged_content)
                    _save_base(publish_target, merged_content)
                    merged_hashes[publish_target] = file_hash(publish_target)
                    merged_created.append((publish_target, "updated"))
                elif base == merged_content or ours == merged_content:
                    merged_skipped.append((publish_target, "unchanged"))
                else:
                    merged_text, has_conflicts = _three_way_merge(ours, base, merged_content)
                    with open(publish_target, "w", encoding="utf-8") as f:
                        f.write(merged_text)
                    _save_base(publish_target, merged_content)
                    merged_hashes[publish_target] = file_hash(publish_target)
                    if has_conflicts:
                        merged_created.append((publish_target,
                                               "CONFLICTS -- resolve manually"))
                        merged_warnings.append(
                            f"{publish_target}: merge conflicts detected, resolve manually")
                    else:
                        merged_created.append((publish_target, "merged"))
            else:
                merged_skipped.append((publish_target, "exists"))

        # Process shared templates (once)
        shared_mappings = reg.get_shared_template_mappings()
        if private:
            shared_mappings = _replace_post_release_hook_for_private(shared_mappings)
        shared_created, shared_skipped, shared_warnings, shared_hashes = process_mappings(
            reg.get_shared_template_dir(),
            shared_mappings,
            vars_dict,
            force,
            update,
            existing_hashes,
        )

        created = ci_created + merged_created + shared_created
        skipped = ci_skipped + merged_skipped + shared_skipped
        warnings = ci_warnings + merged_warnings + shared_warnings

        _finalize_scaffold(
            existing_hashes, [ci_hashes, merged_hashes, shared_hashes],
            created, skipped, warnings,
            flags=flags, registries=registries_list,
        )

        if private:
            _print_private_summary()
        else:
            # Show combined next steps for dual-registry
            steps = [
                "Add an NPM_TOKEN secret to your GitHub repo (Settings > Secrets > Actions)",
                "Configure Trusted Publishing on pypi.org",
                "Push to GitHub to activate the CI workflow",
                "Run rlsbl release [patch|minor|major]",
            ]
            if npm_lockfile_missing:
                steps.insert(0, 'Run "npm install" and commit package-lock.json before pushing')
            print("\nNext steps:")
            for i, step in enumerate(steps, 1):
                print(f"  {i}. {step}")

        # If inside a monorepo, sync root CI workflows
        _trigger_monorepo_sync()
    finally:
        release_lock()
