# rlsbl doctor: diagnose and repair release state

Status: Proposed
Priority: High

## Context

When `rlsbl release` is interrupted midway (Ctrl+C, terminal close, network timeout), it can leave the project in a partially released state. The release flow has 9+ sequential steps (version write, commit, tag, push, GitHub Release, etc.), and interruption at any point leaves different artifacts behind. There is no automated way to diagnose or recover from this.

### Incident that motivated this

A `rlsbl release` on the migrable project was interrupted by the user after the command had already completed (the user didn't realize it had finished). This left:
- A `.rlsbl/lock` file on disk (untracked, not gitignored)
- `rlsbl release` refused to run again because the lock file dirtied the working tree
- `rlsbl undo` also refused (same dirty tree check)
- Manual investigation was needed: check git log, check remote tags with `git ls-remote`, check GitHub Releases with `gh release view`, remove the lock file by hand

The fix was trivial (rm the lock file) but diagnosing that it was safe to do so required understanding rlsbl's internals.

## Proposal

Add `rlsbl doctor` that checks consistency across all state rlsbl manages and optionally repairs issues.

### Checks

1. **Stale lock file**: Does `.rlsbl/lock` exist? Try acquiring `LOCK_EX | LOCK_NB` on it -- if it succeeds, no process holds the lock and the file is stale. Safe to remove.

2. **Version consistency**: Does the version in the primary project file (pyproject.toml, package.json, VERSION, etc.) match across all detected targets? Flag mismatches.

3. **Tag consistency**: Does a local tag exist for the current version? Does the remote have it? Flag: local-only tag (push failed), remote-only tag (local was deleted), or no tag (release didn't get that far).

4. **GitHub Release consistency**: Does a GitHub Release exist for the latest tag? Flag: tag pushed but no release (release creation failed mid-flight).

5. **Commit/push consistency**: Is the local branch ahead of or behind origin? If ahead, are the unpushed commits release-related (commit message equals tag string)?

6. **Changelog coverage**: Does CHANGELOG.md have an entry for the current version? (Already checked by `rlsbl status`, but doctor should include it for completeness.)

7. **Lock file in .gitignore**: Is `.rlsbl/lock` gitignored? If not, warn that stale locks will dirty the working tree.

### Output

For each check: PASS, WARN, or FAIL with a description. At the end, a summary of recommended actions.

```
$ rlsbl doctor
Lock file:        WARN -- stale .rlsbl/lock (no process holds it)
Version files:    PASS -- 0.1.1 across all targets
Local tag:        PASS -- v0.1.1 exists
Remote tag:       PASS -- v0.1.1 on origin
GitHub Release:   PASS -- v0.1.1 exists
Branch sync:      PASS -- up to date with origin/main
Changelog:        PASS -- entry for 0.1.1

1 issue found:
  [WARN] Stale lock file at .rlsbl/lock. Run `rlsbl doctor --fix` to remove.
```

### Auto-repair (`--fix`)

- Remove stale lock files (after verifying no process holds it)
- Push unpushed tags (`git push origin <tag>`)
- Create missing GitHub Release from changelog (`gh release create <tag>`)

Actions that are destructive or ambiguous (removing local-only tags, reverting commits) should NOT be auto-fixed -- just reported with guidance.

## Related improvements

### Gitignore the lock file

Add `.rlsbl/lock` to the gitignore template (`rlsbl/templates/shared/gitignore.tpl`). This prevents stale locks from dirtying the working tree, which is the proximate cause of the "working tree is not clean" error that blocks recovery.

### Signal handling for lock cleanup

Register an `atexit` handler or signal handler in `lock.py` to remove the lock file on abnormal termination. The kernel already releases the `fcntl.flock` advisory lock when the process dies, but the file remains on disk. An `atexit` handler would clean up the file in most termination scenarios (except SIGKILL).

## Affected files

| File | Change |
|------|--------|
| `rlsbl/commands/doctor.py` | New command implementation |
| `rlsbl/cli.py` | Register doctor subcommand |
| `rlsbl/lock.py` | Add stale lock detection helper, add atexit handler |
| `rlsbl/templates/shared/gitignore.tpl` | Add `.rlsbl/lock` |
| `tests/test_doctor.py` | Tests for each check |

## Effort estimate

~1-2 sessions. The checks are mostly subprocess calls (git, gh) and file reads. The lock staleness check is the most nuanced (fcntl probe). Auto-repair is straightforward for the safe cases.
