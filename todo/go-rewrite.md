# Rewrite rlsbl in Go

## Context

- rlsbl is currently pure Python (~5,080 LOC source across 28 files, ~5,400 LOC tests across 20 files), zero runtime dependencies
- Also published to npm via a Node.js wrapper (`bin/cli.js`) that shells out to `python3` -- the #1 distribution pain point
- Has a Python-based config migration system (`ConfigMigrator` in `lib/config_migrator.py`, `schema_loader` in `lib/schema_loader.py`) that dynamically loads `.py` migration files via `importlib.util` -- locks downstream projects to Python
- Consumer projects span multiple languages: JS, Python, Go
- The existing migration system works but has never been adopted on-disk (`.rlsbl/migrations/`) by any downstream project. Some consumers have inline imperative migrations in their own code, not using rlsbl's engine

## Why Go

Concrete improvements over Python, from an exhaustive analysis:

- **Distribution (HIGH)**: Single static binary eliminates Python runtime dependency for all users (npm, PyPI, Homebrew, direct download). The npm wrapper hack (`bin/cli.js` spawning `python3 -m rlsbl`) dies. No more "rlsbl requires Python 3.11+" error messages.
- **TOML read-write (MEDIUM)**: Python's `tomllib` is read-only (stdlib, no writer). rlsbl currently uses ~110 lines of fragile regex to edit `pyproject.toml`: 74 lines in `tagging.py` (`ensure_pypi_keyword`) for keyword injection, 38 lines in `targets/pypi.py` (`write_version`) for version bumping. Both use `re.search`/`re.sub` with section boundary detection, multi-line array handling, and indent preservation -- brittle against edge cases. Go's `go-toml/v2` handles round-trip TOML editing with formatting preservation natively.
- **Template embedding (LOW)**: Go's `embed.FS` compiles scaffold templates (currently in `rlsbl/templates/{shared,npm,pypi,go}/`) into the binary. No `os.path.dirname(__file__)` path resolution or package data manifests.
- **Cross-platform file locking (LOW)**: Current `lock.py` uses `fcntl.flock` which is Unix-only. Go has cross-platform alternatives (`golang.org/x/sys` or pure-Go flock).
- **Build-time version (LOW)**: `-ldflags -X main.version=...` at build time vs runtime probing with `tomllib`/`importlib.metadata` (current `__init__.py` tries `pyproject.toml` then `importlib.metadata` then falls back to "unknown").

What Python was better at (now moot):

- **Config migration engine**: Dynamic loading of `.py` migration scripts via `importlib.util.spec_from_file_location` had no Go equivalent. But with declarative JSON migrations (see below), this advantage disappears entirely.
- **Rapid iteration**: Go compiles ~5K-10K LOC in 1-2 seconds. Acceptable for a CLI tool.
- **Test mocking**: Go uses interfaces + dependency injection instead of monkeypatching. More boilerplate but not a blocker. Tests need rewriting regardless.
- **String manipulation**: Python's regex and string slicing are terser. Go's `strings`/`regexp` packages are more verbose but equivalent. Most string manipulation in rlsbl is for TOML editing, which Go replaces with a proper library.

## Declarative JSON Migration System

This is the centerpiece of the rewrite. Replaces the Python-only imperative migration engine with a language-agnostic declarative format. The existing `ConfigMigrator` class (239 LOC) and `schema_loader` module (200 LOC) are retired.

### Design decisions

**Migration file format**: One JSON file per release version, named by project semver: `.rlsbl/migrations/2.2.0.json`, `.rlsbl/migrations/2.3.1.json`. Not numbered sequences, not Python files.

**Development staging**: During development, migration files live in `.rlsbl/migrations/next/` with descriptive names (`add_lines.json`, `rename_field.json`). At release time (`rlsbl release`), all files in `next/` are combined into a single `<version>.json` and `next/` is emptied. This:

- Forces conflict resolution before release (merging into one file catches incompatible ops)
- Avoids integer sequence number merge conflicts between branches (the current `001_description.py` naming suffers from this)
- Decouples development from knowing the next version number

