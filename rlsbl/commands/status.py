"""Status command: show project status summary."""

import os
import sys

from ..registries import REGISTRIES
from ..utils import (
    extract_changelog_entry,
    get_current_branch,
    is_clean_tree,
    run,
)


def run_cmd(registry, args, flags):
    """Status command handler.

    Shows a quick 'where am I' summary: package info, git state, changelog, CI.
    """
    reg = REGISTRIES[registry]

    if not reg.check_project_exists("."):
        print(f"No {registry} project found in current directory.", file=sys.stderr)
        sys.exit(1)

    version = reg.read_version(".")
    vars_dict = reg.get_template_vars(".")
    name = vars_dict.get("name") or "(unknown)"

    print(f"Package:   {name}")

    # Show version info for all detected registries
    for r_name, r_mod in REGISTRIES.items():
        if r_mod.check_project_exists("."):
            ver = r_mod.read_version(".")
            file = r_mod.get_version_file()
            print(f"Version:   {ver} ({r_name}, {file})")

    # Git info
    try:
        branch = get_current_branch()
        print(f"Branch:    {branch}")
    except Exception:
        print("Branch:    (not a git repo)")

    # Last tag
    try:
        last_tag = run("git", ["describe", "--tags", "--abbrev=0"])
        print(f"Last tag:  {last_tag}")
    except Exception:
        print("Last tag:  (none)")

    # Clean tree
    try:
        print(f"Clean:     {'yes' if is_clean_tree() else 'no'}")
    except Exception:
        print("Clean:     (unknown)")

    # Changelog
    changelog_path = "CHANGELOG.md"
    if os.path.exists(changelog_path):
        entry = extract_changelog_entry(changelog_path, version)
        if entry:
            print(f"Changelog: has entry for {version}")
        else:
            print(f"Changelog: no entry for {version}")
    else:
        print("Changelog: (not found)")

    # CI workflows
    ci_exists = os.path.exists(".github/workflows/ci.yml")
    publish_exists = os.path.exists(".github/workflows/publish.yml") or os.path.exists(
        ".github/workflows/workflow.yml"
    )
    print(f"CI:        {'yes' if ci_exists else 'missing'}")
    print(f"Publish:   {'yes' if publish_exists else 'missing'}")
