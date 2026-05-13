"""rlsbl: Release orchestration and project scaffolding for npm, PyPI, and Go."""

import os
import subprocess
import sys


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

COMMANDS = ("release", "status", "scaffold", "check", "undo", "discover", "watch",
            "pre-push-check", "prs", "record-gif", "unreleased", "targets", "monorepo",
            "migrate", "doctor", "deploy")
COMMAND_ALIASES = {"init": "scaffold"}

HELP = f"""\
rlsbl v{__version__} -- Release orchestration and project scaffolding for npm, PyPI, and Go

Usage:
  rlsbl release [patch|minor|major] [--dry-run] [--yes] [--quiet] [--skip-remote-check] [--allow-dirty]
                                                            Orchestrate a release
  rlsbl status                                              Show project status
  rlsbl scaffold [--force] [--update] [--private] [--no-commit] [--skip-shared]
                                                            Scaffold release infrastructure
  rlsbl check <name> [<name2> ...] --target <npm|pypi|go>     Check name availability
  rlsbl undo [--yes]                                        Revert the last release
  rlsbl discover [--mine]                                   List rlsbl ecosystem projects
  rlsbl watch [<commit-sha>]                                Watch CI runs for a commit
  rlsbl prs                                                 List open pull requests
  rlsbl pre-push-check                                     Verify CHANGELOG entry for current version
  rlsbl unreleased [--json]                                 Audit changelog coverage for unreleased commits
  rlsbl targets                                             List available release targets
  rlsbl monorepo [init|add|remove|list|sync|status|check-names]
                                                            Manage monorepo workspaces
  rlsbl migrate [--dry-run] [--status]              Run config migrations (via migrable)
  rlsbl deploy [name] [--dry-run] [--force]             Deploy to configured targets
  rlsbl doctor [--fix] [--check <name>]                 Diagnose and repair release state
  rlsbl record-gif [--width N] [--height N] [--font-size N] [--duration N]
                                                            Record a demo GIF with vhs

Options:
  --target <npm|pypi|go>    Target a specific registry (auto-detected if omitted)
  --registry <npm|pypi|go>  Deprecated alias for --target
  --no-tag               Disable ecosystem tagging for this invocation
  --private              Scaffold for private repos (skip publish, add asset upload hook)
  --help, -h             Show this help
  --version, -v          Show version"""


def detect_registries():
    """Detect all registries/targets applicable in the current directory.

    Returns a list of name strings, e.g. ["npm"], ["pypi"], or ["npm", "pypi"].
    Delegates to detect_targets() so all registered targets (including docker,
    cargo, deno, hex, maven, etc.) are auto-detected when no config exists.
    """
    from .targets import detect_targets
    return [entry.name for entry in detect_targets(".")]