**Version tracking**: `_schema_version` in the config file, set to the project semver string of the highest applied migration. Engine applies all migrations where the version in the filename is greater than `_schema_version` (semver comparison). When `_schema_version` is absent, treat as `"0.0.0"` and apply all migrations. This replaces the current integer versioning (0, 1, 2, ...) with semver strings tied to actual releases.

**Pre-release versions**: Do NOT create migration directories for betas/RCs. Pre-release migrations stay in `next/` until the actual release.

**Accumulation**: Migration files are never removed. Package version N ships with all migration files from all prior versions. A user upgrading from v2.1 to v2.7 gets all intermediate migrations applied in order.

**Fresh installs**: Every migration must tolerate a config that never had the old shape (not just the immediately prior shape), since `set_default` on a non-existent key and `rename` on a non-existent key both need defined behavior. This is already the case conceptually but was not enforced by the Python engine.

**Config path**: Project-defined in `.rlsbl/config-schema.json` (same file as today, but simplified -- no `defaults_path` indirection needed since ops are self-contained).

**Ordering within a version**: Ops within a single migration file are ordered (array). Only one migration file per version (enforced by the single-file-per-release model), so no cross-file ordering ambiguity.

### Op vocabulary (initial: 6 ops)

| Op | Fields | Description | Behavior when path missing |
|----|--------|-------------|---------------------------|
| `set_default` | `path`, `value` | Add key with value if absent | Creates the key (and intermediate objects) |
| `set` | `path`, `value` | Unconditional overwrite | Creates the key (and intermediate objects) |
| `rename` | `from`, `to` | Rename a key (preserve value) | No-op if source missing |
| `delete` | `path` | Remove a key | No-op |
| `set_where` | `path`, `match`, `set` | On a list, find items matching `match` dict, set fields from `set` dict | No-op if list or matching item not found |
| `move` | `from`, `to` | Relocate a value from one path to another | No-op if source missing; create intermediate objects at destination |

**Path syntax**: JSON Pointer (RFC 6901) -- e.g., `/ui/color`, `/segments/0/key`. Well-specified, no ambiguity with dots in key names, libraries available in every language. The `~0` and `~1` escape sequences handle `/` and `~` in key names.

**Example migration file** (`.rlsbl/migrations/2.2.0.json`):

```json
{
  "description": "Add lines config for element visibility",
  "ops": [
    {
      "op": "set_default",
      "path": "/lines",
      "value": [
        ["context", "elapsed", "profile", "tier", "model", "version"],
        ["usage5h", "staleness", "age", "ghUser", "branch"],
        ["usageWeekly", "staleness", "age", "cwd"]
      ]
    }
  ]
}
```

**Example with set_where** (making a list item optional):

```json
{
  "description": "Make github segment optional",
  "ops": [
    {
      "op": "set_where",
      "path": "/segments",
      "match": {"key": "github"},
      "set": {"required": false}
    }
  ]
}
```

**Example with rename and move**:

```json
{
  "description": "Restructure color config",
  "ops": [
    {"op": "rename", "from": "/color_mode", "to": "/colorMode"},
    {"op": "move", "from": "/theme/background", "to": "/ui/background"},
    {"op": "delete", "path": "/deprecated_field"}
  ]
}
```

### Engine behavior

1. Read config file path from `.rlsbl/config-schema.json`
2. Read `_schema_version` from config (default `"0.0.0"` if absent)
3. Discover migration files in `.rlsbl/migrations/` matching `*.json` (excluding `next/` subdirectory)
4. Parse version from filename (strip `.json` suffix), sort by semver
5. Filter to versions > `_schema_version`
6. For each migration file in order:
   a. Parse ops array
   b. Apply each op sequentially to the in-memory config
7. Set `_schema_version` to the highest applied version
8. Write config atomically (tmp + rename) only if changed
9. All-or-nothing: if any op in any migration fails validation, write nothing and report the error

### Engine location

Single Go implementation inside the rlsbl binary. The migration engine is exposed via the `migrate` command family:

