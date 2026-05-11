# Scaffold should untrack files it adds to .gitignore

## Context

When `rlsbl scaffold` adds entries to `.gitignore` (e.g., `.rlsbl/lock`), it doesn't check whether those files are already tracked. Adding a file to `.gitignore` only prevents new untracked files from being staged — it has no effect on files already in the index.

Discovered in claudewheel: `.rlsbl/lock` was tracked in the repo (likely committed by an older rlsbl version or a manual commit). Running `scaffold --update` added `.rlsbl/lock` to `.gitignore` but the file remained tracked, causing a persistent `deleted: .rlsbl/lock` in `git status` after every release (since the lock is cleaned up on release).

## Problem

After scaffold adds entries to `.gitignore`, any of those entries that are already tracked remain tracked. The `.gitignore` entry is effectively a no-op for those files.

## Solution

In `_finalize_scaffold()`, after writing the `.gitignore`, check if any of the newly added gitignore entries are currently tracked. If so, run `git rm --cached` on them before the scaffold commit. This is safe — the files are being gitignored precisely because they shouldn't be tracked.

## Affected files

| File | Change |
|------|--------|
| `rlsbl/commands/init_cmd.py` | After writing `.gitignore`, untrack any newly-gitignored files that are in the index |

## Effort

Small. A few lines of code: parse the gitignore entries being added, check `git ls-files --cached` against them, run `git rm --cached` on matches.
