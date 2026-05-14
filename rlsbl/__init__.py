"""rlsbl: Release orchestration and project scaffolding for npm, PyPI, and Go."""

import os
import subprocess
import sys

import strictcli


def _detect_version():
    """Detect package version, preferring pyproject.toml over installed metadata.

    Order: pyproject.toml in the source tree (accurate during editable installs)
    -> importlib.metadata (works for regular installs) -> "unknown".
    """
    # Try reading version from pyproject.toml next to the package source
    try:
        pyproject_path = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        )
        if os.path.isfile(pyproject_path):
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return data["project"]["version"]
    except Exception:
        pass

    # Fall back to installed dist-info metadata
    try:
        from importlib.metadata import version as _get_version
        return _get_version("rlsbl")
    except Exception:
        pass

    return "unknown"


__version__ = _detect_version()

# Module-level storage for variadic positional args that strictcli cannot
# handle natively. Populated by main() before app.run().
_variadic_args: list[str] = []


def detect_registries():
    """Detect all registries/targets applicable in the current directory.

    Returns a list of name strings, e.g. ["npm"], ["pypi"], or ["npm", "pypi"].
    Delegates to detect_targets() so all registered targets (including docker,
    cargo, deno, hex, maven, etc.) are auto-detected when no config exists.
    """
    from .targets import detect_targets
    return [entry.name for entry in detect_targets(".")]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _require_project_root():
    """Find the rlsbl project root, chdir to it, or exit with an error."""
    from .utils import find_project_root
    root = find_project_root()
    if root is None:
        print("Error: not in an rlsbl project (no .rlsbl/ found in any ancestor directory).", file=sys.stderr)
        sys.exit(1)
    os.chdir(root)


def _resolve_target(target):
    """Validate and resolve a --target flag value.

    If target is a string, validates it against TARGETS. If None,
    auto-detects from the current directory. Returns the resolved
    registry name string or exits on error.
    """
    from .targets import TARGETS
    if target:
        if target not in TARGETS:
            print(
                f"Error: unknown target '{target}'. Valid: {', '.join(TARGETS.keys())}",
                file=sys.stderr,
            )
            sys.exit(1)
        return target
    # Auto-detect
    regs = detect_registries()
    if not regs:
        print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
        sys.exit(1)
    return regs[0]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = strictcli.App(
    name="rlsbl",
    version=__version__,
    help="Release orchestration and project scaffolding for npm, PyPI, and Go",
)


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

@app.command(name="release", help="Orchestrate a release")
@strictcli.flag(name="target", type=str, help="Target a specific registry (auto-detected if omitted)", default="")
@strictcli.flag(name="dry-run", type=bool, help="Preview release without making changes")
@strictcli.flag(name="yes", type=bool, help="Non-interactive mode (skip confirmations)")
@strictcli.flag(name="quiet", type=bool, help="Suppress non-essential output")
@strictcli.flag(name="skip-remote-check", type=bool, help="Skip the remote-ahead check")
@strictcli.flag(name="skip-tests", type=bool, help="Skip built-in test execution")
@strictcli.flag(name="skip-lint", type=bool, help="Skip built-in library lint")
@strictcli.flag(name="allow-dirty", type=bool, help="Allow releasing with a dirty working tree")
@strictcli.flag(name="no-tag", type=bool, help="Disable ecosystem tagging for this invocation")
@strictcli.arg(name="bump", help="Bump type: patch, minor, or major", required=False)
def cmd_release(target, dry_run, yes, quiet, skip_remote_check, skip_tests, skip_lint, allow_dirty, no_tag, bump=None):
    _require_project_root()
    registry = _resolve_target(target or None)
    args = [bump] if bump else []
    flags = {
        "dry-run": dry_run,
        "yes": yes,
        "quiet": quiet,
        "skip-remote-check": skip_remote_check,
        "skip-tests": skip_tests,
        "skip-lint": skip_lint,
        "allow-dirty": allow_dirty,
        "no-tag": no_tag,
    }
    from .commands.release import run_cmd
    run_cmd(registry, args, flags)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command(name="status", help="Show project status")
