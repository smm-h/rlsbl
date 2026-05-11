# rlsbl should find project root, not rely on cwd

Status: Proposed
Priority: Medium

## Context

When running `rlsbl release` from a subdirectory of the project (e.g., `pypi/`), rlsbl fails with "CHANGELOG.md not found" because it looks for files relative to cwd, not relative to the `.rlsbl/` directory.

This happened twice in the migrable project: after `cd pypi && python -m build && twine upload`, the working directory was left in `pypi/` and the next `rlsbl release` failed.

## Proposal

rlsbl should walk up from cwd to find the `.rlsbl/` directory (similar to how git finds `.git/`) and resolve all paths relative to that project root. If `.rlsbl/` is not found in any ancestor, error with "not in an rlsbl project."

This is the standard pattern used by git, cargo, npm, and most project-aware tools.

## Affected files

| File | Change |
|------|--------|
| `rlsbl/cli.py` or `rlsbl/utils.py` | Add `find_project_root()` that walks up to find `.rlsbl/` |
| All command files | Use the resolved project root instead of `"."` |

## Effort estimate

~0.5 session. The walk-up logic is trivial. The main work is auditing all file path references in command files to ensure they use the resolved root.
