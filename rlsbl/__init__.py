"""rlsbl: Release orchestration and project scaffolding for npm, PyPI, and Go."""

import os
import sys

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("rlsbl")
except Exception:
    __version__ = "unknown"

REGISTRIES = ("npm", "pypi", "go")
COMMANDS = ("release", "status", "scaffold", "check", "config", "undo", "discover")
COMMAND_ALIASES = {"init": "scaffold"}

HELP = f"""\
rlsbl v{__version__} -- Release orchestration and project scaffolding for npm, PyPI, and Go

Usage:
  rlsbl release [patch|minor|major] [--dry-run] [--yes] [--quiet]  Orchestrate a release
  rlsbl status                                              Show project status
  rlsbl scaffold [--force] [--update]                       Scaffold release infrastructure
  rlsbl check <name>                                        Check name availability
  rlsbl config                                              Show project configuration
  rlsbl undo [--yes]                                        Revert the last release
  rlsbl discover [--mine]                                   List rlsbl ecosystem projects

Options:
  --registry <npm|pypi|go>  Target a specific registry (auto-detected if omitted)
  --no-tag               Disable ecosystem tagging for this invocation
  --help, -h             Show this help
  --version, -v          Show version"""


def detect_registries():
    """Detect all registries that have a project file in the current directory.

    Returns a list, e.g. ["npm"], ["pypi"], or ["npm", "pypi"].
    """
    found = []
    if os.path.exists("package.json"):
        found.append("npm")
    if os.path.exists("pyproject.toml"):
        found.append("pypi")
    if os.path.exists("go.mod"):
        found.append("go")
    return found


def parse_args(argv):
    """Parse sys.argv into positional args and flags.

    Flags listed in VALUE_FLAGS consume the next token as their value
    (e.g. --registry npm). All other --flags are boolean.
    """
    VALUE_FLAGS = ("registry",)
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
        "config": "config",
        "undo": "undo",
        "discover": "discover",
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

    args = positional[1:]
    registry = flags.get("registry")

    # Validate --registry if provided
    if registry and registry not in REGISTRIES:
        print(
            f"Error: unknown registry '{registry}'. Valid: {', '.join(REGISTRIES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        handler = _get_command_module(command)
        if handler is None:
            print(f'Error: command "{command}" is not yet implemented.', file=sys.stderr)
            sys.exit(1)

        if command == "check":
            # check: if registry given, check that one; otherwise check all
            if registry:
                handler.run_cmd(registry, args, flags)
            else:
                all_registries = ["npm", "pypi", "go"]
                for i, r in enumerate(all_registries):
                    handler.run_cmd(r, args, flags)
                    if i < len(all_registries) - 1:
                        print("")
        elif command == "scaffold":
            if registry:
                handler.run_cmd(registry, args, flags)
            else:
                regs = detect_registries()
                if not regs:
                    print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
                    sys.exit(1)
                if len(regs) > 1:
                    handler.run_cmd_multi(regs, args, flags)
                else:
                    handler.run_cmd(regs[0], args, flags)
        elif command == "config":
            # config: auto-detect, pass first registry or fallback
            regs = detect_registries()
            handler.run_cmd(registry or (regs[0] if regs else "npm"), args, flags)
        elif command == "undo":
            # undo: auto-detect like release
            if not registry:
                regs = detect_registries()
                if not regs:
                    print("Error: no package.json, pyproject.toml, or go.mod found.", file=sys.stderr)
                    sys.exit(1)
                registry = regs[0]
            handler.run_cmd(registry, args, flags)
        elif command == "discover":
            # discover: global query, no registry needed
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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
