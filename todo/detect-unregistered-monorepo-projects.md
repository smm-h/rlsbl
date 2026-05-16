# Detect unregistered monorepo projects

## Problem

When new projects are added to a monorepo (e.g., a new Go module or Python package in a directory), they can easily be forgotten from `.rlsbl-monorepo/workspace.toml`. This leads to:
- Missing CI coverage
- No release management for the new project
- Silent drift between what's in the repo and what rlsbl manages

## Proposed solution

Add a `rlsbl monorepo lint` (or `rlsbl monorepo check`) command that:

1. Scans all directories in the monorepo root for recognized project manifests (go.mod, pyproject.toml, package.json, Cargo.toml, etc.)
2. Compares found projects against entries in workspace.toml
3. Reports any directories with manifests that aren't registered
4. Exits non-zero if unregistered projects found (suitable for CI/pre-push hooks)

## Considerations

- Should ignore directories listed in .gitignore or a .rlsblignore
- Should handle nested directories (e.g., don't flag a go.mod inside a vendor/ directory)
- Could also detect registered projects whose directories no longer exist (stale entries)
- Depth limit: only scan first-level directories by default (monorepo convention)

## Affected files

- src/ (rlsbl CLI implementation)
- Likely a new subcommand under `monorepo`

## Effort

Small — directory scanning + set comparison + reporting.
