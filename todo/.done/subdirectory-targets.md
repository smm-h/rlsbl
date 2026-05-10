# Per-target subdirectory paths

Status: Proposed
Priority: High

## Context

Projects that ship wrapper packages alongside the main artifact (e.g., a Go binary with npm and PyPI wrappers in subdirectories) need rlsbl to manage version files in multiple directories during a single release.

Current limitation: all targets share the same `version_dir` (project root or monorepo sub-project path). The version sync loop, build/publish, and detection all hardcode this single directory. If `package.json` lives in `npm/` and `pyproject.toml` lives in `pypi/`, rlsbl can't find or update them.

### Real-world case (migrable)

```
migrable/
  VERSION              # Go target (root)
  npm/package.json     # npm wrapper
  pypi/pyproject.toml  # PyPI wrapper
```

One release should bump all three version files and publish to Go module proxy, npm, and PyPI.

## Proposal

### Config format

Extend `"targets"` to accept structured entries with an optional `path` field:

```json
{
  "targets": [
    "go",
    {"name": "npm", "path": "npm/"},
    {"name": "pypi", "path": "pypi/"}
  ]
}
```

Plain strings remain valid (default to project root). The `"release_targets"` list should support the same format.

### Code changes

~5 call sites in `release.py` that pass `version_dir` need to resolve a per-target directory instead:

1. **`detect_targets()`** in `targets/__init__.py` — check configured subdirectories, not just root
2. **Version sync loop** (release.py ~lines 328-370) — pass per-target `dir_path`
3. **Build/publish loop** (release.py ~lines 520-534) — pass per-target `dir_path`
4. **Ecosystem tagging** (release.py ~lines 373-389) — use per-target path
5. **Config validation** — verify configured paths exist

### What this does NOT cover

- Monorepo independent projects (already handled by workspace.toml)
- Different versions per subdirectory (all share one version in this model)
- Scaffold support for subdirectory targets (future work)

## Affected files

| File | Change |
|------|--------|
| `rlsbl/targets/__init__.py` | Parse structured target entries, resolve per-target paths |
| `rlsbl/commands/release.py` | Pass per-target `dir_path` to all target method calls |
| `rlsbl/commands/status.py` | Show per-target paths in status output |
| `tests/test_release.py` | Tests for subdirectory target version sync and publish |

## Effort estimate

~1 session. The structural change is small (config parsing + 5 call sites). Most work is testing the combinations.