@strictcli.flag(name="target", type=str, help="Target a specific registry (auto-detected if omitted)", default="")
@strictcli.flag(name="json", type=bool, help="Output status as JSON")
def cmd_status(target, json):
    _require_project_root()
    registry = _resolve_target(target or None)
    flags = {"json": json}
    from .commands.status import run_cmd
    run_cmd(registry, [], flags)


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

@app.command(name="scaffold", help="Scaffold release infrastructure")
@strictcli.flag(name="target", type=str, help="Target a specific registry (auto-detected if omitted)", default="")
@strictcli.flag(name="force", type=bool, help="Overwrite all files (ignore user customizations)")
@strictcli.flag(name="update", type=bool, help="Update scaffolding via three-way merge")
@strictcli.flag(name="private", type=bool, help="Scaffold for private repos (skip publish)")
@strictcli.flag(name="no-commit", type=bool, help="Skip auto-commit of scaffolded files")
@strictcli.flag(name="skip-shared", type=bool, help="Skip shared template processing")
@strictcli.flag(name="no-tag", type=bool, help="Disable ecosystem tagging for this invocation")
def cmd_scaffold(target, force, update, private, no_commit, skip_shared, no_tag):
    # Scaffold is special: if a project root exists, chdir to it;
    # if not, stay in cwd (for new projects).
    from .utils import find_project_root
    root = find_project_root()
    if root is not None:
        os.chdir(root)

    flags = {
        "force": force,
        "update": update,
        "private": private,
        "no-commit": no_commit,
        "skip-shared": skip_shared,
        "no-tag": no_tag,
    }

    resolved_target = target or None
    if resolved_target:
        from .targets import TARGETS
        if resolved_target not in TARGETS:
            print(
                f"Error: unknown target '{resolved_target}'. Valid: {', '.join(TARGETS.keys())}",
                file=sys.stderr,
            )
            sys.exit(1)
        from .commands.init_cmd import run_cmd
        run_cmd(resolved_target, [], flags)
    else:
        regs = detect_registries()
        if not regs:
            print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
            sys.exit(1)
        # Warn when auto-detection is used without explicit config
        from .config import read_project_config
        cfg = read_project_config()
        if "targets" not in cfg:
            print(
                f"Note: Auto-detected target(s): {', '.join(regs)}. "
                "Run 'rlsbl scaffold' again after reviewing .rlsbl/config.json.",
                file=sys.stderr,
            )
        if len(regs) > 1:
            from .commands.init_cmd import run_cmd_multi
            run_cmd_multi(regs, [], flags)
        else:
            from .commands.init_cmd import run_cmd
            run_cmd(regs[0], [], flags)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

