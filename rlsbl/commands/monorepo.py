"""Monorepo workspace management commands."""

import os
import subprocess
import sys

from ..workspace import find_workspace_root, load_workspace, save_workspace, WORKSPACE_DIR, WORKSPACE_FILE
from ..targets import detect_targets, TARGETS

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
        print(f"Error: Project at '{path}' not found in workspace.", file=sys.stderr)
        sys.exit(1)

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

def _cmd_sync(flags):
    print("monorepo sync: not yet implemented", file=sys.stderr)
    sys.exit(1)

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

        # Determine status
        if latest_tag_version is None:
            status = "unreleased"
        elif version != latest_tag_version:
            status = "unreleased"
        else:
            status = "released"

        rows.append((name, path, target_name, version, latest_tag, status))

    # Calculate column widths
    headers = ("Project", "Path", "Target", "Version", "Tag", "Status")
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
