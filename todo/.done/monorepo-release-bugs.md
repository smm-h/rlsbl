# Monorepo release bugs

Found during a release attempt in the strictcli monorepo (Python + Go + conformance sub-projects). Five bugs prevent `rlsbl release` from completing in monorepo mode.

## Bug 1: Pre-push hook doesn't recognize monorepo release commit messages

- **Where:** `rlsbl/pre_push_check.py` line ~49
- **Pattern:** `_RELEASE_MSG_RE = r"^v\d+\.\d+\.\d+$"`
- **Problem:** Monorepo releases use commit messages like `"strictcli: release v0.4.0"`, which don't match
- **Effect:** Pre-push hook blocks the release push
- **Fix:** Extend regex to match `^([\w-]+: release )?v\d+\.\d+\.\d+$` or similar

## Bug 2: Pre-push hook checks ALL pushed commits, not just project-relevant ones

- **Where:** `rlsbl/pre_push_check.py`, `_check_jsonl_changelog()`
- **Problem:** `_get_pushed_commits(refs)` returns all pushed SHAs without filtering by project path. In a monorepo, commits touching only `go/` are checked against `python/`'s changelog (and vice versa)
- **Effect:** JSONL coverage check fails even when the project's own commits are fully covered
- **Fix:** Filter pushed commits to only those touching files under the current project's path

## Bug 3: `__init__.py` not included in release commit

- **Where:** `rlsbl/release.py`, `PyPITarget._update_dunder_version()`
- **Problem:** The method modifies `__init__.py` (bumps `__version__`) but `release.py` only adds `version_file()` (pyproject.toml) to `files_to_commit`. The dunder version file is silently left uncommitted.
- **Effect:** Released tag doesn't include the `__version__` bump; requires a manual post-tag fix
- **Fix:** Add the dunder version file path to the commit file list in the release flow

## Bug 4: `uv` commands run from monorepo root instead of project subdirectory

- **Where:** `rlsbl/release.py` line ~291
- **Problem:** After `os.chdir(monorepo_root)`, subprocess calls to `uv sync`, `uv build`, and `uv run pytest` can't find `pyproject.toml` because they're running from the monorepo root, not the project directory
- **Effect:** Built-in tests and build steps fail or run against the wrong project
- **Fix:** Pass `cwd=project_dir` to subprocess calls, or chdir to the project dir before running uv commands

## Bug 5: Tag pattern matching uses `v*` which finds pre-monorepo tags

- **Where:** `rlsbl/changelog/validate.py`, `_unreleased_range()`
- **Problem:** Uses `git describe --tags --abbrev=0 --match 'v*'` to find the last release tag. In a monorepo with project-prefixed tags like `strictcli@v0.2.0`, this matches plain `v*` tags from before the monorepo was set up, giving a wrong commit range
- **Effect:** Validation thinks hundreds of already-released commits are unreleased
- **Fix:** Use `--match '<project_name>@v*'` for monorepo projects

## Related: Changelog-only commit exemption (already filed)

The `monorepo-changelog-only-exemption.md` todo covers a related issue where `_is_changelog_only_commit()` doesn't match monorepo paths like `go/.rlsbl/changes/`. A fix was applied locally but not committed to rlsbl.

## Affected files

- `rlsbl/pre_push_check.py` (bugs 1, 2)
- `rlsbl/release.py` (bugs 3, 4)
- `rlsbl/changelog/validate.py` (bug 5)

## Effort

Medium — each bug is a small fix, but they interact and all need testing with a real monorepo. The pre-push hook bugs (1+2) are the blockers; the rest cause partial failures that can be worked around.