- `rlsbl migrate` -- run pending migrations
- `rlsbl migrate --dry-run` -- preview changes without writing (show each op and its effect)
- `rlsbl migrate --status` -- show current `_schema_version` and list pending migrations

Auto-migration integration points:

- `rlsbl scaffold` and `rlsbl scaffold --update` run migrations automatically after scaffolding (porting existing behavior from the Python `config migrate` subcommand)
- `rlsbl release` combines `next/*.json` into `<version>.json` before committing

Runtime auto-migration for downstream projects: each project can either:

1. Shell out to `rlsbl migrate --config-dir <path>` on first invocation (requires rlsbl binary installed)
2. Embed a minimal migration engine in its own language -- the op spec is simple enough for a ~200 LOC implementation in any language

A conformance test suite (JSON input/output pairs in a `testdata/migrations/` directory) ensures behavioral equivalence across implementations.

### `next/` merging at release time

When `rlsbl release` detects files in `.rlsbl/migrations/next/`:

1. Read all `*.json` files from `next/`, sorted alphabetically
2. Concatenate their `ops` arrays into a single ordered list
3. Concatenate descriptions with "; " separator (or use the first file's description if only one)
4. Write combined result as `.rlsbl/migrations/<new-version>.json`
5. Delete all files from `next/`
6. Include both the new migration file and the `next/` cleanup in the release commit

If `next/` is empty or absent, no migration file is created (not all releases need config changes).

### Known open questions

- **Comment preservation**: JSONC configs (used by some JS consumer projects) lose comments when read + written via standard JSON parsers. Options:
  - Use a JSONC-aware parser that preserves comments (exists in Go: `github.com/tidwall/jsonc` for reading, but writing with comments is harder)
  - Document that comments are stripped on migration and recommend moving config documentation elsewhere
  - Migrate config format to TOML (supports comments natively, Go has round-trip editing)
  - Accept the limitation: migrations are rare events, users can re-add comments

- **Multi-file configs**: Some projects split config across multiple files (e.g., separate files for segments, options, theme). The current Python `ConfigMigrator` operates across all files simultaneously (migrations receive a dict of all configs). The declarative engine operates on paths within a single file. Options:
  - Each migration file declares which config file it targets (add a `"file"` field)
  - Restrict to single-file configs (simpler, may require multi-file projects to consolidate)
  - Support a `"files"` map in `config-schema.json` and prefix paths with the file key

- **Op vocabulary expansion**: Future ops may include:
  - `append`: add value to end of array
  - `remove_where`: remove list items matching a condition (inverse of `set_where`)
  - `transform`: conditional value change (e.g., "if value is X, change to Y")
  - `merge_defaults`: deep-merge a defaults object (replaces the current `deep_merge_missing` strategy)

  Add as needed -- the initial 6 ops cover all real-world migrations today.

## Migration of downstream projects

After the Go rewrite ships, downstream projects need to:

1. Set up `.rlsbl/config-schema.json` declaring config file path(s)
2. Write declarative migrations for any schema changes (converting existing imperative migrations to JSON ops)
3. Include `.rlsbl/migrations/` in their published packages
4. Call `rlsbl migrate` on startup or embed a minimal migration engine in their own language (~150-200 LOC)

## Rewrite plan

The rewrite is a full replacement, not incremental porting. The Go binary replaces both the Python package and the npm wrapper.

### Modules to port (in dependency order)

| Priority | Module | Python source | Go target | Notes |
|----------|--------|---------------|-----------|-------|
| 1 | Version/utils | `utils.py` (137 LOC) | `internal/utils/` | Git helpers, version parsing, semver bumping, changelog extraction |
| 2 | File locking | `lock.py` (61 LOC) | `internal/lock/` | Now cross-platform (no `fcntl`) |
| 3 | Project config | `config.py` (57 LOC) | `internal/config/` | `.rlsbl/config.json`, user config reading |
| 4 | Registry detection | `registries/` (444 LOC) | `internal/registry/` | npm, pypi, go detection and version read/write |
| 5 | Release targets | `targets/` (514 LOC) | `internal/target/` | npm, pypi, go, docs target implementations; TOML editing improves here |
| 6 | Tagging | `tagging.py` (207 LOC) | `internal/tagging/` | Keyword injection; pyproject.toml editing uses `go-toml/v2` instead of regex |
| 7 | Scaffold engine | `commands/init_cmd.py` (599 LOC) | `internal/scaffold/` | Template rendering with `embed.FS`; three-way merge for `--update` |
| 8 | **Migration engine** | **new** | `internal/migrate/` | Declarative JSON migration engine (new, ~500-800 LOC estimated) |
| 9 | Release flow | `commands/release.py` (504 LOC) | `internal/release/` | Core release orchestration; includes `next/` merging |
| 10 | Watch | `commands/watch.py` (243 LOC) | `internal/watch/` | CI monitoring via GitHub API |
| 11 | Smaller commands | Various (~750 LOC total) | `internal/cmd/` | `check`, `discover`, `undo`, `status`, `unreleased`, `prs`, `pre_push_check`, `record_gif` |
| 12 | CLI entry point | `__init__.py` (296 LOC), `__main__.py` (4 LOC) | `cmd/rlsbl/main.go` | Argument parsing with `cobra` or `kong` |

### Key dependencies (Go modules)

| Dependency | Purpose | Replaces |
|------------|---------|----------|
| `github.com/pelletier/go-toml/v2` | Round-trip TOML editing | `tomllib` + regex hacks |
| `github.com/spf13/cobra` | CLI framework | Manual `argparse`-style parsing in `__init__.py` |
| `github.com/Masterminds/semver/v3` | Semver parsing and comparison | Custom string splitting in `utils.py` |
| `golang.org/x/sys` (optional) | Cross-platform file locking | `fcntl` |

### Distribution channels

| Channel | Mechanism | Replaces |
|---------|-----------|----------|
| GitHub Releases | `goreleaser` cross-platform binaries (linux/darwin/windows, amd64/arm64) | Python sdist/wheel |
| Homebrew | Tap with goreleaser-generated formula | N/A (not available today) |
| npm | Platform-specific optional dependencies pattern (like esbuild: `@rlsbl/linux-x64`, etc.) or single package with postinstall download | Node.js wrapper shelling out to `python3` |
| PyPI | Platform wheels with embedded binary (like ruff: `rlsbl-linux-x86_64`, etc.) | Python package requiring Python runtime |
| Direct download | Curl-pipe-bash installer or manual download from releases | `pip install rlsbl` / `npm install -g rlsbl` |

The npm and PyPI packages become thin wrappers around the Go binary rather than requiring a language runtime.

### Testing strategy

- Port all ~5,400 LOC of Python tests to Go table-driven tests
- Add conformance test suite for the migration engine: JSON files with input config, migration ops, and expected output config -- usable by any language implementation
- Integration tests: same smoke test pattern (run binary with `--version`, `--help`, `--test-colors`-equivalent)
- CI matrix: test on linux/darwin/windows (currently only linux)

## Effort estimate

High. ~5,080 LOC source + ~5,400 LOC tests to port, plus the new declarative migration engine (~500-800 LOC) and conformance test suite. Go code will likely be ~30-40% longer due to explicit error handling and interface boilerplate. Estimated 7K-10K LOC Go source, 7K-9K LOC Go tests.

Major work items:

1. **Core library** (modules 1-6): port existing logic, improve TOML handling -- ~3K LOC
2. **Scaffold engine** (module 7): port templates to `embed.FS` -- ~800 LOC
3. **Migration engine** (module 8): new declarative engine + conformance tests -- ~800 LOC + ~500 LOC tests
4. **Release flow + commands** (modules 9-12): port orchestration and smaller commands -- ~2.5K LOC
5. **CLI + distribution** (goreleaser, npm/PyPI wrappers): ~500 LOC + configuration
6. **Test porting**: ~8K LOC
7. **Downstream project adoption**: update config schemas and migration files -- separate effort per project

This supersedes `todo/.done/config-management.md` which designed the Python-based migration system that already exists in `lib/config_migrator.py` and `lib/schema_loader.py`.
