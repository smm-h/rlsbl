# Require JSONL changelog for all rlsbl-managed projects

## Problem

`rlsbl release` currently treats JSONL changelogs as opt-in: if `.rlsbl/changes/` exists, it uses JSONL mode with validation; if not, it falls back to requiring a manual `## x.y.z` heading in CHANGELOG.md. This means projects without `.rlsbl/changes/` can release with hand-written changelogs and no commit coverage validation.

This silent fallback is a problem:
- Projects miss the commit coverage guarantee (every commit accounted for)
- `rlsbl scaffold` creates the directory for new projects, but existing projects that haven't run `scaffold --update` never get it
- There's no error or even warning telling the user they're on the legacy path

## Expected behavior

`rlsbl release` should error if `.rlsbl/changes/` does not exist, with a message like:

> Error: JSONL changelog not set up. Run `rlsbl scaffold --update` to create `.rlsbl/changes/`, then backfill existing versions.

This makes JSONL the required mode, not opt-in. Projects that haven't migrated are forced to set it up before their next release.

## Migration path

For existing projects without `.rlsbl/changes/`:
1. `rlsbl scaffold --update` creates the directory and empty `unreleased.jsonl`
2. Existing CHANGELOG.md versions need backfilling into `.jsonl` files (the `scripts/backfill_changelog.py` in rlsbl itself is a reference)
3. Once backfilled, `rlsbl changelog generate` produces CHANGELOG.md from JSONL sources

## Affected files

- `rlsbl/commands/release.py` — where `uses_jsonl` flag is checked; should error instead of falling back
- `rlsbl/commands/pre_push_check.py` — should also warn/error if changes dir is missing

## Effort

Small. Change the `uses_jsonl` conditional from a fallback to an error.
