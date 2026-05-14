# Bug: scaffold walks to monorepo root instead of sub-project

## Problem

When `rlsbl scaffold` runs inside a monorepo sub-project (e.g., `go/`), `find_project_root()` walks up and finds `.rlsbl-monorepo/` at the repo root, then `os.chdir(root)` moves to the repo root. This causes scaffold to write files (CLAUDE.md, LICENSE, CHANGELOG.md, VERSION, `.rlsbl/`, `.claude/`) in the repo root instead of the sub-project directory. Target auto-detection also fails because manifest files (go.mod, pyproject.toml) are in the sub-project, not the root.

## Reproduction

```bash
cd /path/to/monorepo/go/   # sub-project with go.mod
rlsbl scaffold              # writes files to monorepo root, not go/
```

## Affected flows

- `rlsbl monorepo add` auto-scaffolding (runs scaffold as a subprocess)
- Manual `rlsbl scaffold` from sub-project directories

## Workaround

Pre-create `.rlsbl/config.json` in the sub-project before scaffolding, so `find_project_root()` stops at the sub-project instead of walking up to the monorepo root.

## Expected fix

`find_project_root()` should prefer `.rlsbl/` in the current directory or nearest ancestor over `.rlsbl-monorepo/` at the repo root. Or scaffold should respect the monorepo context and know which sub-project it's operating on.

## Affected files

- `rlsbl/scaffold.py` or wherever `find_project_root()` is defined
- Discovered during strictcli monorepo setup (2026-05-14)
