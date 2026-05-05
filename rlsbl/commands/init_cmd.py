"""Init command: scaffold release infrastructure from templates."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from ..config import should_tag
from ..lock import acquire_lock, release_lock
from ..registries import REGISTRIES
from ..tagging import ensure_tags
from ..utils import find_commit_tool

HASHES_FILE = os.path.join(".rlsbl", "hashes.json")
BASES_DIR = os.path.join(".rlsbl", "bases")

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

    content = re.sub(r"\{\{(\w+)\}\}", replacer, template_content)
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
                       registry=None, flags=None, registries=None):
    """Shared post-processing for scaffold: chmod, hooks, version marker, hashes, tagging, summary.

    all_hash_dicts is a list of dicts to merge into existing_hashes.
    flags is the CLI flags dict (used for tagging check).
    registries is a list of registry names (used for tagging).
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
    for rlsbl_file in [HASHES_FILE, os.path.join(".rlsbl", "version")]:
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


def run_cmd(registry, args, flags):
    """Init command handler.

    Scaffolds release infrastructure (CI, publish workflows, changelog, etc.)
    from templates.
    """
    reg = REGISTRIES[registry]

    # Check that a project file exists
    if not reg.check_project_exists("."):
        print(f"Error: no {registry} project found in current directory.", file=sys.stderr)
        print(reg.get_project_init_hint(), file=sys.stderr)
        sys.exit(1)

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        # Gather template variables
        vars_dict = reg.get_template_vars(".")
        from datetime import datetime
        vars_dict["year"] = str(datetime.now().year)

        force = flags.get("force", False)
        update = flags.get("update", False)

        existing_hashes = load_hashes()

        # Process registry-specific templates
        reg_created, reg_skipped, reg_warnings, reg_hashes = process_mappings(
            reg.get_template_dir(),
            reg.get_template_mappings(),
            vars_dict,
            force,
            update,
            existing_hashes,
        )

        # Process shared templates (skip if another registry already handled them)
        shared_created, shared_skipped, shared_warnings, shared_hashes = [], [], [], {}
        if not flags.get("skip-shared"):
            shared_created, shared_skipped, shared_warnings, shared_hashes = process_mappings(
                reg.get_shared_template_dir(),
                reg.get_shared_template_mappings(),
                vars_dict,
                force,
                update,
                existing_hashes,
            )

        created = reg_created + shared_created
        skipped = reg_skipped + shared_skipped
        warnings = reg_warnings + shared_warnings

        _finalize_scaffold(
            existing_hashes, [reg_hashes, shared_hashes],
            created, skipped, warnings, registry=registry,
            flags=flags, registries=[registry],
        )
    finally:
        release_lock()


def run_cmd_multi(registries_list, args, flags):
    """Scaffold for multiple registries with a merged publish workflow.

    Uses the primary registry for template vars and CI, then writes a merged
    publish.yml that contains jobs for all detected registries.
    """
    primary = registries_list[0]
    reg = REGISTRIES[primary]

    if not reg.check_project_exists("."):
        print(f"Error: no {primary} project found in current directory.", file=sys.stderr)
        sys.exit(1)

    # Acquire advisory lock to prevent concurrent rlsbl operations
    acquire_lock()

    try:
        print(f"Multiple registries detected: {', '.join(registries_list)}")
        print("Scaffolding with merged publish workflow.")

        vars_dict = reg.get_template_vars(".")
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

        # Process merged publish workflow template
        merged_tpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      "templates", "merged")
        merged_created, merged_skipped, merged_warnings, merged_hashes = process_mappings(
            merged_tpl_dir,
            [{"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"}],
            vars_dict,
            force,
            update,
            existing_hashes,
        )

        # Process shared templates (once)
        shared_created, shared_skipped, shared_warnings, shared_hashes = process_mappings(
            reg.get_shared_template_dir(),
            reg.get_shared_template_mappings(),
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

        # Show combined next steps for dual-registry
        print("\nNext steps:")
        print("  1. Add an NPM_TOKEN secret to your GitHub repo (Settings > Secrets > Actions)")
        print("  2. Configure Trusted Publishing on pypi.org")
        print("  3. Push to GitHub to activate the CI workflow")
        print("  4. Run rlsbl release [patch|minor|major]")
    finally:
        release_lock()
