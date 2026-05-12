# Changelog

## 0.20.0

- **Breaking: `rlsbl check` now requires `--target`.** The implicit default of checking both npm and PyPI has been removed. Specify `--target npm`, `--target pypi`, or `--target go` explicitly.
- **Multi-name checking.** `rlsbl check foo bar baz --target pypi` checks multiple names in one invocation and prints a compact table. Single-name invocations still show the verbose format with variants.
- **Rate limiting for `rlsbl check`.** New `--delay` flag (default 200ms) throttles between names. HTTP 429 responses from PyPI/Go/GitHub trigger automatic retry with exponential backoff.
- **`rlsbl monorepo check-names`.** Batch-check name availability for all workspace projects. Supports `--prefix` and `--suffix` to evaluate namespacing strategies (e.g., `--prefix www- --target pypi`).
- **`rlsbl monorepo release-order`.** Shows the topological order to release projects in, based on intra-workspace dependencies. Detects cycles.
- **`rlsbl monorepo outdated`.** For each project, shows its intra-workspace dependency constraints against current sibling versions. Reports versioned deps as ok/outdated, and labels workspace/path references.
- **Dependency columns in `rlsbl monorepo status`.** New Deps and Rdeps columns show how many workspace siblings each project depends on and how many depend on it. Hidden when no intra-workspace dependencies exist.
- **Monorepo-aware pre-push changelog check.** The pre-push hook now detects monorepo context and only checks changelogs for projects whose files appear in the pushed commits.
- **Per-subcommand help for `rlsbl monorepo`.** Each subcommand now has its own `--help` with usage and description.
- **Path dependency rewriting for PyPI.** When building a PyPI package in a monorepo, path dependencies (e.g., `core @ {root:uri}/../core`) are automatically rewritten to versioned constraints in a temp copy. The working tree is never modified.

## 0.19.1

- No user-facing changes.

## 0.19.0

- **`rlsbl deploy [name]` command.** Deploy to configured targets via SSH with health checks (HTTP, TCP, script) and automatic rollback on failure. Configure targets in `.rlsbl/config.json` under the `deploy` key. Supports `--dry-run` to preview without executing and `--force` to override branch restrictions.
- **Deploy after publish.** `rlsbl release` runs deploy automatically after publish completes. Deploy failures do not undo the release — retry with `rlsbl deploy <name>`.
- **Deploy CI workflow template.** `rlsbl scaffold` generates a deploy workflow when deploy targets are configured.
- **Project root discovery.** rlsbl now finds the project root automatically, so commands work from any subdirectory (like git, cargo, npm).
- **Scaffold untracks gitignored files.** `rlsbl scaffold` runs `git rm --cached` on tracked files matching new `.gitignore` entries.
- **Monorepo: lock files moved to `.rlsbl-monorepo/`.** `rlsbl release` no longer creates a spurious `.rlsbl/` directory at the repo root.

## 0.18.1

- **`env_file` config key.** Set `"env_file": "~/path/to/.env"` in `.rlsbl/config.json` to load environment variables before release. Useful for secrets needed by target publish steps (e.g., `CLOUDFLARE_API_TOKEN` for docs deploys).

## 0.18.0

- **Go binary distribution: Homebrew tap.** Go binary projects can now scaffold Homebrew tap support. Set `{"homebrew": {"tap": "homebrew-tap"}}` in `.rlsbl/config.json` to add a `brews:` section to the goreleaser config and pass `HOMEBREW_TAP_TOKEN` to the publish workflow. Users install via `brew install user/tap/tool`.
- **Go binary distribution: npm wrapper.** Go binary projects can scaffold npm binary wrapper packages (the esbuild/biome/turbo pattern). Set `{"npm_wrapper": {"scope": "@user"}}` to generate platform-specific packages for 6 platforms (linux/darwin/win32, x64/arm64), a wrapper package with `optionalDependencies`, a bin script, and a publish workflow that packages goreleaser archives into npm packages. Users install via `npm install -g @user/tool`.
- **Breaking: removed `--include` and `--exclude` flags from `rlsbl release`.** Target selection for releases is now config-only via `release_targets` in `.rlsbl/config.json`.

