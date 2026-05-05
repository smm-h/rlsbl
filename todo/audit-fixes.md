# Audit fixes and improvements

Findings from two independent audits (correctness + security) on v0.7.0, filtered to items still needing attention as of v0.8.2.

## Quick wins (effort 5 each)

### Auto-commit after scaffold
`rlsbl/commands/init_cmd.py` — scaffold leaves modified/untracked files that the user must manually commit. Consider auto-committing when scaffold completes without conflicts. On conflict-free runs: stage all scaffold-touched files and commit with a message like `"rlsbl scaffold v{version}"`. On runs WITH conflicts: still auto-commit — git allows committing files with conflict markers, and having them tracked is better than leaving them untracked. The user resolves conflicts and commits again. The key question is whether to use safegit or git (detect via `find_commit_tool`). Could also add `--no-commit` flag to opt out.

### Tagging not mentioned in release confirmation
`rlsbl/commands/release.py` — the confirmation prompt shows files but doesn't explain that ecosystem tagging will add the `"rlsbl"` keyword to manifests. Fix: include "Will add 'rlsbl' keyword" in the prompt when tagging is enabled.

### record-gif non-integer flag gives raw error
`rlsbl/commands/record_gif.py` — `--width abc` produces `ValueError: invalid literal for int()` without indicating which flag failed. Fix: wrap `int()` calls in try/except with a clear message.

### Rename test_tagging.py
`tests/test_tagging.py` — tests 3 different modules (config, tagging, discover) under a misleading filename. Fix: split into `test_config.py`, `test_tagging.py`, `test_discover.py` or at minimum rename.

### Discover no page-count cap
`rlsbl/commands/discover.py` — `MAX_RESULTS` limits total items but not page count. A server returning 1 item per page could cause 1000 API calls. Fix: add `MAX_PAGES = 20` guard.

## Small fixes (effort 10-15 each)

### `undo` should push the revert
`rlsbl/commands/undo.py` — deletes remote tag and GitHub Release but doesn't push the revert commit, leaving the remote in an inconsistent state. Fix: auto-push with confirmation, or at minimum warn more prominently.

### `undo` partial failure summary
`rlsbl/commands/undo.py` — each step (delete release, delete tags, revert commit) warns independently on failure. No structured summary of what succeeded vs. failed. Fix: collect results, print a table at the end with manual remediation steps.

### CalledProcessError exposes stderr
`rlsbl/__init__.py` — the top-level `except Exception as e: print(f"Error: {e}")` prints the full CalledProcessError string including stderr, which could contain partial token info. Fix: catch CalledProcessError specifically and print only `e.stderr`.

### Race between clean-tree check and release operations
`rlsbl/commands/release.py` — clean-tree check at the start, then confirmation prompt + pre-release hook, then commit. Another process could dirty the tree in between. Fix: re-check `is_clean_tree()` immediately before committing.

### `pre_push_check` run_cmd not tested
`tests/test_commands.py` — only `_detect_version` is tested, not the full `run_cmd` that checks changelog entries and prints errors. Fix: add tests for the full flow with mocked filesystem.

### No PyPI/Go availability check tests
`tests/test_commands.py` — only npm check is tested. PyPI uses urllib, Go uses urllib — different mock strategy needed. Fix: mock `urllib.request.urlopen` for both.

### No happy-path undo test
`tests/test_commands.py` — only error paths (no tags, dirty tree) are tested. Fix: mock all subprocess calls and verify the full undo flow succeeds.

### Discover no rate-limit retry
`rlsbl/commands/discover.py` — on 403 prints a hint about auth but doesn't retry or respect `Retry-After` header. Fix: parse header and wait, or at minimum retry once after auth hint.

## Medium effort (effort 20-35 each)

### `run_cmd_multi` in scaffold untested
`tests/test_commands.py` — the dual-registry scaffold path (both package.json and pyproject.toml present) has no test coverage. Fix: set up temp dir with both files, call `run_cmd_multi`, verify merged workflow is generated.

### `bump_version` no pre-release support
`rlsbl/utils.py` — versions like `1.0.0-beta.1` fail with "Invalid semver version". Fix: parse pre-release suffix, strip before bumping, optionally re-attach or drop on release.

### `check` sequential variant checking
`rlsbl/commands/check.py` — each npm variant checked via separate `npm view` subprocess call (1-2s each, 4-5 variants = 5-10s). Fix: use `concurrent.futures.ThreadPoolExecutor` for parallel checking.

### Concurrent release/scaffold no lockfile
`rlsbl/commands/release.py`, `rlsbl/commands/init_cmd.py` — two simultaneous invocations can race on version files, tags, and hashes.json. Fix: advisory file lock via `fcntl.flock` on `.rlsbl/lock`.

### `watch` sequential run watching
`rlsbl/commands/watch.py` — watches CI runs one at a time via `gh run watch`. If 3 runs are active, the user doesn't see run 2's result until run 1 finishes. Fix: parallel watching with `concurrent.futures` or async polling.
