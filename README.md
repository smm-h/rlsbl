# rlsbl

Release orchestration and project scaffolding CLI for npm and PyPI.

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

All commands work at the top level -- registries are auto-detected from project files (`package.json`, `pyproject.toml`). Use the registry-specific form (`rlsbl <registry> <command>`) only when you need to target a single registry.

### scaffold [--force] [--update]

Scaffolds CI/CD infrastructure and release tooling for all detected registries.

```
rlsbl scaffold
rlsbl npm scaffold          # target npm only
rlsbl pypi scaffold --force # overwrite existing files
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
rlsbl npm release major --dry-run
```

The version is synced across all detected project files (`package.json`, `pyproject.toml`) regardless of which registry is primary.

If `scripts/pre-release.sh` exists, it runs before any changes are made. A non-zero exit aborts the release.

### status

Shows project status: package name, version (per registry), git branch, last tag, working tree state, changelog coverage, and CI workflow presence.

```
rlsbl status
rlsbl pypi status
```

### check-name \<name\>

Checks name availability on both npm and PyPI, and warns about confusingly similar names.

```
rlsbl check-name my-cool-lib
rlsbl npm check-name my-cool-lib   # npm only
```

npm checks variant spellings (hyphens, underscores, dots, no separator). PyPI normalizes per PEP 503 and checks common alternatives.

Global flags: `--help`, `--version`.

## Release flow

When you run `release`, the following happens in order:

1. Verifies `gh` CLI is installed and authenticated
2. Checks that the git working tree is clean
3. Reads the current version from the primary project file
4. Computes the new version and confirms the git tag does not already exist
5. Validates that `CHANGELOG.md` contains a `## <new-version>` section
6. Runs `scripts/pre-release.sh` if present (non-zero exit aborts)
7. Writes the new version to the primary project file
8. Syncs the new version to all other detected project files
9. Commits the version bump (uses `safegit` if available, otherwise `git`)
10. Pushes the branch to `origin`
11. Creates a GitHub Release tagged `v<new-version>` with the changelog entry as notes
12. The GitHub Release triggers `publish.yml`, which publishes to the registry

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
| `scripts/check-prs.sh` | Shared | PR review helper |
| `scripts/pre-release.sh` | Shared | Pre-release hook (runs before each release) |
| `scripts/record-gif.sh` | Shared | Terminal recording helper |
| `scripts/pre-push-hook.sh` | Shared | Pre-push changelog enforcement |

All `.sh` files in `scripts/` are made executable automatically. The pre-push hook is installed into `.git/hooks/pre-push` during scaffold.

## Pre-push hook

The scaffolded `scripts/pre-push-hook.sh` is installed as a git pre-push hook during `scaffold`. It prevents pushing when `CHANGELOG.md` lacks an entry for the current version.

How it works:

1. Detects project type (`package.json` or `pyproject.toml`)
2. Extracts the current version
3. Checks that `CHANGELOG.md` contains a heading `## <version>`
4. Blocks the push with an error if the entry is missing

To reinstall manually:

```
cp scripts/pre-push-hook.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

## First publish

The first version must be published manually before CI can take over:

| Registry | Manual first publish | Then configure |
|---|---|---|
| npm | Add an `NPM_TOKEN` secret to your GitHub repo (Settings > Secrets > Actions), then push a release | CI handles subsequent publishes |
| PyPI | Run `uv publish` | Set up [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) on pypi.org |

After configuration, all subsequent releases are handled by CI when `rlsbl release` creates a GitHub Release.

## Requirements

- Node 18+
- [GitHub CLI](https://cli.github.com) (`gh`), installed and authenticated
- git

## License

MIT