def parse_args(argv):
    """Parse sys.argv into positional args and flags.

    Flags listed in VALUE_FLAGS consume the next token as their value
    (e.g. --registry npm). All other --flags are boolean.
    """
    VALUE_FLAGS = ("registry", "target", "width", "height", "font-size", "duration",
                   "name", "watch", "subtree-remote", "delay", "prefix", "suffix",
                   "depends-on", "library", "check")
    raw = argv[1:]
    positional = []
    flags = {}
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg.startswith("--"):
            key = arg[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                flags[k] = v
            elif key in VALUE_FLAGS and i + 1 < len(raw) and not raw[i + 1].startswith("-"):
                flags[key] = raw[i + 1]
                i += 1
            else:
                flags[key] = True
        elif arg.startswith("-") and len(arg) == 2:
            flags[arg[1:]] = True
        else:
            positional.append(arg)
        i += 1
    return positional, flags


def _get_command_module(command):
    """Import and return the command module for the given command name."""
    # Map CLI command names to Python module names
    module_map = {
        "release": "release",
        "status": "status",
        "scaffold": "init_cmd",
        "check": "check",
        "undo": "undo",
        "discover": "discover",
        "watch": "watch",
        "pre-push-check": "pre_push_check",
        "prs": "prs",
        "record-gif": "record_gif",
        "unreleased": "unreleased",
        "targets": "targets_cmd",
        "monorepo": "monorepo",
        "migrate": "migrate",
        "doctor": "doctor",
        "deploy": "deploy_cmd",
    }
    module_name = module_map.get(command)
    if not module_name:
        return None

    # Import the command module
    from importlib import import_module
    return import_module(f".commands.{module_name}", package="rlsbl")


def main():
    positional, flags = parse_args(sys.argv)

    # Top-level flags
    if flags.get("help") or flags.get("h"):
        print(HELP)
        sys.exit(0)

    if flags.get("version") or flags.get("v"):
        print(__version__)
        sys.exit(0)

    command = positional[0] if positional else None

    # Resolve command aliases (e.g. "init" -> "scaffold")
    if command in COMMAND_ALIASES:
        command = COMMAND_ALIASES[command]

    if not command:
        print("Error: missing command.\n", file=sys.stderr)
        print(HELP, file=sys.stderr)
        sys.exit(1)

    if command not in COMMANDS:
        print(f'Error: unknown command "{command}".\n', file=sys.stderr)
        print(HELP, file=sys.stderr)
        sys.exit(1)

    # Project root discovery: chdir to project root for commands that need it
    from .utils import find_project_root

    NEEDS_PROJECT = {"release", "status", "doctor", "pre-push-check", "unreleased", "record-gif", "targets", "deploy"}

    if command in NEEDS_PROJECT:
        root = find_project_root()
        if root is None:
            print("Error: not in an rlsbl project (no .rlsbl/ found in any ancestor directory).", file=sys.stderr)
            sys.exit(1)
        os.chdir(root)
    elif command == "scaffold":
        # Scaffold creates .rlsbl/ for new projects; for existing projects, find the root
        root = find_project_root()
        if root is not None:
            os.chdir(root)

    args = positional[1:]
    registry = flags.get("registry")
    target = flags.get("target")

    # Emit deprecation warning when --registry is used directly
    if registry and registry is not True:
        print("Warning: --registry is deprecated, use --target instead", file=sys.stderr)

    # --registry was the last arg with no value following it
    if registry is True:
        print("Error: --registry requires a value (npm, pypi, or go).", file=sys.stderr)
        sys.exit(1)

    # --target is an alias for --registry
    if target is True:
        print("Error: --target requires a value (npm, pypi, or go).", file=sys.stderr)
        sys.exit(1)

    # --target acts as alias for --registry; error if both given with different values
    if target and registry and target != registry:
        print("Error: --target and --registry conflict. Use one or the other.", file=sys.stderr)
        sys.exit(1)
    if target and not registry:
        registry = target
        flags["registry"] = target

    # Validate --registry/--target if provided
    if registry:
        from .targets import TARGETS
        if registry not in TARGETS:
            print(
                f"Error: unknown target '{registry}'. Valid: {', '.join(TARGETS.keys())}",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        handler = _get_command_module(command)
        if handler is None:
            print(f'Error: command "{command}" is not yet implemented.', file=sys.stderr)
            sys.exit(1)

        if command == "check":
            if not registry:
                print(
                    "Error: --target is required. "
                    "Usage: rlsbl check <name> --target <npm|pypi|go>",
                    file=sys.stderr,
                )
                sys.exit(1)
            handler.run_cmd(registry, args, flags)
        elif command == "scaffold":
            if registry:
                handler.run_cmd(registry, args, flags)
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
                    handler.run_cmd_multi(regs, args, flags)
                else:
                    handler.run_cmd(regs[0], args, flags)
        elif command == "discover":
            # discover: global query, no registry needed
            handler.run_cmd(registry, args, flags)
        elif command == "watch":
            # watch: monitors CI runs, no registry needed
            handler.run_cmd(registry, args, flags)
        elif command in ("pre-push-check", "record-gif", "prs", "unreleased", "targets", "monorepo", "migrate", "doctor", "deploy", "undo"):
            # Standalone commands, no registry needed
            handler.run_cmd(registry, args, flags)
        else:
            # release, status: use explicit registry or auto-detect primary
            if not registry:
                regs = detect_registries()
                if not regs:
                    print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
                    sys.exit(1)
                registry = regs[0]
            handler.run_cmd(registry, args, flags)
    except subprocess.CalledProcessError as e:
        if e.stderr and e.stderr.strip():
            print(f"Error: {e.stderr.strip()}", file=sys.stderr)
        else:
            print(f"Error: Command failed: {e.cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
