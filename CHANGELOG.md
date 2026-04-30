# Changelog

## 0.4.6

- Fix: multi-registry scaffold no longer clobbers shared/registry-specific files
- Fix: seed hashes for skipped files so future --update has a baseline
- Bump astral-sh/setup-uv from v6 to v8 (fixes Node 20 deprecation warning)
- 63 tests (22 new integration tests for scaffold command)
- Dual-registry projects now scaffold for primary registry only (avoids workflow conflicts)

## 0.4.5

- Fix: scaffold --update now detects customized files via SHA-256 hash comparison (prevents overwriting custom work)
- Stores file hashes in .rlsbl/hashes.json for future update safety
- Conservative default: files with no stored hash are treated as customized (safe skip)

## 0.4.4

- Rename `init` command to `scaffold` (`init` still works as alias)
- Add `--update` mode: refreshes managed files (CI, publish, hooks) while preserving customized files
- Fix CI: install pytest before running tests
- Read version from `importlib.metadata` (works in wheel installs, not just editable)
- Standardize on `publish.yml` for workflow naming (reverted from `workflow.yml`)
- Fix safegit vs git commit strategy in release command

## 0.4.3

- Fix: stage files before commit in release (plain git was producing empty commits)
- Fix: crash when no project file found for release/status commands
- Fix: atomic writes for version files (prevents corruption on interrupt)
- Fix: section-aware version replacement in pyproject.toml (won't match [tool.*] sections)
- Fix: helpful errors for missing version fields in package.json/pyproject.toml
- Fix: 30s timeout on all subprocess calls (prevents indefinite hangs)
- Add pytest to CI pipeline (41 tests run on Python 3.11-3.14)
- Read version from importlib.metadata (works in wheel installs)
- Standardize on publish.yml for workflow naming
- Bump GitHub Actions to v5

## 0.4.2

- Standardize generated publish workflow name to workflow.yml (matches PyPI Trusted Publishing default)
- Derive binCommand from `[project.scripts]` in pypi adapter
- Scaffolding freshness validation: writes `.rlsbl/version` marker, pre-push hook warns on version drift

## 0.4.1

- Fix npm package: include Python source in files array (was shipping empty lib/)
- CI tests Python 3.11-3.14 + Node wrapper
- Bump GitHub Actions to v5 (checkout, setup-node, setup-python)
- Bump actions to v5 in all scaffolding templates
- 41 Python unit tests (ported from JS)
- Strip src/ prefix from hatch packages when deriving import name

## 0.4.0

- Full rewrite from JavaScript to Python (stdlib only, Python 3.11+)
- TOML parsing via `tomllib` (replaces fragile regex for pyproject.toml reading)
- Import name derivation from hatch packages config with `src/` prefix stripping
- Git tagging on release (local tag + push)
- No more Node.js dependency for PyPI users
- npm distribution uses thin Node wrapper that delegates to `python3 -m rlsbl`
- 33 unit tests (JS, to be ported)

## 0.3.0

- All commands now work top-level without registry prefix: `rlsbl release`, `rlsbl status`, `rlsbl init`, `rlsbl check-name`
- `release` auto-detects registries and syncs version across all project files (package.json + pyproject.toml)
- `check-name` checks both npm and PyPI when called top-level
- `init` scaffolds for all detected project files when called top-level
- `status` shows version info for all detected registries
- Pre-push hook template enforcing changelog entries before push
- Registry-specific prefix still works as fallback (`rlsbl npm init`)
- Publish workflow renamed to `workflow.yml` for PyPI Trusted Publishing UX
- Published on both npm and PyPI

## 0.2.0

### New commands
- `rlsbl <registry> status` -- show package name, version, branch, last tag, changelog status, CI presence

### Init improvements
- Context-aware CLAUDE.md: appends release workflow section to existing file instead of skipping
- Context-aware .gitignore: merges missing entries instead of skipping
- Preserves existing CI workflow with a helpful note
- Scaffolds `scripts/check-prs.sh` + `.claude/settings.json` SessionStart hook
- Scaffolds `scripts/record-gif.sh` for demo asset generation
- Scaffolds `scripts/pre-release.sh` for custom pre-release validation
- Scaffolds `scripts/pre-push-hook.sh` and auto-installs as git pre-push hook
- CLAUDE.md template now includes a Conventions section (atomic writes, no tokens in argv, graceful fallbacks)
- Gitignore template now includes `.credentials.json`, `.*-cache.json`, `.env`

### Release improvements
- Pre-release hook: runs `scripts/pre-release.sh` if present, aborts on failure
- Changelog quality warning for entries under 10 characters
- Atomic write for release notes temp file
- `--quiet` flag to suppress informational output
- Removed "stash" from error messages

### Check-name improvements
- Distinguishes "available" from "network error" (no more false positives)
- 5-second timeout on HTTP requests
- Suppressed npm stderr noise

### Security and correctness
- Token-based auth as default (OIDC Trusted Publishing removed -- requires 2FA)
- Consistent `execFile` usage (no shell) for all git and gh commands
- NPM_TOKEN in publish workflow template and own publish workflow

## 0.1.0

- Initial release
- `rlsbl npm init` / `rlsbl pypi init` -- scaffold release infrastructure
- `rlsbl npm release` / `rlsbl pypi release` -- orchestrate a release
- `rlsbl npm check-name` / `rlsbl pypi check-name` -- check name availability
