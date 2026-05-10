"""Monorepo workspace management commands."""

import os
import re
import subprocess
import sys

from ..workspace import find_workspace_root, load_workspace, save_workspace, WORKSPACE_DIR, WORKSPACE_FILE
from ..targets import detect_targets, TARGETS

def _auto_commit(message, files):
    """Best-effort commit of specific files. Failures are silently ignored."""
    try:
        subprocess.run(
            ["safegit", "commit", "-m", message, "--"] + files,
            check=True, capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("Error: safegit not found. Install it or check your PATH.", file=sys.stderr)
    except subprocess.CalledProcessError:
        pass


MONOREPO_HELP = """\
Usage: rlsbl monorepo <subcommand>

Subcommands:
  init                      Initialize a monorepo workspace
  add <path> [--name <n>]   Add a project to the workspace
  remove <path>             Remove a project from the workspace
  list                      List all projects in the workspace
  sync                      Sync CI workflows to repo root
  status                    Show status of all projects"""


def run_cmd(registry, args, flags):
    """Dispatch to monorepo subcommand."""
    if not args:
        print(MONOREPO_HELP)
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "init":
        _cmd_init(flags)
    elif subcommand == "add":
        _cmd_add(sub_args, flags)
    elif subcommand == "remove":
        _cmd_remove(sub_args, flags)
    elif subcommand == "list":
        _cmd_list(flags)
    elif subcommand == "sync":
        _cmd_sync(flags)
    elif subcommand == "status":
        _cmd_status(flags)
    else:
        print(f"Error: unknown monorepo subcommand '{subcommand}'.", file=sys.stderr)
        sys.exit(1)


def _cmd_init(flags):
    ws_file = os.path.join(".", WORKSPACE_DIR, WORKSPACE_FILE)
    if os.path.isfile(ws_file):
        print("Error: Workspace already initialized.", file=sys.stderr)
        sys.exit(1)
    save_workspace(".", [])
    print("Initialized monorepo workspace in .rlsbl-monorepo/")

    # Auto-commit workspace.toml
    _auto_commit("monorepo: init workspace", [os.path.join(WORKSPACE_DIR, WORKSPACE_FILE)])


def _cmd_add(args, flags):
    if not args:
        print("Error: Usage: rlsbl monorepo add <path> [--name <name>]", file=sys.stderr)
        sys.exit(1)

    path = args[0]
    if not os.path.isdir(path):
        print(f"Error: '{path}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    targets = detect_targets(path)
    if not targets:
        print(f"Error: No release target detected in '{path}'. Initialize a project first.", file=sys.stderr)
        sys.exit(1)

    name = flags.get("name") or os.path.basename(path.rstrip("/"))

    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)

    norm_path = path.rstrip("/")
    for proj in projects:
        if proj["path"].rstrip("/") == norm_path:
            print(f"Error: Project at '{path}' already exists in workspace.", file=sys.stderr)
            sys.exit(1)
        if proj["name"] == name:
            print(f"Error: Project named '{name}' already exists in workspace.", file=sys.stderr)
            sys.exit(1)

    projects.append({"path": path, "name": name})
    save_workspace(root, projects)
    print(f"Added project '{name}' at {path}")

    # Commit workspace.toml
    ws_file = os.path.join(WORKSPACE_DIR, WORKSPACE_FILE)
    _auto_commit(f"monorepo: add {name}", [ws_file])

    # Auto-scaffold if not already scaffolded
    project_rlsbl = os.path.join(path, ".rlsbl", "config.json")
    if not os.path.exists(project_rlsbl):
        print(f"Scaffolding {name}...")
        try:
            subprocess.run(
                [sys.executable, "-m", "rlsbl", "scaffold"],
                cwd=path,
                check=False,
            )
        except Exception as e:
            print(f"Warning: scaffold failed: {e}", file=sys.stderr)

    # Sync CI workflows
    try:
        subprocess.run(
            [sys.executable, "-m", "rlsbl", "monorepo", "sync"],
            cwd=root,
            check=False,
        )
    except Exception:
        pass


def _cmd_remove(args, flags):
    if not args:
        print("Error: Usage: rlsbl monorepo remove <path>", file=sys.stderr)
        sys.exit(1)

    path = args[0]

    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)

    norm_path = path.rstrip("/")
    new_projects = [p for p in projects if p["path"].rstrip("/") != norm_path]

    if len(new_projects) == len(projects):
        print(f"Warning: Project at '{path}' not found in workspace.", file=sys.stderr)
        return

    save_workspace(root, new_projects)
    print(f"Removed project at {path}")


