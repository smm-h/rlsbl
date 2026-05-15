# JSONL changelog migration friction

## Context

Migrating 11 projects from manual CHANGELOG.md to JSONL revealed several friction points in the tooling. Each is small individually but compounds across multiple projects.

## 1. Status and validate disagree on coverage

`rlsbl changelog validate` passes (changelog-only commits are auto-exempted from the coverage check), but `rlsbl status` reports "11/12 commits covered" without noting the exemption. A user seeing that thinks something is wrong. Status should apply the same exemptions as validate, or at least annotate exempted commits.

## 2. changelog add creates uncovered auto-commits

`rlsbl changelog add` auto-commits `unreleased.jsonl`, but that auto-commit itself is uncovered by any entry. The validation exempts it (changelog-only), but status reports it as uncovered (see item 1). Options:

- Fix via item 1 (status applies exemptions — simplest, solves the visible problem)
- changelog add could amend its own auto-commit to include the entry's hash — but amending is destructive and the hash isn't known pre-commit
- changelog add could do a two-phase commit (write entry, commit, get hash, append self-referencing entry, amend) — fragile and violates safegit conventions
- Accept the bootstrap gap and ensure tooling never reports it as a problem

## 3. Scaffold --update produces predictable merge conflicts

Every `scaffold --update` creates merge conflicts in `.gitignore`, `pre-release.sh`, and CI workflows. For batch migrations this means N rounds of identical conflict resolution. Options:

- `.gitignore`: use additive merging (append new entries, never remove existing ones) instead of three-way merge. Gitignore entries are inherently additive.
- Hooks: use `# USER START` / `# USER END` markers to fence user customizations. The scaffold replaces everything outside the markers, preserves everything inside.
- CI workflows: harder since structure matters. Consider a "user overrides" section or a separate user-owned workflow file.

## 4. Backfill script is not portable

`scripts/backfill_changelog.py` hardcodes its project root to `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`, which resolves to rlsbl's own root. Running it on another project writes to rlsbl's `.rlsbl/changes/`, not the target's. The workaround is calling the `backfill()` function directly with the correct path. Options:

- Move to `~/Projects/rlsbl-backfill.py` as a standalone script that uses CWD
- Fix the script to use CWD instead of `__file__`-relative paths
- Add a `--project-root` flag

## Affected files

- `rlsbl/commands/status.py` — coverage display (item 1)
- `rlsbl/commands/changelog_cmd.py` — add subcommand auto-commit (item 2)
- `rlsbl/commands/init_cmd.py` — scaffold merge strategy (item 3)
- `scripts/backfill_changelog.py` — project root resolution (item 4)

## Effort

Small to medium per item. Items 1 and 4 are quick fixes. Item 2 is a design decision. Item 3 is medium (new merge strategy).
