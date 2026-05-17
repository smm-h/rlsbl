# Selfdoc integration

## Problem

rlsbl has no awareness of selfdoc. Projects using selfdoc for documentation sites have no automated validation or build step during releases. Stale docs ship silently.

## Proposed feature

Detect if a project uses selfdoc (presence of `selfdoc.json` in the project root) and automatically:

1. **During `rlsbl release`:** Run `selfdoc check` as part of pre-release validation. Fail the release if check fails (unless `--skip-docs`).
2. **During `rlsbl release`:** Run `selfdoc build` to regenerate the site. Commit any changed output files as part of the release commit.
3. **During `rlsbl scaffold --update`:** Add a `selfdoc check` step to the CI workflow if `selfdoc.json` exists.
4. **In `rlsbl doctor`:** Add a `--check selfdoc` diagnostic that runs `selfdoc check` and reports coverage, staleness, and SEO issues.

## Detection

Simple file existence: `os.path.exists(os.path.join(project_root, "selfdoc.json"))`.

Read `selfdoc.json` to find the output directory (default `docs/_build/`) so rlsbl knows which files to commit after build.

## Integration points

- `release.py` -- add selfdoc check after built-in tests/lint, before version bump
- `release.py` -- add selfdoc build after version bump (so the site has the new version)
- `scaffold.py` -- add selfdoc check step to CI template if detected
- `doctor.py` -- add selfdoc diagnostic check

## Skip flag

`--skip-docs` on `rlsbl release` to bypass selfdoc check and build (parallel to `--skip-tests` and `--skip-lint`).

## Effort estimate

Small-medium. Detection is trivial. The check/build integration is straightforward subprocess calls. The scaffold CI template change requires a conditional block.