## 0.17.0

- **Cross-target metadata in templates.** Multi-target projects now merge template variables from all targets during scaffold, not just the primary. Variables are namespaced by target (`{{pypi.minRequiredPython}}`, `{{npm.minRequiredNode}}`). CI templates include runtime version references from project manifests (`requires-python`, `engines.node`, `go` directive, `rust-version`).
- **`rlsbl doctor`: metadata consistency checks.** Three new checks validate that package name, license, and description are consistent across targets. Names are normalized per registry conventions (npm scope stripping, PyPI PEP 503, Go module path). Mismatches produce warnings, not failures.
- **Per-target subdirectory paths.** Targets can now live in subdirectories. Configure with `{"name": "npm", "path": "npm/"}` in the `targets` array (plain strings still default to project root). Version sync, build, publish, doctor, status, and scaffold all resolve per-target paths. Useful for projects that ship wrapper packages alongside the main artifact.

## 0.16.1

- **npm scaffold: lockfile warning.** `rlsbl scaffold` now warns when an npm project has no lockfile (`package-lock.json`, `pnpm-lock.yaml`, or `yarn.lock`) and adds a "run npm install" step to the next steps output. Prevents broken CI from `npm ci` failing on first push.

## 0.16.0

- **`rlsbl doctor` command.** Diagnoses release state with 7 checks: stale lock file, version consistency across targets, local/remote tag existence, GitHub Release existence, branch sync, changelog coverage. `--fix` auto-repairs safe issues (stale locks, missing remote tags, missing GitHub Releases).
- **Lock file hardening.** `.rlsbl/lock` added to gitignore template. `atexit` handler ensures lock cleanup on process exit. New `is_stale()` helper for doctor.
- **Go scaffold: goreleaser ldflags.** Goreleaser template now includes `-X main.version={{.Version}}` for version injection at build time.
- **Go scaffold: dynamic goreleaser main field.** `main:` field auto-detects root vs `cmd/<name>/` project structure via `{{goreleaserMain}}` template variable.
- **Go scaffold: version.go generation.** Binary Go projects get a scaffolded `version.go` with `ReadBuildInfo` fallback for `go install` users. Libraries are excluded.
- **npm: package manager detection.** `NpmTarget` detects pnpm, yarn, or npm by searching for lock files from the project directory up to the git root.
- **npm: per-manager CI and publish templates.** Separate CI and publish workflow templates for npm, pnpm, and yarn. pnpm templates include `pnpm/action-setup@v4`. All CI templates now include an install step before testing.

## 0.15.0

- **Deleted built-in config migration engine.** Removed `rlsbl/lib/` (ConfigMigrator, schema_loader, ~440 LOC), the `rlsbl config` subcommand tree, and all associated tests (~1,500 LOC). Config migrations are now handled by the external `migrable` tool.
- **`rlsbl migrate` command.** Shells out to `migrable migrate --config-dir .rlsbl`. Supports `--dry-run` and `--status`. Gives install instructions if migrable is not found.
- **`--json` flag for `rlsbl status`.** Outputs structured JSON with name, version, target, branch, tag, clean, changelog, ci, publish.
- **Documented hidden flags.** `--no-commit` and `--skip-shared` now appear in `rlsbl scaffold --help`.
- **Go root main detection.** `rlsbl scaffold` warns when a Go project has its main package in `cmd/<name>/` instead of the project root, since `go install module@latest` won't work.

## 0.14.0

