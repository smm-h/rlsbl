# Release failure recovery: undo and rollback

## Problems

### 1. `rlsbl release` doesn't rollback on push failure

When the push step (step 10) fails, the release flow has already:
- Bumped the version in pyproject.toml and committed (`v0.1.1`)
- Tagged the commit (`v0.1.1`)
- Finalized the JSONL changelog (renamed `unreleased.jsonl` to `0.1.1.jsonl`, created fresh `unreleased.jsonl`, regenerated CHANGELOG.md, committed)

All of this local state is left dirty with no cleanup. The user must manually undo version bumps, delete tags, restore changelog files, and re-populate `unreleased.jsonl`. This is error-prone and took significant manual effort to recover from.

### 2. `rlsbl undo` can't handle the finalize commit

After a full release flow (even a failed one), HEAD is the finalize commit (`chore: finalize changelog for 0.1.1`), not the version bump commit (`v0.1.1`). `rlsbl undo` checks `HEAD` against the expected version bump message and skips the revert with "HEAD does not match expected." It should handle both commits -- the finalize commit AND the version bump commit.

## Solutions

### For problem 1
If the push fails, `rlsbl release` should automatically rollback:
- Delete the local tag
- Revert the finalize commit
- Revert the version bump commit
- Restore `unreleased.jsonl` from the version-specific JSONL file
- Delete the version-specific JSONL and MD files
- Report what happened and suggest re-running after fixing the push issue

### For problem 2
`rlsbl undo` should detect and revert BOTH the finalize commit and the version bump commit, not just the version bump. It should walk back from HEAD, identifying release-related commits by their message patterns (`chore: finalize changelog for X.Y.Z` and `vX.Y.Z`).

## Reproduction

Trigger: a pre-push hook that fails (e.g., the `$@` bug in `fix-pre-push-hook-args.md`) causes `rlsbl release` to succeed through step 11 but fail at step 10's push. `rlsbl undo --yes` then fails to clean up.

## Affected files
- `rlsbl/commands/release.py` (add rollback on push failure)
- `rlsbl/commands/undo.py` (handle finalize commit)

## Effort
Medium -- rollback logic needs to reverse multiple steps atomically, and undo needs to walk multiple commits.