def _cmd_list(flags):
    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)

    if not projects:
        print("No projects in workspace.")
        return

    name_width = max(len("Name"), max(len(p["name"]) for p in projects))
    header_name = "Name".ljust(name_width)
    print(f"{header_name}  Path")
    for proj in projects:
        name_col = proj["name"].ljust(name_width)
        print(f"{name_col}  {proj['path']}")

def _rewrite_trigger(content):
    """Replace the on: trigger block with workflow_call.

    Handles both multi-line triggers (on: alone on a line, with indented
    sub-keys up to jobs:) and single-line triggers (on: push, on: [push, ...]).
    """
    lines = content.splitlines()
    on_idx = None
    single_line = False
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if on_idx is None and (stripped == "on:" or stripped.startswith("on: ")):
            on_idx = i
            single_line = stripped.startswith("on: ")
            break

    if on_idx is None:
        print("Warning: no 'on:' trigger found in workflow, skipping rewrite", file=sys.stderr)
        return content

    if single_line:
        new_lines = lines[:on_idx] + ["on:", "  workflow_call:", ""] + lines[on_idx + 1:]
        return "\n".join(new_lines) + "\n"

    # Multi-line: find the next top-level key after on: (unindented, non-empty, non-comment)
    next_key_idx = None
    for i in range(on_idx + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace() and not line.startswith("#"):
            next_key_idx = i
            break

    if next_key_idx is None:
        print("Warning: no top-level key found after 'on:' in workflow, skipping rewrite", file=sys.stderr)
        return content

    new_lines = lines[:on_idx] + ["on:", "  workflow_call:", ""] + lines[next_key_idx:]
    return "\n".join(new_lines) + "\n"


def _generate_router(projects):
    """Generate ci-router.yml content from project list."""
    lines = []
    lines.append("# DO NOT EDIT -- generated by rlsbl monorepo sync")
    lines.append("name: CI Router")
    lines.append("")
    lines.append("on:")
    lines.append("  push:")
    lines.append("    branches: [main]")
    lines.append("  pull_request:")
    lines.append("")
    lines.append("jobs:")

    # detect job
    lines.append("  detect:")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    outputs:")
    for p in projects:
        lines.append(f"      {p['name']}: ${{{{ steps.changes.outputs.{p['name']} }}}}")
    lines.append("    steps:")
    lines.append("      - uses: actions/checkout@v4")
    lines.append("      - uses: dorny/paths-filter@v3")
    lines.append("        id: changes")
    lines.append("        with:")
    lines.append("          filters: |")
    for p in projects:
        lines.append(f"            {p['name']}: '{p['path']}/**'")

    # per-project jobs
    for p in projects:
        lines.append("")
        lines.append(f"  {p['name']}:")
        lines.append("    needs: detect")
        lines.append(f"    if: needs.detect.outputs.{p['name']} == 'true'")
        lines.append(f"    uses: ./.github/workflows/{p['name']}-ci.yml")

    return "\n".join(lines) + "\n"


def _generate_publish_router(projects):
    """Generate publish-router.yml content for projects with publish workflows."""
    lines = []
    lines.append("# DO NOT EDIT -- generated by rlsbl monorepo sync")
    lines.append("name: Publish Router")
    lines.append("")
    lines.append("on:")
    lines.append("  release:")
    lines.append("    types: [published]")
    lines.append("")
    lines.append("jobs:")

    for p in projects:
        lines.append(f"  {p['name']}:")
        lines.append(f"    if: startsWith(github.event.release.tag_name, '{p['name']}@v')")
        lines.append(f"    uses: ./.github/workflows/{p['name']}-publish.yml")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _cmd_sync(flags):
    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)
    if not projects:
        print("No projects in workspace. Nothing to sync.")
        return

    workflows_dir = os.path.join(root, ".github", "workflows")
    os.makedirs(workflows_dir, exist_ok=True)

    written_files = []
    current_project_names = set()

    # Track which projects have publish workflows
    projects_with_publish = []

    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        current_project_names.add(name)

        for wf_type in ("ci", "publish"):
            src = os.path.join(root, path, ".github", "workflows", f"{wf_type}.yml")
            dest = os.path.join(workflows_dir, f"{name}-{wf_type}.yml")

            if not os.path.isfile(src):
                if wf_type == "ci":
                    print(f"Warning: {path} has no CI workflow ({src})", file=sys.stderr)
                continue

            with open(src, "r", encoding="utf-8") as f:
                content = f.read()

            # Rewrite trigger
            rewritten = _rewrite_trigger(content)

            # Prepend header
            header = (
                f"# DO NOT EDIT -- generated by rlsbl monorepo sync\n"
                f"# Source: {path}/.github/workflows/{wf_type}.yml\n"
            )
            final = header + rewritten

            # Write destination
            if os.path.isfile(dest):
                os.chmod(dest, 0o644)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(final)
            os.chmod(dest, 0o444)
            written_files.append(dest)

            if wf_type == "publish":
                projects_with_publish.append(proj)

    # Generate CI router
    router_path = os.path.join(workflows_dir, "ci-router.yml")
    if os.path.isfile(router_path):
        os.chmod(router_path, 0o644)
    with open(router_path, "w", encoding="utf-8") as f:
        f.write(_generate_router(projects))
    os.chmod(router_path, 0o444)
    written_files.append(router_path)

    # Generate publish router (only if any project has publish.yml)
    publish_router_path = os.path.join(workflows_dir, "publish-router.yml")
    if projects_with_publish:
        if os.path.isfile(publish_router_path):
            os.chmod(publish_router_path, 0o644)
        with open(publish_router_path, "w", encoding="utf-8") as f:
            f.write(_generate_publish_router(projects_with_publish))
        os.chmod(publish_router_path, 0o444)
        written_files.append(publish_router_path)

    # Remove stale workflows
    stale_removed = 0
    deleted_files = []
    for filename in os.listdir(workflows_dir):
        filepath = os.path.join(workflows_dir, filename)
        if filepath in written_files:
            continue
        # Check if this is a generated per-project workflow
        for suffix in ("-ci.yml", "-publish.yml"):
            if filename.endswith(suffix):
                proj_name = filename[: -len(suffix)]
                if proj_name not in current_project_names:
                    os.chmod(filepath, 0o644)
                    os.remove(filepath)
                    deleted_files.append(filepath)
                    stale_removed += 1

    # Auto-commit
    all_files = written_files + deleted_files
    if all_files:
        _auto_commit("monorepo: sync CI workflows", all_files)

    wf_count = len(written_files) - 1  # subtract router(s)
    if projects_with_publish:
        wf_count -= 1
    router_count = 1 + (1 if projects_with_publish else 0)
    msg = f"Synced {wf_count} workflow(s), generated {router_count} router(s)."
    if stale_removed:
        msg += f" Removed {stale_removed} stale workflow(s)."
    print(msg)