- **Router watch paths.** Projects in a monorepo can declare extra file patterns to watch via `--watch` on `monorepo add` or the `watch` key in `workspace.toml`. The CI router generates multi-line path filters including both the project directory and all watch entries.
- **Swift target split.** New `swift-apple` target for Apple-platform Swift projects (macOS-only CI). The existing `swift` target keeps macOS+ubuntu for server-side Swift. `swift-apple` requires explicit declaration in `.rlsbl/config.json` (no auto-detection).
- **Subtree publishing.** Monorepo projects with `subtree_remote` configured get automatic git subtree pushes after release. The project's subdirectory is split and pushed to a mirror repo with plain semver tags, enabling SPM consumption. A GitHub Release is also created on the mirror. Failures are non-fatal.
- **Explicit target enforcement.** `rlsbl scaffold` now warns when using auto-detected targets and always writes the detected target to `.rlsbl/config.json`, ensuring subsequent runs use explicit config.
- **`monorepo status` enhanced.** Optional Watch column (path count) and Remote column (subtree URL) appear when projects use these features.
- **`monorepo sync` warns for Swift projects** without `subtree_remote`, since SPM can't resolve monorepo-style prefixed tags.
- **12 registered targets.** swift-apple joins npm, pypi, go, swift, cargo, deno, docker, hex, maven, spec, docs.

## 0.13.1

- **Monorepo sync adds `working-directory`.** Synced CI workflows now include `defaults: run: working-directory: {path}` so steps run in the correct project subdirectory.
- **Monorepo add shows guidance.** When no target is detected, the error now suggests which manifest files to create.
- **Dynamic merged publish workflows.** Multi-target projects now get dynamically generated publish workflows composed from each target's individual template. Supports all 11 targets, replaces the static npm+pypi+go-only merged template.

## 0.13.0

- **Monorepo support.** New `rlsbl monorepo` command family for managing multi-project repos with independent versioning. Projects remain fully standalone — extracting to a solo repo requires zero config changes.
  - `monorepo init` creates a `.rlsbl-monorepo/workspace.toml` workspace manifest.
  - `monorepo add <path>` registers a project (auto-detects target, auto-scaffolds, auto-syncs CI).
  - `monorepo remove <path>` unregisters a project.
  - `monorepo list` shows all registered projects.
  - `monorepo status` shows version, latest tag, target, and unreleased changelog entries per project.
  - `monorepo sync` copies per-project CI workflows to root, rewrites triggers to `workflow_call`, generates a CI router (paths-filter dispatch) and publish router (tag-prefix dispatch), sets copies read-only with source header.
- **Scoped releases in monorepos.** `rlsbl release` inside a monorepo project automatically prefixes tags (`name@vX.Y.Z`), scopes version reads/writes and changelog to the project subdirectory, and uses a scoped commit message.
- **Monorepo-aware `rlsbl status`.** Shows monorepo tag format and project count hint when inside a monorepo project.
- **Scaffold triggers monorepo sync.** Running `rlsbl scaffold` inside a monorepo project automatically syncs workflows to root.

## 0.12.0

- **7 new release targets.** swift (SPM), cargo (Rust/crates.io), deno (JSR), hex (Elixir/hex.pm), maven (Gradle/Maven), docker, spec (versioned specifications). Each with CI/publish templates and hybrid publish support.
- **Opt-in target config.** Projects declare targets in `.rlsbl/config.json` `"targets"` array. Auto-detection remains as fallback for existing projects.
- **Hybrid publish.** `rlsbl release` publishes locally when ecosystem token is available (NPM_TOKEN, CARGO_REGISTRY_TOKEN, HEX_API_KEY, etc.). Falls back to CI otherwise.
- **Private registry workflow.** `rlsbl scaffold --private` (or auto-detected) skips publish.yml, generates a post-release hook that uploads artifacts to GitHub Releases. Prints consumer install instructions.
- **tomlkit replaces TOML regex.** `pyproject.toml` editing (version bumps, keyword injection) now uses tomlkit for correct round-trip editing with comment preservation. Fixes edge cases with `[project.urls]` sub-tables.
- **detect_targets() covers all targets.** Auto-detection now finds all 11 registered targets, not just npm/pypi/go.

