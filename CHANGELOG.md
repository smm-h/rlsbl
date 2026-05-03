# Changelog

## 0.8.0

- **Universal three-way merge for scaffold updates.** Replaced all format-specific merge strategies (YAML job-level, JSON deep-merge, line-based, section append) with `git merge-file`. Bases are stored in `.rlsbl/bases/` at scaffold time. On `--update`, user customizations and template updates merge cleanly; conflicts get git-style conflict markers.
- **Removed `ruamel-yaml` dependency.** No longer needed since YAML-aware merging is replaced by three-way text merge.
- **Detailed scaffold output.** Every file now shows its action: created, updated, merged, unchanged, user-owned, or CONFLICTS.

## 0.7.0

- **Removed `check-prs` command.** Was a useless wrapper around `gh pr list`.
- **JSON deep-merge for `.claude/settings.json`.** Scaffold now merges new template keys into existing user settings instead of skipping the file. User values are preserved.
- **YAML job-level merge for CI workflows.** `ci.yml` and `publish.yml` are now merged at the job level: rlsbl-managed jobs are updated, user-added jobs are preserved. Uses `ruamel.yaml` for comment-preserving round-trip parsing.
- **Explicit USER_OWNED category.** `CHANGELOG.md`, `LICENSE`, and hooks are formally marked as user-owned and never overwritten.
- **LICENSE year update.** `scaffold --update` extends the copyright year range to the current year.

## 0.6.0

- **Scripts moved to subcommands.** `check-prs.sh`, `record-gif.sh`, and `pre-push-hook.sh` are no longer scaffolded into `scripts/`. They are now built-in subcommands: `rlsbl record-gif`, `rlsbl pre-push-check`.
- **Hooks moved to `.rlsbl/hooks/`.** `pre-release.sh` and `post-release.sh` moved from `scripts/` to `.rlsbl/hooks/`. `rlsbl release` looks for hooks there.
- **`rlsbl watch` command.** Monitors all CI runs for a commit, prints results to stderr, sends desktop notification, exits 1 on failure. `rlsbl release` prints `Watch CI: rlsbl watch <sha>` for easy invocation.
- **Pre-push hook is a one-liner.** `.git/hooks/pre-push` now calls `exec rlsbl pre-push-check "$@"` instead of being a full script copy. Updates happen via `uv tool upgrade rlsbl`, not re-scaffolding.
- **Removed built-in background CI watcher** from `rlsbl release`. Use `rlsbl watch` explicitly instead.

## 0.5.2

- **Version detection reads source tree first.** `__version__` now reads `pyproject.toml` directly when running from source, fixing stale metadata from editable installs.
- **CLAUDE.md template is registry-specific.** Publish setup instructions (NPM_TOKEN, Trusted Publishing, GoReleaser) now match the project's registry instead of always showing NPM_TOKEN.
- **Gitignore merge normalizes trailing slashes.** `*.egg-info/` and `*.egg-info` are now recognized as duplicates during scaffold merge.
- **`record-gif.sh` no longer hardcodes `/tmp/`.** Uses bare `mktemp` for portability.
- **Go check hidden by default in `rlsbl check`.** Only shown with `--registry go`. Labels changed from "available"/"taken" to "not found"/"exists" since Go modules use repository paths.
- **Auth hint on 403 in `rlsbl discover`.** Suggests `gh auth login` when rate-limited.

## 0.5.1

- **CI watcher prints to stderr.** The background CI watcher now writes results to inherited stderr instead of attempting tty detection. AI agents and terminal users both see CI pass/fail in their output stream. On failure, the GitHub Actions run URL is printed.
- **`*.local-only` gitignore pattern.** Scaffolded `.gitignore` now includes `*.local-only`. Use a `.local-only/` directory or `*.local-only` suffix to keep files out of version control without per-file gitignore entries.

## 0.5.0

- **Post-release hooks.** `scripts/post-release.sh` runs after a successful release with `RLSBL_VERSION` env var set. Non-fatal (release is already complete). Scaffolded via `rlsbl scaffold`.
- **CI watcher.** After pushing, rlsbl spawns a background process that watches CI via `gh run watch` and sends a desktop notification (notify-send on Linux, osascript on macOS) when CI passes or fails.
- `run()` utility accepts optional `env` parameter for subprocess environment
- Ecosystem discoverability: `rlsbl discover` command lists all rlsbl-tagged projects via GitHub topics
- Auto-tagging: `scaffold` and `release` inject `"rlsbl"` keyword into package.json/pyproject.toml and add the `rlsbl` GitHub topic
- Opt-out via `--no-tag` flag, project config (`.rlsbl/config.json`), or user config (`~/.rlsbl/config.json`)
- `rlsbl config` shows ecosystem tagging status and source
- `--quiet` flag is respected by all tagging output
- `rlsbl discover --mine` filters to the authenticated user's repos

## 0.4.2

- Configurable push timeout via `RLSBL_PUSH_TIMEOUT` env var (default 120s), fixing timeouts on repos with slow pre-push hooks
- Bump `run()` default subprocess timeout from 30s to 120s
- All `git push` call sites (release, undo, push_if_needed) use the configurable push timeout
- Print a note when `RLSBL_PUSH_TIMEOUT` overrides the default
- Remove dead `run_silent` function (identical to `run`, zero callers)
- Fix own pre-push hook missing VERSION file detection for Go projects
- Document `RLSBL_PUSH_TIMEOUT` in README

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
