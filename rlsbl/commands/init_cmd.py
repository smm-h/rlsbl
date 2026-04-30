"""Init command: scaffold release infrastructure from templates."""

import hashlib
import json
import os
import re
import shutil
import stat
import sys

from ..registries import REGISTRIES

HASHES_FILE = os.path.join(".rlsbl", "hashes.json")

# Files where existing content is preserved and template sections are appended
APPENDABLE = {"CLAUDE.md"}
APPEND_MARKER = "rlsbl"

# Files where missing entries from the template are merged into the existing file
MERGEABLE = {".gitignore"}

# Files that are safe to overwrite during --update (managed files users typically don't customize)
UPDATABLE = {
    ".github/workflows/ci.yml",
    ".github/workflows/publish.yml",
    "scripts/check-prs.sh",
    "scripts/pre-push-hook.sh",
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
        "Run rlsbl npm release [patch|minor|major]",
    ],
    "pypi": [
        "Push to GitHub",
        "Configure Trusted Publishing on pypi.org",
        "Run rlsbl pypi release [patch|minor|major]",
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


def process_mappings(template_dir, mappings, vars_dict, force, update=False,
                     existing_hashes=None):
    """Process a list of template mappings: read each template, apply vars, write target files.

    Skips existing files unless force is True, with special handling:
    - APPENDABLE files: append template sections if the marker is not already present
    - MERGEABLE files: merge missing entries from the template into the existing file
    - UPDATABLE files (with --update): overwrite only if the file hasn't been customized
      (detected via SHA-256 hash comparison against stored hashes)

    Returns (created, skipped, warnings, new_hashes).
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

        # When file exists and force is not set, use context-aware handling
        if os.path.exists(target) and not force:
            basename = os.path.basename(target)

            # In --update mode, overwrite managed files only if not customized
            if update and target in UPDATABLE:
                current_hash = file_hash(target)
                stored_hash = existing_hashes.get(target)
                if stored_hash and current_hash == stored_hash:
                    # File matches stored hash -- not customized, safe to overwrite
                    with open(template_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    content, unreplaced = process_template(raw, vars_dict)
                    target_dir = os.path.dirname(target)
                    if target_dir and target_dir != ".":
                        os.makedirs(target_dir, exist_ok=True)
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(content)
                    new_hashes[target] = file_hash(target)
                    created.append(target + " (updated)")
                    if unreplaced:
                        warnings.append(f"{target}: unreplaced vars: {', '.join(unreplaced)}")
                else:
                    # File was customized or no stored hash -- skip conservatively
                    # Seed the hash so future --update can detect changes
                    new_hashes[target] = current_hash
                    skipped.append(f"{target} (customized, use --force to overwrite)")
                continue

            if basename in APPENDABLE:
                with open(target, "r", encoding="utf-8") as f:
                    existing = f.read()
                if APPEND_MARKER in existing:
                    skipped.append(target + " (already has rlsbl section)")
                    continue
                # Append only the ## sections, stripping the top-level # heading
                with open(template_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                content, _ = process_template(raw, vars_dict)
                lines = content.split("\n")
                first_section_idx = None
                for i, line in enumerate(lines):
                    if i > 0 and line.startswith("## "):
                        first_section_idx = i
                        break
                section = "\n".join(lines[first_section_idx:]) if first_section_idx is not None else content
                with open(target, "a", encoding="utf-8") as f:
                    f.write("\n\n" + section.strip() + "\n")
                created.append(target + " (appended)")
                continue

            if basename in MERGEABLE:
                with open(target, "r", encoding="utf-8") as f:
                    existing = f.read()
                with open(template_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                content, _ = process_template(raw, vars_dict)
                existing_lines = {
                    line.strip() for line in existing.split("\n") if line.strip()
                }
                new_lines = [
                    line.strip() for line in content.split("\n") if line.strip()
                ]
                # Only merge non-comment entries that are missing from the existing file
                missing = [
                    line for line in new_lines
                    if line not in existing_lines and not line.startswith("#")
                ]
                if missing:
                    with open(target, "a", encoding="utf-8") as f:
                        f.write("\n# Added by rlsbl\n" + "\n".join(missing) + "\n")
                    created.append(f"{target} (merged {len(missing)} entries)")
                else:
                    skipped.append(target + " (all entries present)")
                continue

            skipped.append(target)
            continue

        with open(template_path, "r", encoding="utf-8") as f:
            raw = f.read()
        content, unreplaced = process_template(raw, vars_dict)

        # Ensure parent directory exists
        target_dir = os.path.dirname(target)
        if target_dir and target_dir != ".":
            os.makedirs(target_dir, exist_ok=True)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        new_hashes[target] = file_hash(target)
        created.append(target)

        if unreplaced:
            warnings.append(f"{target}: unreplaced vars: {', '.join(unreplaced)}")

    return created, skipped, warnings, new_hashes


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

    # Make all shell scripts in scripts/ executable
    scripts_dir = os.path.join(".", "scripts")
    if os.path.isdir(scripts_dir):
        for entry in os.listdir(scripts_dir):
            if entry.endswith(".sh"):
                os.chmod(os.path.join(scripts_dir, entry), 0o755)

    # Auto-install pre-push hook if not already present
    hook_source = os.path.join("scripts", "pre-push-hook.sh")
    hook_target = os.path.join(".git", "hooks", "pre-push")
    if os.path.exists(hook_source) and os.path.isdir(".git"):
        if not os.path.exists(hook_target):
            os.makedirs(os.path.join(".git", "hooks"), exist_ok=True)
            shutil.copy2(hook_source, hook_target)
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
    all_new_hashes.update(reg_hashes)
    all_new_hashes.update(shared_hashes)
    existing_hashes.update(all_new_hashes)
    save_hashes(existing_hashes)

    # Merge results
    created = reg_created + shared_created
    skipped = reg_skipped + shared_skipped
    warnings = reg_warnings + shared_warnings

    # Print summary
    if created:
        print("Created:")
        for f in created:
            print(f"  {f}")

    if skipped:
        print("Skipped (already exist, use --update to refresh managed files or --force to overwrite all):")
        for f in skipped:
            print(f"  {f}")

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  {w}")

    # Helpful note when existing CI workflow is preserved
    ci_path = ".github/workflows/ci.yml"
    if any(s.startswith(ci_path) for s in skipped):
        print("\nNote: Existing CI workflow preserved. Review and merge manually if needed.")

    # Next steps
    steps = NEXT_STEPS.get(registry)
    if steps:
        print("\nNext steps:")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")