def _cmd_status(flags):
    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)

    if not projects:
        print("No projects in workspace.")
        return

    rows = []
    for proj in projects:
        name = proj["name"]
        path = proj["path"]

        # Detect target
        targets = detect_targets(path)
        target_name = targets[0] if targets else "none"

        # Read version
        version = "?"
        if target_name != "none" and target_name in TARGETS:
            try:
                version = TARGETS[target_name].read_version(path)
            except Exception:
                version = "?"

        # Find latest tag
        latest_tag = "(none)"
        latest_tag_version = None
        try:
            result = subprocess.run(
                ["git", "tag", "-l", f"{name}@v*", "--sort=-v:refname"],
                capture_output=True, text=True, check=True,
            )
            first_line = result.stdout.strip().split("\n")[0].strip() if result.stdout.strip() else ""
            if first_line:
                latest_tag = first_line
                # Extract version from tag like "name@v1.2.3"
                prefix = f"{name}@v"
                if first_line.startswith(prefix):
                    latest_tag_version = first_line[len(prefix):]
        except Exception:
            pass

        # Count unreleased changelog entries
        changelog_path = os.path.join(path, "CHANGELOG.md")
        if not os.path.isfile(changelog_path):
            unreleased_str = "no changelog"
        else:
            with open(changelog_path, "r") as f:
                changelog_text = f.read()
            if latest_tag_version is None:
                # No tag: count all bullet lines across all ## sections
                count = sum(1 for line in changelog_text.splitlines() if line.startswith("- "))
            else:
                # Count bullet lines in ## sections above the tagged version
                tag_pattern = re.compile(r"^## " + re.escape(latest_tag_version) + r"(\s|$)", re.MULTILINE)
                match = tag_pattern.search(changelog_text)
                if match:
                    above = changelog_text[:match.start()]
                    count = sum(1 for line in above.splitlines() if line.startswith("- "))
                else:
                    # Tagged version not found in changelog: count all bullets
                    count = sum(1 for line in changelog_text.splitlines() if line.startswith("- "))
            if count == 0:
                unreleased_str = "0"
            elif count == 1:
                unreleased_str = "1 entry"
            else:
                unreleased_str = f"{count} entries"

        rows.append((name, path, target_name, version, latest_tag, unreleased_str))

    # Calculate column widths
    headers = ("Project", "Path", "Target", "Version", "Tag", "Unreleased")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Print header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)

    # Print rows
    for row in rows:
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        print(line)
