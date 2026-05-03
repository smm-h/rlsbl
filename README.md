<p align="center">
  <img src="logo.svg" alt="rlsbl" width="336" height="105">
</p>

# rlsbl

Release orchestration and project scaffolding CLI for npm, PyPI, and Go.

## Install

From npm:

```
npm i -g rlsbl
```

From PyPI (requires Node.js 18+):

```
uv tool install rlsbl
```

## Quick start

```
rlsbl scaffold
rlsbl release minor
```

## Commands

All commands work at the top level -- registries are auto-detected from project files (`package.json`, `pyproject.toml`, `go.mod`). Use `--registry <npm|pypi|go>` when you need to target a specific registry.

### scaffold [--force] [--update]

Scaffolds CI/CD infrastructure and release tooling for all detected registries.

```
rlsbl scaffold
rlsbl scaffold --registry npm          # target npm only
rlsbl scaffold --registry pypi --force # overwrite existing files
rlsbl scaffold --registry go           # target Go only
```

Context-aware behavior when files already exist (without `--force`):

| File | Behavior |
|---|---|
| `CLAUDE.md` | Appends rlsbl sections if the marker is not present |
| `.gitignore` | Merges missing entries from the template |
| `.github/workflows/ci.yml` | Preserves existing file, prints a note to review manually |
| All others | Skipped |

### release [patch|minor|major] [--dry-run] [--quiet]

Bumps version, commits, pushes, and creates a GitHub Release. Defaults to `patch`.

```
rlsbl release minor
rlsbl release major --dry-run --registry npm
```

The version is synced across all detected project files (`package.json`, `pyproject.toml`, `VERSION`) regardless of which registry is primary. Go projects use a plain `VERSION` file as the version source.