## 0.11.3

- **`--include`/`--exclude` release flags.** Control which targets run during release. Replaces `--skip-docs`.
- **`release_targets` config.** Declare baseline targets in `.rlsbl/config.json` to avoid auto-detect surprises.

## 0.11.2

- **Watch re-polls for late-starting workflows.** After initial runs complete, waits 5 seconds and re-polls for workflows that started late (e.g., Publish triggered by GitHub Release creation). Fixes missing Publish detection.

## 0.11.1

- **Release aborts if behind remote.** Fetches origin before releasing and exits if local branch is behind. Use `--skip-remote-check` for offline releases.
- **Watch reports which workflows ran.** After CI completes, prints a summary table of workflow names and results. Warns if a publish workflow exists on disk but didn't trigger.

## 0.11.0

- **Docs system extracted to selfdoc.** `rlsbl docs` commands removed. DocsTarget now detects `selfdoc.json` and delegates to the `selfdoc` CLI. Install selfdoc separately for documentation generation.
- **`rlsbl check` includes GitHub repo search.** Shows repo count as informational context (not an availability check) after registry checks.
- **Codehome target removed.** The plugin target and `rlsbl register` command were premature and have been removed pending a more mature design.

## 0.10.1

- **Codehome target rewrite.** Now root-scoped: each plugin (or plugin group) lives in its own repo with `plugin.json`. Standard `v1.2.3` tags, no namespacing. Push is delivery.
- **Plugin validation.** Release validates `plugin.json` has required fields (name, version, description) and valid semver.
- **`rlsbl register` command.** Prints the JSON registry entry for the current plugin repo (name, repo URL, description, plugins provided).
- **Scaffold template for codehome.** `rlsbl scaffold --target codehome` creates CI workflow that validates plugin.json.

## 0.10.0

- **Codehome plugin target.** `--target codehome --scope plugins/<name>` releases individual plugins from a monorepo. Reads/writes `plugin.toml`, creates namespaced tags (`name@v1.2.3`).
- **Docs target.** Auto-generate documentation from Python docstrings and deploy to Cloudflare Pages or GitHub Pages. `rlsbl docs init/build/serve/deploy` commands. Zero external dependencies (stdlib `ast` + built-in MD/HTML converter).
- **`rlsbl targets` command.** Lists all available targets with detection status, scope type, and version file.
- **Multi-target release.** Secondary root-scoped targets (e.g., docs) auto-run build+deploy during release. Use `--skip-docs` to opt out.
- **`--target` and `--scope` CLI flags.** `--target` selects the release target explicitly. `--scope` restricts operations to a subdirectory for subdir-scoped targets.
- **`--registry` deprecated.** Use `--target` instead. Prints a deprecation warning when used.
- **Scoped release safety.** Validates scope path exists, includes pyproject.toml in commit for plugin targets, warns when `--scope` is used with root-scoped targets.

## 0.9.1

- **`rlsbl config show` subcommand.** Bare `rlsbl config` now prints help; use `config show` for project info.
- **Race condition parsing fix.** Porcelain parser handles stripped leading whitespace correctly.

## 0.9.0

