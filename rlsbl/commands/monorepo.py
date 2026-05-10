"""Monorepo workspace management commands."""

import sys

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
    print("monorepo init: not yet implemented", file=sys.stderr)
    sys.exit(1)

def _cmd_add(args, flags):
    print("monorepo add: not yet implemented", file=sys.stderr)
    sys.exit(1)

def _cmd_remove(args, flags):
    print("monorepo remove: not yet implemented", file=sys.stderr)
    sys.exit(1)

def _cmd_list(flags):
    print("monorepo list: not yet implemented", file=sys.stderr)
    sys.exit(1)

def _cmd_sync(flags):
    print("monorepo sync: not yet implemented", file=sys.stderr)
    sys.exit(1)

def _cmd_status(flags):
    print("monorepo status: not yet implemented", file=sys.stderr)
    sys.exit(1)