@app.command(name="check", help="Check name availability on a registry")
@strictcli.flag(name="target", type=str, help="Target registry (npm, pypi, or go)")
@strictcli.flag(name="delay", type=str, help="Delay between checks in ms", default="200")
def cmd_check(target, delay):
    # --target is required for check
    if not target:
        print(
            "Error: --target is required. "
            "Usage: rlsbl check <name> [<name2> ...] --target <npm|pypi|go>",
            file=sys.stderr,
        )
        sys.exit(1)
    from .targets import TARGETS
    if target not in TARGETS:
        print(
            f"Error: unknown target '{target}'. Valid: {', '.join(TARGETS.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)
    # Names come from _variadic_args (extracted before strictcli parsing)
    names = _variadic_args
    flags = {"delay": delay}
    from .commands.check import run_cmd
    run_cmd(target, names, flags)


# ---------------------------------------------------------------------------
# edit-release
# ---------------------------------------------------------------------------

@app.command(name="edit-release", help="Update GitHub Release notes from CHANGELOG.md")
@strictcli.flag(name="dry-run", type=bool, help="Preview without making changes")
@strictcli.arg(name="version", help="Version to update (defaults to current)", required=False)
def cmd_edit_release(dry_run, version=None):
    _require_project_root()
    args = [version] if version else []
    flags = {"dry-run": dry_run}
    from .commands.edit_release import run_cmd
    run_cmd(args, flags)


# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------

@app.command(name="undo", help="Revert the last release")
@strictcli.flag(name="target", type=str, help="Target a specific registry", default="")
@strictcli.flag(name="yes", type=bool, help="Non-interactive mode (skip confirmations)")
def cmd_undo(target, yes):
    flags = {"yes": yes}
    from .commands.undo import run_cmd
    run_cmd(target or None, [], flags)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

@app.command(name="discover", help="List rlsbl ecosystem projects")
@strictcli.flag(name="mine", type=bool, help="Show only your own repositories")
def cmd_discover(mine):
    flags = {"mine": mine}
    from .commands.discover import run_cmd
    run_cmd(None, [], flags)


# ---------------------------------------------------------------------------
# watch
# ---------------------------------------------------------------------------

@app.command(name="watch", help="Watch CI runs for a commit")
@strictcli.flag(name="target", type=str, help="Target a specific registry", default="")
@strictcli.arg(name="sha", help="Commit SHA to watch (defaults to HEAD)", required=False)
def cmd_watch(target, sha=None):
    args = [sha] if sha else []
    from .commands.watch import run_cmd
    run_cmd(target or None, args, {})


# ---------------------------------------------------------------------------
# pre-push-check
# ---------------------------------------------------------------------------

@app.command(name="pre-push-check", help="Verify CHANGELOG entry for current version")
def cmd_pre_push_check():
    _require_project_root()
    from .commands.pre_push_check import run_cmd
    run_cmd(None, [], {})


# ---------------------------------------------------------------------------
# prs
# ---------------------------------------------------------------------------

@app.command(name="prs", help="List open pull requests")
def cmd_prs():
    from .commands.prs import run_cmd
    run_cmd(None, [], {})


# ---------------------------------------------------------------------------
# unreleased
# ---------------------------------------------------------------------------

@app.command(name="unreleased", help="Audit changelog coverage for unreleased commits")
@strictcli.flag(name="json", type=bool, help="Output as JSON")
def cmd_unreleased(json):
    _require_project_root()
    flags = {"json": json}
    from .commands.unreleased import run_cmd
    run_cmd(None, [], flags)


# ---------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------

@app.command(name="targets", help="List available release targets")
def cmd_targets():
    _require_project_root()
    from .commands.targets_cmd import run_cmd
    run_cmd(None, [], {})


# ---------------------------------------------------------------------------
# record-gif
# ---------------------------------------------------------------------------

@app.command(name="record-gif", help="Record a demo GIF with vhs")
@strictcli.flag(name="width", type=str, help="GIF width in pixels", default="1200")
@strictcli.flag(name="height", type=str, help="GIF height in pixels", default="600")
@strictcli.flag(name="font-size", type=str, help="Font size in pixels", default="24")
@strictcli.flag(name="duration", type=str, help="Duration in seconds", default="10")
def cmd_record_gif(width, height, font_size, duration):
    _require_project_root()
    flags = {"width": width, "height": height, "font-size": font_size, "duration": duration}
    from .commands.record_gif import run_cmd
    run_cmd(None, [], flags)


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

@app.command(name="migrate", help="Run config migrations (via migrable)")
@strictcli.flag(name="dry-run", type=bool, help="Preview migrations without applying")
@strictcli.flag(name="status", type=bool, help="Show migration status")
def cmd_migrate(dry_run, status):
    flags = {"dry-run": dry_run, "status": status}
    from .commands.migrate import run_cmd
    run_cmd(None, [], flags)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

@app.command(name="doctor", help="Diagnose and repair release state")
@strictcli.flag(name="fix", type=bool, help="Auto-fix issues where possible")
@strictcli.flag(name="check", type=str, help="Run a specific check by name", default="")
def cmd_doctor(fix, check):
    _require_project_root()
    flags = {"fix": fix, "check": check or None}
    from .commands.doctor import run_cmd
    run_cmd(None, [], flags)


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------

@app.command(name="deploy", help="Deploy to configured targets")
@strictcli.flag(name="target", type=str, help="Target a specific registry", default="")
@strictcli.flag(name="dry-run", type=bool, help="Show what would be deployed")
@strictcli.flag(name="force", type=bool, help="Override branch restrictions")
@strictcli.arg(name="target_name", help="Deploy target name", required=False)
def cmd_deploy(target, dry_run, force, target_name=None):
    _require_project_root()
    args = [target_name] if target_name else []
    flags = {"dry-run": dry_run, "force": force}
    from .commands.deploy_cmd import run_cmd
    run_cmd(target or None, args, flags)


# ---------------------------------------------------------------------------
# changelog group
# ---------------------------------------------------------------------------

chlog = app.group("changelog", help="Structured changelog management")


@chlog.command(name="add", help="Add an entry to unreleased.jsonl")
@strictcli.flag(name="commits", type=str, help="Comma-separated commit hashes", default="")
@strictcli.flag(name="description", type=str, help="Entry description", default="")
@strictcli.flag(name="type", type=str, help="Entry type (feature, fix, breaking)", default="")
@strictcli.flag(name="no-user-facing", type=bool, help="Mark as non-user-facing")
@strictcli.flag(name="no-commit", type=bool, help="Skip auto-commit of unreleased.jsonl")
def cmd_chlog_add(commits, description, type, no_user_facing, no_commit):
    _require_project_root()
    flags = {
        "commits": commits,
        "description": description,
        "type": type,
        "no-user-facing": no_user_facing,
        "no-commit": no_commit,
    }
    from .commands.changelog_cmd import cmd_add
    cmd_add(flags)


@chlog.command(name="validate", help="Validate unreleased changelog entries")
def cmd_chlog_validate():
    _require_project_root()
    from .commands.changelog_cmd import cmd_validate
    cmd_validate({})


@chlog.command(name="generate", help="Generate CHANGELOG.md from JSONL files")
@strictcli.flag(name="dry-run", type=bool, help="Preview without writing files")
def cmd_chlog_generate(dry_run):
    _require_project_root()
    flags = {"dry-run": dry_run}
    from .commands.changelog_cmd import cmd_generate
    cmd_generate(flags)


# ---------------------------------------------------------------------------
# monorepo group
# ---------------------------------------------------------------------------

mono = app.group("monorepo", help="Monorepo workspace management")


@mono.command(name="init", help="Initialize a monorepo workspace")
def cmd_mono_init():
    from .commands.monorepo import _cmd_init
    _cmd_init({})


@mono.command(name="add", help="Add a project to the workspace")
@strictcli.flag(name="name", type=str, help="Project name (defaults to directory name)", default="")
@strictcli.flag(name="target", type=str, help="Target registry", default="")
@strictcli.flag(name="watch", type=str, help="Comma-separated glob patterns to watch", default="")
@strictcli.flag(name="subtree-remote", type=str, help="Subtree remote URL", default="")
@strictcli.flag(name="depends-on", type=str, help="Comma-separated dependency project names", default="")
@strictcli.flag(name="library", type=str, help="Mark as library (true/false)", default="")
@strictcli.arg(name="path", help="Path to the project directory")
def cmd_mono_add(name, target, watch, subtree_remote, depends_on, library, path):
    flags = {}
    if name:
        flags["name"] = name
    if target:
        flags["target"] = target
    if watch:
        flags["watch"] = watch
    if subtree_remote:
        flags["subtree-remote"] = subtree_remote
    if depends_on:
        flags["depends-on"] = depends_on
    if library:
        flags["library"] = library
    from .commands.monorepo import _cmd_add
    _cmd_add([path], flags)


@mono.command(name="remove", help="Remove a project from the workspace")
@strictcli.arg(name="path", help="Path to the project to remove")
def cmd_mono_remove(path):
    from .commands.monorepo import _cmd_remove
    _cmd_remove([path], {})


@mono.command(name="list", help="List all projects in the workspace")
def cmd_mono_list():
    from .commands.monorepo import _cmd_list
    _cmd_list({})


@mono.command(name="sync", help="Sync CI workflows from projects to repo root")
def cmd_mono_sync():
    from .commands.monorepo import _cmd_sync
    _cmd_sync({})


@mono.command(name="status", help="Show status of all projects")
def cmd_mono_status():
    from .commands.monorepo import _cmd_status
    _cmd_status({})


@mono.command(name="check-names", help="Check name availability for all projects")
@strictcli.flag(name="target", type=str, help="Target registry (npm, pypi, or go)")
@strictcli.flag(name="prefix", type=str, help="Prefix to prepend to project names", default="")
@strictcli.flag(name="suffix", type=str, help="Suffix to append to project names", default="")
@strictcli.flag(name="delay", type=str, help="Delay between checks in ms", default="200")
def cmd_mono_check_names(target, prefix, suffix, delay):
    flags = {"target": target, "prefix": prefix, "suffix": suffix, "delay": delay}
    from .commands.monorepo import _cmd_check_names
    _cmd_check_names(_variadic_args, flags)


@mono.command(name="release-order", help="Show topological release order for projects")
def cmd_mono_release_order():
    from .commands.monorepo import _cmd_release_order
    _cmd_release_order({})


@mono.command(name="outdated", help="Show outdated intra-workspace dependencies")
def cmd_mono_outdated():
    from .commands.monorepo import _cmd_outdated
    _cmd_outdated({})


# ---------------------------------------------------------------------------
# Variadic arg extraction
# ---------------------------------------------------------------------------

def _extract_variadic_args():
    """Extract variadic positional args from sys.argv for commands that need them.

    For 'check' and 'monorepo check-names', removes positional args from
    sys.argv and returns them. This must be called before app.run() since
    strictcli does not support variadic positional args.
    """
    argv = sys.argv[1:]
    if not argv:
        return []

    cmd = argv[0]

    if cmd == "check":
        # Everything after 'check' that doesn't start with '-' and isn't
        # a value following a flag is a positional name arg.
        positionals = []
        new_argv = [sys.argv[0], "check"]
        i = 1  # index into argv (after 'check')
        value_flags = {"target", "delay"}
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("--"):
                key = tok[2:]
                if "=" in key:
                    new_argv.append(tok)
                elif key in value_flags and i + 1 < len(argv):
                    new_argv.append(tok)
                    new_argv.append(argv[i + 1])
                    i += 1
                else:
                    new_argv.append(tok)
            elif tok.startswith("-"):
                new_argv.append(tok)
            else:
                positionals.append(tok)
            i += 1
        sys.argv = new_argv
        return positionals

    if cmd == "monorepo" and len(argv) > 1 and argv[1] == "check-names":
        # Same pattern for monorepo check-names
        positionals = []
        new_argv = [sys.argv[0], "monorepo", "check-names"]
        i = 2  # index into argv (after 'monorepo check-names')
        value_flags = {"target", "prefix", "suffix", "delay"}
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("--"):
                key = tok[2:]
                if "=" in key:
                    new_argv.append(tok)
                elif key in value_flags and i + 1 < len(argv):
                    new_argv.append(tok)
                    new_argv.append(argv[i + 1])
                    i += 1
                else:
                    new_argv.append(tok)
            elif tok.startswith("-"):
                new_argv.append(tok)
            else:
                positionals.append(tok)
            i += 1
        sys.argv = new_argv
        return positionals

    return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global _variadic_args
    _variadic_args = _extract_variadic_args()
    try:
        app.run()
    except subprocess.CalledProcessError as e:
        if e.stderr and e.stderr.strip():
            print(f"Error: {e.stderr.strip()}", file=sys.stderr)
        else:
            print(f"Error: Command failed: {e.cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