- **`rlsbl unreleased` command.** Lists commits since last tag, cross-references CHANGELOG entries, reports coverage status. Supports `--json` for machine-readable output.
- **`rlsbl prs` command.** Lists open GitHub pull requests for the current repo.
- **Config management system.** `rlsbl config init/migrate/status` subcommands for managing project config with schema-driven migration (deep merge, flat merge, list-by-key merge strategies, versioned migrations, atomic writes).
- **Scaffold auto-commits.** Created files are committed automatically (use `--no-commit` to opt out). Runs config migrations when `.rlsbl/config-schema.json` exists.
- **Parallel watch.** `rlsbl watch` polls CI runs concurrently (total time = max of all runs, not sum).
- **Parallel variant checking.** `rlsbl check` uses ThreadPoolExecutor for concurrent registry queries.
- **Advisory lockfile.** `.rlsbl/lock` prevents concurrent release/scaffold operations.
- **`rlsbl undo` improvements.** Auto-pushes revert commit (with confirmation prompt, or automatic with `--yes`). Prints structured failure summary table with remediation commands on partial failure.
- **Pre-release suffix support.** `bump_version` handles versions like `1.0.0-beta.1`.
- **`--force` no longer overwrites user-owned files.** CHANGELOG.md, LICENSE, and hooks are preserved even with `--force`.
- **Pre-release hook receives `RLSBL_VERSION`.** Matches the existing post-release hook behavior.
- **Release race condition fix.** Aborts if unexpected files are modified before commit.
- **Top-level error handler sanitized.** No longer exposes sensitive CalledProcessError details.
- **Discover hardened.** Pagination capped at 20 pages; retries once on HTTP 403 with `Retry-After` header.
- **`record-gif` validates flags.** Clear error message on non-integer flag values.
- **npm check timeout.** Variant checking has 10-second subprocess timeout.
- **Release prompt mentions ecosystem tagging** when enabled.

## 0.8.3

- Fix watch: resolve short SHAs to full 40-char (`gh run list --commit` requires it)
- Pre-release hook runs Python checks before npm (faster failure)
- Node.js 24 in all CI/publish templates (dropped Node 18 EOL)
- Go CI template uses `go-version-file: go.mod` instead of hardcoded versions; adds `-race` flag

## 0.8.2

- Handle KeyboardInterrupt in watch command (clean exit, no stack trace)
- Escape AppleScript strings in watch notifications (prevents injection via git tags)
- Clear error when `--registry` is missing a value
- Resolve project config path at call time (not module import time)
- Add `--width`, `--height`, `--font-size`, `--duration` flags to record-gif

## 0.8.1

- **Templates included in wheel.** Moved `templates/` into the `rlsbl/` package so non-editable installs (pip, pipx) get them. Previously `rlsbl scaffold` crashed on PyPI installs.
- **`undo` checks prerequisites.** Now verifies gh CLI auth and clean working tree before proceeding.
- **Non-ASCII preserved in package.json.** `json.dumps` now uses `ensure_ascii=False`.
- **TOML trailing comma fix.** Adding the rlsbl keyword no longer produces a double comma.
- **Pagination URL validation in `discover`.** Only follows `Link` header URLs pointing to `api.github.com`.
- **`.rlsbl/version` included in release commit.** No more orphaned version marker changes.

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
- Ecosystem discoverability: `rlsbl discover` command lists all rlsbl-tagged projects via GitHub topics
- Auto-tagging: `scaffold` and `release` inject `"rlsbl"` keyword into package.json/pyproject.toml and add the `rlsbl` GitHub topic
- Opt-out via `--no-tag` flag, project config (`.rlsbl/config.json`), or user config (`~/.rlsbl/config.json`)
- `rlsbl config` shows ecosystem tagging status and source
- `--quiet` flag is respected by all tagging output
- `rlsbl discover --mine` filters to the authenticated user's repos

## 0.4.2

- Configurable push timeout via `RLSBL_PUSH_TIMEOUT` env var (default 120s), fixing timeouts on repos with slow pre-push hooks
- Print a note when `RLSBL_PUSH_TIMEOUT` overrides the default
- Fix own pre-push hook missing VERSION file detection for Go projects

## 0.4.1

- Go adapter uses VERSION file as version source (not git tags)
- First release bootstraps from VERSION without bumping
- Pre-release.sh template auto-detects Go/npm/Python and runs appropriate checks
- Pre-push hook template supports Go VERSION file
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
- Dual-publish CI: npm (token) + PyPI (OIDC Trusted Publishing)
- Also installable via npm (thin Node wrapper)
