# Python improvements

Decided changes to rlsbl now that the migration engine lives in migrable (separate Go project).

## Replace TOML regex with tomlkit

`tagging.py` (74 LOC) and `targets/pypi.py` (38 LOC) use regex to edit `pyproject.toml` -- section boundary detection, multi-line array handling, indent preservation. Fragile against edge cases.

Replace with `tomlkit` (python-poetry, 280M downloads/month, MIT, zero runtime deps, preserves comments/formatting on round-trip).

### Files to change

- `rlsbl/tagging.py`: `ensure_pypi_keyword()` regex -> tomlkit read/modify/write
- `rlsbl/targets/pypi.py`: `write_version()` regex -> tomlkit read/modify/write
- `pyproject.toml`: add `tomlkit` to `[project.dependencies]`

### Notes

- This adds rlsbl's first runtime dependency. README claim "Pure Python, no dependencies" must be updated.
- tomlkit is pure Python with zero transitive deps. No C extensions.

## Remove config subcommand tree

The `rlsbl config` subcommand tree (`show`, `init`, `migrate`, `status`) is superseded:

- `config migrate` / `config status` / `config init` -> migrable handles this
- `config show` -> absorb into `rlsbl status`

### Files to change

- `rlsbl/commands/config.py`: delete entirely
- `rlsbl/__init__.py`: remove `config` from COMMANDS, update HELP string, add `migrate` command
- `rlsbl/commands/status.py`: add registry detection, hooks, scaffold state (from config show)

## Remove ConfigMigrator and schema_loader

Dead code once migrable exists. ~440 LOC total.

### Files to delete

- `rlsbl/lib/config_migrator.py` (239 LOC)
- `rlsbl/lib/schema_loader.py` (200 LOC)
- `tests/test_config_migrator.py`
- `tests/test_schema_loader.py`

## Add `rlsbl migrate` command

Shells out to `migrable migrate`. Optional dependency -- if migrable is not installed, show a clear error with install instructions.

### Behavior

- `rlsbl migrate` -> `migrable migrate --config-dir .rlsbl`
- `rlsbl migrate --dry-run` -> `migrable migrate --dry-run --config-dir .rlsbl`
- `rlsbl migrate --status` -> `migrable migrate --status --config-dir .rlsbl`
- `rlsbl release` calls `migrable merge <version>` if `migrations/next/` has files

## Nice-to-haves

- Document hidden flags in HELP string: `--quiet` (release), `--no-commit` (scaffold), `--skip-shared` (scaffold)
- Add `--json` flag to `status` for structured output
