# Monorepo changelog-only commit exemption broken

## Context

The `_is_changelog_only_commit` function in `rlsbl/changelog/validate.py` checks if a commit only touches changelog-maintenance files. If all files match `_CHANGELOG_PATTERNS`, the commit is exempted from coverage requirements. This prevents the bootstrap problem where a changelog commit can't cover itself.

## Problem

`_CHANGELOG_PATTERNS` contains `.rlsbl/changes/` as a prefix pattern. In a monorepo, sub-project changelog files live at paths like `python/.rlsbl/changes/unreleased.jsonl`, which does NOT match the `.rlsbl/changes/` prefix. The exemption silently fails, and every changelog commit in a monorepo sub-project requires a coverage entry, creating an infinite bootstrap loop.

## Reproduction

1. Set up a monorepo with `.rlsbl-monorepo/workspace.toml` listing sub-projects
2. In a sub-project (e.g., `python/`), create `.rlsbl/changes/unreleased.jsonl`
3. Add changelog entries with `rlsbl changelog add` (auto-commit enabled)
4. Run `rlsbl changelog validate` -- the auto-commit touching `python/.rlsbl/changes/unreleased.jsonl` is flagged as uncovered
5. Adding coverage for that commit creates another commit, which is also uncovered, ad infinitum

## Solution

Update `_CHANGELOG_PATTERNS` matching in `_is_changelog_only_commit` to handle monorepo sub-project paths. Two approaches:

### Option A: Path suffix matching

Instead of checking if the path starts with `.rlsbl/changes/`, check if the path contains `/.rlsbl/changes/` or starts with `.rlsbl/changes/`. Similarly for `CHANGELOG.md`, match paths ending with `/CHANGELOG.md`.

### Option B: Monorepo-aware patterns

Detect if running inside a monorepo sub-project (check for `../.rlsbl-monorepo/workspace.toml`), read the workspace config, and dynamically build patterns with the sub-project prefix (e.g., `python/.rlsbl/changes/`).

Option A is simpler and more robust. The patterns could be:
- Any path containing `.rlsbl/changes/` (either at start or after a directory prefix)
- Any path equal to `CHANGELOG.md` or ending with `/CHANGELOG.md`
- Any path containing `.rlsbl/version` (either at start or after a directory prefix)

## Affected files

- `rlsbl/changelog/validate.py` (lines 82-86, 115-119)
- `tests/test_changelog_validate.py` (test_changelog_only_files)

## Effort estimate

Small -- ~10 lines of code change plus test updates.
