# Monorepo: spurious .rlsbl/ directory created at repo root

## Problem

In a monorepo setup (using `.rlsbl-monorepo/workspace.toml`), running `rlsbl release` on a sub-project creates a `.rlsbl/` directory at the repository root containing a `lock` file and possibly other runtime state.

This is confusing because:
- The monorepo config lives in `.rlsbl-monorepo/`
- Each sub-project has its own `.rlsbl/` (e.g. `ios/.rlsbl/`)
- A root `.rlsbl/` looks like it should be a config directory but is actually just runtime artifacts
- It requires a gitignore entry (`/.rlsbl/`) to hide it

## Expected behavior

Runtime state (lock files, etc.) should go inside either:
- The sub-project's `.rlsbl/` directory, or
- The `.rlsbl-monorepo/` directory

No `.rlsbl/` directory should be created at the repo root in monorepo setups.

## Reproduction

1. Set up a monorepo with `.rlsbl-monorepo/workspace.toml`
2. Run `rlsbl release` on any sub-project
3. Observe `.rlsbl/` created at repo root with a `lock` file

## Observed in

incantino monorepo (6 sub-projects in workspace.toml)
