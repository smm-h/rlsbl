"""Monorepo workspace management commands."""

import os
import re
import subprocess
import sys
import time

from ..workspace import find_workspace_root, load_workspace, save_workspace, WORKSPACE_DIR, WORKSPACE_FILE
from ..workspace_graph import WorkspaceGraph
from ..targets import detect_targets, TARGETS

def _auto_commit(message, files):
    """Best-effort commit of specific files. Failures are silently ignored."""
    try:
        subprocess.run(
            ["safegit", "commit", "-m", message, "--"] + files,
            check=True, capture_output=True, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


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

    target_entries = detect_targets(path)
    if not target_entries:
        print(f"Error: No release target detected in '{path}'. Initialize a project first.", file=sys.stderr)
        print("Hint: create a project manifest (e.g., package.json, pyproject.toml, go.mod, version.json) in the directory.", file=sys.stderr)
        sys.exit(1)

    name = flags.get("name") or os.path.basename(path.rstrip("/"))
    watch_raw = flags.get("watch")
    subtree_remote = flags.get("subtree-remote")

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

    project = {"path": path, "name": name}
    if watch_raw:
        project["watch"] = [w.strip() for w in watch_raw.split(",")]
    if subtree_remote:
        project["subtree_remote"] = subtree_remote
    projects.append(project)
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


def _inject_working_directory(content, path):
    """Insert a defaults.run.working-directory block before the jobs: line."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == "jobs:":
            block = [
                "defaults:",
                "  run:",
                f"    working-directory: {path}",
                "",
            ]
            new_lines = lines[:i] + block + lines[i:]
            return "\n".join(new_lines) + "\n"
    # No jobs: line found; return content unchanged
    return content


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
        watch = p.get("watch", [])
        if watch:
            lines.append(f"            {p['name']}:")
            lines.append(f"              - '{p['path']}/**'")
            for w in watch:
                lines.append(f"              - '{w}'")
        else:
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

            # Rewrite trigger and inject working directory
            rewritten = _rewrite_trigger(content)
            rewritten = _inject_working_directory(rewritten, path)

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

    # Warn about Swift projects without subtree_remote
    for proj in projects:
        proj_targets = detect_targets(proj["path"])
        if any(te.name in ("swift", "swift-apple") for te in proj_targets):
            if not proj.get("subtree_remote"):
                print(
                    f"Warning: Swift project '{proj['name']}' has no subtree_remote configured. "
                    "SPM consumers won't be able to resolve monorepo tags.",
                    file=sys.stderr,
                )

def _cmd_status(flags):
    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)

    if not projects:
        print("No projects in workspace.")
        return

    # Build dependency graph
    graph = WorkspaceGraph(root, projects)

    rows = []
    for proj in projects:
        name = proj["name"]
        path = proj["path"]

        # Detect target
        target_entries = detect_targets(path)
        target_name = target_entries[0].name if target_entries else "none"

        # Read version
        version = "?"
        if target_name != "none" and target_name in TARGETS:
            target_path = target_entries[0].path if target_entries else path
            try:
                version = TARGETS[target_name].read_version(target_path)
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

        # Dependency counts
        deps_count = graph.dep_count(name)
        rdeps_count = graph.rdep_count(name)
        deps_str = str(deps_count) if deps_count else "0"
        rdeps_str = str(rdeps_count) if rdeps_count else "0"

        # Watch paths
        watch = proj.get("watch", [])
        watch_str = f"{len(watch)} paths" if watch else "-"

        # Subtree remote
        remote = proj.get("subtree_remote", "")
        remote_str = remote if remote else "-"

        rows.append((name, path, target_name, version, latest_tag, unreleased_str, deps_str, rdeps_str, watch_str, remote_str))

    # Determine which dynamic columns to show
    any_deps = any(row[6] != "0" for row in rows)
    any_rdeps = any(row[7] != "0" for row in rows)
    any_watch = any(row[8] != "-" for row in rows)
    any_remote = any(row[9] != "-" for row in rows)

    # Calculate column widths
    base_headers = ("Project", "Path", "Target", "Version", "Tag", "Unreleased")
    if any_deps:
        base_headers = base_headers + ("Deps",)
    if any_rdeps:
        base_headers = base_headers + ("Rdeps",)
    if any_watch:
        base_headers = base_headers + ("Watch",)
    if any_remote:
        base_headers = base_headers + ("Remote",)
    headers = base_headers

    # Build display rows matching the dynamic header order
    display_rows = []
    for row in rows:
        cells = list(row[:6])  # base columns: name, path, target, version, tag, unreleased
        if any_deps:
            cells.append(row[6])
        if any_rdeps:
            cells.append(row[7])
        if any_watch:
            cells.append(row[8])
        if any_remote:
            cells.append(row[9])
        display_rows.append(tuple(cells))

    widths = [len(h) for h in headers]
    for cells in display_rows:
        for i in range(len(headers)):
            widths[i] = max(widths[i], len(cells[i]))

    # Print header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)

    # Print rows
    for cells in display_rows:
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))
        print(line)


def _cmd_check_names(args, flags):
    target = flags.get("target")
    if not target:
        print("Error: --target is required. Usage: rlsbl monorepo check-names --target <npm|pypi|go>", file=sys.stderr)
        sys.exit(1)

    prefix = flags.get("prefix", "")
    suffix = flags.get("suffix", "")
    delay_ms = int(flags.get("delay", "200"))

    root = find_workspace_root(".")
    if root is None:
        print("Error: No workspace found. Run 'rlsbl monorepo init' first.", file=sys.stderr)
        sys.exit(1)

    projects = load_workspace(root)
    if not projects:
        print("No projects in workspace.")
        return

    from .check import _check_single_name, _format_table_row

    rows = []
    for i, proj in enumerate(projects):
        checked_name = prefix + proj["name"] + suffix
        result = _check_single_name(checked_name, target)
        table_row = _format_table_row(result)
        rows.append({
            "project": proj["name"],
            "checked_name": checked_name,
            "status": table_row["status"],
        })
        if i < len(projects) - 1:
            time.sleep(delay_ms / 1000)

    # Compute column widths
    proj_width = max(len("Project"), max(len(r["project"]) for r in rows))
    name_width = max(len("Checked Name"), max(len(r["checked_name"]) for r in rows))
    status_width = max(len("Status"), max(len(r["status"]) for r in rows))

    header = f"{'Project':<{proj_width}}  {'Checked Name':<{name_width}}  {'Status':<{status_width}}"
    print(header)
    for row in rows:
        line = f"{row['project']:<{proj_width}}  {row['checked_name']:<{name_width}}  {row['status']:<{status_width}}"
        print(line)


# --- Subcommand registry and dispatch ---

SUBCOMMANDS = {
    "init": (_cmd_init, "Initialize a monorepo workspace", "rlsbl monorepo init"),
    "add": (
        _cmd_add,
        "Add a project to the workspace",
        "rlsbl monorepo add <path> [--name <name>] [--watch <globs>] [--subtree-remote <url>]",
    ),
    "remove": (_cmd_remove, "Remove a project from the workspace", "rlsbl monorepo remove <path>"),
    "list": (_cmd_list, "List all projects in the workspace", "rlsbl monorepo list"),
    "sync": (_cmd_sync, "Sync CI workflows from projects to repo root", "rlsbl monorepo sync"),
    "status": (_cmd_status, "Show status of all projects", "rlsbl monorepo status"),
    "check-names": (
        _cmd_check_names,
        "Check name availability for all projects",
        "rlsbl monorepo check-names --target <npm|pypi|go> [--prefix <str>] [--suffix <str>] [--delay <ms>]",
    ),
}

# Subcommands whose handlers accept (args, flags) instead of just (flags)
_SUBCOMMANDS_WITH_ARGS = {"add", "remove", "check-names"}


def _print_subcommand_list():
    """Print the list of all monorepo subcommands with aligned descriptions."""
    print("Usage: rlsbl monorepo <subcommand>\n")
    print("Subcommands:")
    max_name_len = max(len(name) for name in SUBCOMMANDS)
    for name, (_, description, _) in SUBCOMMANDS.items():
        padding = " " * (max_name_len - len(name) + 4)
        print(f"  {name}{padding}{description}")


def _print_subcommand_help(name):
    """Print help for a specific subcommand."""
    _, description, usage = SUBCOMMANDS[name]
    print(f"{description}\n")
    print(f"Usage: {usage}")


def run_cmd(registry, args, flags):
    """Dispatch to monorepo subcommand."""
    if not args or (len(args) == 1 and args[0] == "--help"):
        _print_subcommand_list()
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand not in SUBCOMMANDS:
        print(f"Error: unknown monorepo subcommand '{subcommand}'.", file=sys.stderr)
        valid = ", ".join(SUBCOMMANDS)
        print(f"Valid subcommands: {valid}", file=sys.stderr)
        sys.exit(1)

    if "--help" in sub_args:
        _print_subcommand_help(subcommand)
        return

    handler, _, _ = SUBCOMMANDS[subcommand]
    if subcommand in _SUBCOMMANDS_WITH_ARGS:
        handler(sub_args, flags)
    else:
        handler(flags)
