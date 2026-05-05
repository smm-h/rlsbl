# rlsbl centralized config management and migration system

## Context

All projects under `~/Projects` use [rlsbl](https://github.com/smm-h/rlsbl) for releases, CI scaffolding, and changelog enforcement. Many of these projects have JSON config files that evolve over time: new keys get added, defaults change, and new sections appear as the project matures.

Currently each project implements its own config migration logic. claudewheel implemented a local solution in `config.py` during this session:

- `_migrate()` for adding missing keys from `DEFAULT_*` dicts
- `_deep_merge_missing()` for recursive dict merging (handles nested structures like theme sections)
- `_run_versioned_migrations()` with a `_MIGRATIONS` registry keyed by `_schema_version` in `config.json`
- Mutation detection via JSON snapshot comparison (only writes if something actually changed)

The implementation is solid, but it's project-specific: it references hardcoded file paths, project-specific default dicts, and claudewheel-only migrations.

## Problem

Config migration is a cross-cutting concern. Every project with config files needs:

- Key merging (add missing defaults without overwriting user values)
- Deep merge (recursive, for nested dicts and sections)
- Schema version tracking (know which migrations have already run)
- A migration registry (ordered list of one-time transformations)

Without centralization:

- Each project reinvents these patterns independently
- Different projects implement them differently, making maintenance harder across the portfolio
- Bugs fixed in one project's migration logic don't propagate to others
- New projects have to copy-paste and adapt rather than import a tested solution

## Proposed solution: `rlsbl config` subcommand family

Extend rlsbl with a `config` subcommand that handles config file migration as a first-class concern:

- `rlsbl config init` -- scaffold a config schema: creates a version field in the config file, sets up a migration directory
- `rlsbl config migrate` -- run pending migrations on project config files
- Auto-detect config files from project structure (the same way rlsbl auto-detects registries from `package.json`, `pyproject.toml`, `go.mod`)
- Standard migration format: numbered files in `.rlsbl/migrations/` or a declarative migrations registry
- Two migration types:
  - **Key-merge**: add missing defaults from a reference dict, recursive deep merge for nested structures
  - **Versioned**: one-time value changes keyed by schema version (rename a key, change a default, restructure a section)
- Standard `_schema_version` field management: starts at 0, incremented by each versioned migration

## Alternative: library approach

Instead of a CLI subcommand, provide a Python module that projects import and call at app startup:

- `from rlsbl.config import ConfigMigrator` or similar
- Projects instantiate with their defaults and migration list, then call `migrator.run(config_path)`
- Migrations run every time the app starts, so stale user configs are fixed immediately

## Pros and cons

### CLI approach

| Aspect | Assessment |
|--------|------------|
| Runtime dependency | None -- rlsbl remains a dev/release tool only |
| Consistency | Fits rlsbl's existing role as a project management tool |
| Cross-language | Works for Python, JS, and Go projects alike |
| Timing | Migrations run at release/CI time or manually, not at app startup -- stale user configs aren't fixed until the user runs `rlsbl config migrate` |
| Discovery | Can auto-detect config files the same way rlsbl detects registries |

### Library approach

| Aspect | Assessment |
|--------|------------|
| Startup migration | Fixes stale configs automatically when the app runs |
| Flexibility | Can inspect app state during migration (e.g. check environment, prompt user) |
| Runtime dependency | rlsbl becomes a runtime dependency, not just a dev tool |
| Language scope | Only works for Python projects -- rlsbl also supports JS and Go |
| Coupling | Tighter coupling between app lifecycle and release tooling |

### Hybrid approach

Provide both:

- A Python library for Python projects that want startup migration (`from rlsbl.config import ConfigMigrator`)
- A CLI for everything else and for projects that prefer explicit migration

The library is optional. Projects that don't need startup migration use the CLI. The core migration logic (deep merge, version tracking, migration registry) is shared between both surfaces.

## Reference implementation

claudewheel's `config.py` serves as the reference:

- **`_migrate()`**: entry point, calls key-merge then versioned migrations
- **`_deep_merge_missing(target, source)`**: recursive dict merge, adds missing keys from source without overwriting existing values, handles nested dicts
- **`_run_versioned_migrations(config, segments_def, theme)`**: iterates `_MIGRATIONS` list, skips already-applied versions, calls each migration's `apply` function, bumps `_schema_version`
- **`_MIGRATIONS`**: list of `{version, description, apply}` dicts where `apply` receives the config objects and mutates them in place
- **Schema version field**: `"_schema_version"` in `config.json`, integer starting at 0
- **Mutation detection**: JSON snapshot before and after migration, only writes to disk if content changed

The generalization challenge: claudewheel's implementation hardcodes which files to migrate (`config.json`, `segments.json`, `theme.json`) and which default dicts to merge from. A general solution needs a project-agnostic way to declare config files, their defaults, and their migration registries.

## Files/dirs that would change in rlsbl

- `rlsbl/commands/config.py` -- new subcommand module (`init`, `migrate`, `status`)
- `.rlsbl/migrations/` -- per-project migration directory (scaffolded by `config init`)
- `.rlsbl/config-schema.json` or similar -- declares which config files exist, where defaults live, schema version field name
- Optional `rlsbl/lib/config_migrator.py` -- shared migration engine, importable as a library for Python projects
- `rlsbl/templates/` -- scaffolding templates for config migration setup
- Documentation updates

## Relative effort

Medium-high. The core migration logic exists in claudewheel and can be extracted and generalized. The main work is:

- Designing the project-agnostic interface: how projects declare their config files, default values, and migrations
- Supporting multiple project types (Python, JS, Go) for the CLI path
- Deciding the migration file format (Python callables vs. declarative JSON patches vs. both)
- Testing across different project structures
- Optionally building the library surface alongside the CLI

The claudewheel implementation covers roughly 40% of the work (the core algorithms). The remaining 60% is the abstraction layer and multi-project support.
