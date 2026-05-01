# Changelog

## 0.4.1

- Go adapter uses VERSION file as version source (not git tags)
- First release bootstraps from VERSION without bumping
- find_commit_tool returns "safegit" not full path
- Pre-release.sh template auto-detects Go/npm/Python and runs appropriate checks
- Pre-push hook template supports Go VERSION file
- README documents Go support
- GoReleaser NEXT_STEPS clarified (CI handles it, no local install needed)

## 0.4.0

- Go project support: scaffold with GoReleaser, CI, and publish workflows
- Version-file-less registries: release skips commit step when version is the git tag
- Go name availability check via pkg.go.dev
- Cross-compilation template (linux/darwin/windows x amd64/arm64)

## 0.3.0

- Confirmation prompt on release (skip with --yes)
- `config` command: show detected registries, scaffolding state, workflows, hooks
- `undo` command: revert a botched release (deletes tag, reverts commit, deletes GitHub Release)
- Merged publish workflow for dual-registry projects (scaffold generates one file with both npm + pypi jobs)

## 0.2.0

- CLI redesign: `--registry` flag replaces positional registry argument
- Rename `check-name` command to `check`
- All commands are top-level: `rlsbl release`, `rlsbl check`, `rlsbl scaffold`, `rlsbl status`
- Fix astral-sh/setup-uv version (v7, not v8)

## 0.1.1

- Fix astral-sh/setup-uv version (v8 tag doesn't exist, use v7)

## 0.1.0

- Initial release as `rlsbl` (renamed from share-it-on)
- Pure Python (stdlib only, Python 3.11+, tomllib for TOML parsing)
- 4 top-level commands: `release`, `status`, `scaffold`, `check-name`
- Auto-detects registries from project files (package.json, pyproject.toml)
- Release syncs version across all detected version files
- Context-aware scaffold: appends CLAUDE.md, merges .gitignore, preserves custom CI
- Hash-based `--update` mode detects customized files
- Pre-release hook, pre-push changelog enforcement
- 63 tests
- Dual-publish CI: npm (token) + PyPI (OIDC Trusted Publishing)
- Also installable via npm (thin Node wrapper)
