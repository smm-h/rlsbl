# Migrate CLI dispatch to strictcli

## Problem

rlsbl has ~300 lines of hand-rolled CLI dispatch in `rlsbl/__init__.py`: custom `parse_args()`, `VALUE_FLAGS` whitelist, manual command routing, monolithic help string, no per-command help.

## Solution

Replace with [strictcli](https://github.com/smm-h/strictcli), an explicit zero-dependency CLI framework built specifically for this use case.

## What changes

- `parse_args()` and `VALUE_FLAGS` -> `@strictcli.flag` declarations with `type=str`/`type=bool`
- Command dispatch switch -> `@app.command` and `@group.command` decorators
- Monolithic `HELP` string -> auto-generated per-command help from mandatory help text
- `COMMAND_ALIASES` -> deferred (aliases not yet in strictcli v1)
- Env var handling (if any) -> `env=` on flags with prefix enforcement
- monorepo subcommands -> `app.group('monorepo', help='...')` with nested commands

## Affected files

- `rlsbl/__init__.py` (main dispatch, ~300 lines replaced)
- `rlsbl/commands/*.py` (each command module's `run_cmd` signature may change)
- `pyproject.toml` (add strictcli dependency)

## Effort

Medium. The 16 commands and monorepo subcommands need individual migration, but each is mechanical: declare flags, write handler, register.
