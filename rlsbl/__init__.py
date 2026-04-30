"""rlsbl: Release orchestration and project scaffolding for npm and PyPI."""

import os
import sys

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("rlsbl")
except Exception:
    __version__ = "unknown"

REGISTRIES = ("npm", "pypi")
COMMANDS = ("release", "status", "scaffold", "check-name")
COMMAND_ALIASES = {"init": "scaffold"}

HELP = f"""\
rlsbl v{__version__} -- Release orchestration and project scaffolding for npm and PyPI

Usage:
  rlsbl release [patch|minor|major] [--dry-run] [--quiet]  Orchestrate a release
  rlsbl status                                             Show project status
  rlsbl scaffold [--force] [--update]                       Scaffold release infrastructure
  rlsbl check-name <name>                                  Check name availability

  Registry-specific (when you need to target one):
  rlsbl <registry> <command> [args...]

Registries: {', '.join(REGISTRIES)}"""


def detect_registries():
    """Detect all registries that have a project file in the current directory.

    Returns a list, e.g. ["npm"], ["pypi"], or ["npm", "pypi"].
    """
    found = []
    if os.path.exists("package.json"):
        found.append("npm")
    if os.path.exists("pyproject.toml"):
        found.append("pypi")
    return found


def parse_args(argv):
    """Parse sys.argv into positional args and flags."""
    raw = argv[1:]
    positional = []
    flags = {}

    for arg in raw:
        if arg.startswith("--"):
            flags[arg[2:]] = True
        elif arg.startswith("-") and len(arg) == 2:
            flags[arg[1:]] = True
        else:
            positional.append(arg)

    return positional, flags


def _get_command_module(command):
    """Import and return the command module for the given command name."""
    # Map CLI command names to Python module names
    module_map = {
        "release": "release",
        "status": "status",
        "scaffold": "init_cmd",
        "check-name": "check_name",
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

    first = positional[0] if positional else None

    # Resolve command aliases (e.g. "init" -> "scaffold")
    if first in COMMAND_ALIASES:
        first = COMMAND_ALIASES[first]

    if not first:
        print("Error: missing command.\n", file=sys.stderr)
        print(HELP, file=sys.stderr)
        sys.exit(1)

    registry = None
    command = None
    args = []

    if first in COMMANDS:
        # Top-level: rlsbl <command> ... -- auto-detect registry
        command = first
        args = positional[1:]
    elif first in REGISTRIES:
        # Registry-prefixed: rlsbl <registry> <command> ...
        registry = first
        command = positional[1] if len(positional) > 1 else None
        if command and command in COMMAND_ALIASES:
            command = COMMAND_ALIASES[command]

        if not command:
            print(f'Error: missing command for registry "{registry}".\n', file=sys.stderr)
            print(HELP, file=sys.stderr)
            sys.exit(1)

        if command not in COMMANDS:
            print(
                f'Error: unknown command "{command}". Valid commands: {", ".join(COMMANDS)}\n',
                file=sys.stderr,
            )
            print(HELP, file=sys.stderr)
            sys.exit(1)

        args = positional[2:]
    else:
        print(f'Error: unknown command or registry "{first}".\n', file=sys.stderr)
        print(HELP, file=sys.stderr)
        sys.exit(1)

    try:
        handler = _get_command_module(command)
        if handler is None:
            print(f'Error: command "{command}" is not yet implemented.', file=sys.stderr)
            sys.exit(1)

        if registry:
            # Explicit registry -- single invocation
            handler.run_cmd(registry, args, flags)
        elif command == "check-name":
            # Top-level check-name: check ALL registries
            regs = ["npm", "pypi"]
            for i, r in enumerate(regs):
                handler.run_cmd(r, args, flags)
                if i < len(regs) - 1:
                    print("")
        elif command == "scaffold":
            # Top-level scaffold: scaffold for each detected registry
            regs = detect_registries()
            if not regs:
                print("Error: no package.json or pyproject.toml found.", file=sys.stderr)
                sys.exit(1)
            if len(regs) > 1:
                # Multi-registry: only scaffold for the primary registry
                # (CI/publish workflows conflict when both registries target the same paths)
                print(f"Multiple registries detected: {', '.join(regs)}")
                print(f"Scaffolding for primary registry: {regs[0]}")
                print("For dual-registry projects, manually configure workflows with both jobs.")
            handler.run_cmd(regs[0], args, flags)
        else:
            # Top-level release/status: use primary detected registry
            regs = detect_registries()
            if not regs:
                print("Error: no package.json or pyproject.toml found.", file=sys.stderr)
                sys.exit(1)
            handler.run_cmd(regs[0], args, flags)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