If `.rlsbl/hooks/pre-release.sh` exists, it runs before any changes are made. A non-zero exit aborts the release. If `.rlsbl/hooks/post-release.sh` exists, it runs after the release completes (non-fatal). See [Release flow](#release-flow) for details.

### status

Shows project status: package name, version (per registry), git branch, last tag, working tree state, changelog coverage, and CI workflow presence.

```
rlsbl status
rlsbl status --registry pypi
```

### check \<name\>

Checks name availability on both npm and PyPI, and warns about confusingly similar names.

```
rlsbl check my-cool-lib
rlsbl check my-cool-lib --registry npm   # npm only
```

npm checks variant spellings (hyphens, underscores, dots, no separator). PyPI normalizes per PEP 503 and checks common alternatives.

### discover [--mine]

Lists all projects in the rlsbl ecosystem by querying GitHub for repositories with the `rlsbl` topic.

```
rlsbl discover
rlsbl discover --mine              # only your repos
```

Uses GitHub token if available (higher rate limit). Works unauthenticated for public repos.

### Ecosystem tagging

By default, `scaffold` and `release` add an `"rlsbl"` keyword to `package.json` and/or `pyproject.toml`, and set the `rlsbl` topic on the GitHub repository. This makes projects discoverable via `rlsbl discover`.

To disable tagging:

| Method | Scope |
|---|---|
| `--no-tag` flag | Single invocation |
| `{"tag": false}` in `.rlsbl/config.json` | This project |
| `{"tag": false}` in `~/.rlsbl/config.json` | All your projects |

Precedence: CLI flag > project config > user config > default (enabled).

Global flags: `--help`, `--version`.

## Release flow

When you run `release`, the following happens in order:

1. Verifies `gh` CLI is installed and authenticated
2. Checks that the git working tree is clean
3. Reads the current version from the primary project file
4. Computes the new version and confirms the git tag does not already exist
5. Validates that `CHANGELOG.md` contains a `## <new-version>` section
6. Runs `.rlsbl/hooks/pre-release.sh` if present (non-zero exit aborts)
7. Writes the new version to the primary project file
8. Syncs the new version to all other detected project files
9. Commits the version bump (uses `safegit` if available, otherwise `git`)
10. Pushes the branch to `origin`
11. Creates a GitHub Release tagged `v<new-version>` with the changelog entry as notes
12. The GitHub Release triggers `publish.yml`, which publishes to the registry
13. Runs `.rlsbl/hooks/post-release.sh` if present (non-fatal -- the release is already complete). The `RLSBL_VERSION` env var is set to the released version. Useful for local install (`go install ./cmd/myapp/`), deploy, or notifications.
14. Spawns a background process that watches CI via `gh run watch`. When CI finishes, it prints the result to stderr (so AI agents can read it) and sends a desktop notification (`notify-send` on Linux, `osascript` on macOS). On CI failure, it also prints the GitHub Actions run URL. This happens automatically -- no configuration needed.

## What scaffold creates

| File | Source | Purpose |
|---|---|---|
| `.github/workflows/ci.yml` | Registry-specific | CI workflow (lint, test) |
| `.github/workflows/publish.yml` | Registry-specific | Publish on GitHub Release (OIDC) |
| `CHANGELOG.md` | Shared | Version changelog |
| `LICENSE` | Shared | MIT license (author and year filled in) |
| `.gitignore` | Shared | Standard ignores for the ecosystem |
| `CLAUDE.md` | Shared | AI assistant instructions |
| `.claude/settings.json` | Shared | Claude Code settings |
| `.rlsbl/hooks/pre-release.sh` | Shared | User-customizable pre-release validation |
| `.rlsbl/hooks/post-release.sh` | Shared | User-customizable post-release actions |
| `.git/hooks/pre-push` | Shared | One-liner that calls `rlsbl pre-push-check` |

Hook files are made executable automatically. The `record-gif` and `pre-push-check` functionality is provided as built-in subcommands (`rlsbl record-gif`, `rlsbl pre-push-check`) rather than scaffolded scripts.

The scaffolded `.gitignore` includes a `*.local-only` pattern. Create a `.local-only/` directory or rename files with a `.local-only` suffix to keep them out of version control -- useful for local-only assets, experiments, and keeping the working tree clean for tools that check `git status`.

## Pre-push hook

The `rlsbl pre-push-check` subcommand enforces changelog coverage. During `scaffold`, a one-liner git hook is installed at `.git/hooks/pre-push` that calls this subcommand. It prevents pushing when `CHANGELOG.md` lacks an entry for the current version.

How it works:

1. Detects project type (`package.json`, `pyproject.toml`, or `VERSION`)
2. Extracts the current version
3. Checks that `CHANGELOG.md` contains a heading `## <version>`
4. Blocks the push with an error if the entry is missing

To reinstall manually:

```
echo '#!/bin/sh' > .git/hooks/pre-push && echo 'exec rlsbl pre-push-check "$@"' >> .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

## First publish

The first version must be published manually before CI can take over:

| Registry | Manual first publish | Then configure |
|---|---|---|
| npm | Add an `NPM_TOKEN` secret to your GitHub repo (Settings > Secrets > Actions), then push a release | CI handles subsequent publishes |
| PyPI | Run `uv publish` | Set up [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) on pypi.org |
| Go | Push to GitHub and create a release -- Go modules are published by the tag itself | No secrets needed; `pkg.go.dev` indexes automatically |

After configuration, all subsequent releases are handled by CI when `rlsbl release` creates a GitHub Release. Go projects use GoReleaser in CI (via GitHub Actions) to build cross-platform binaries.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RLSBL_PUSH_TIMEOUT` | `120` | Timeout in seconds for `git push` operations. Increase if your pre-push hooks (e.g. test suites) take longer than 2 minutes. |
| `RLSBL_VERSION` | -- | Set automatically when running `.rlsbl/hooks/post-release.sh`. Contains the just-released version string. |

## Requirements

- Node 18+
- [GitHub CLI](https://cli.github.com) (`gh`), installed and authenticated
- git

## License

MIT
