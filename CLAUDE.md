# rlsbl

Release orchestration and project scaffolding CLI. Automates the full release lifecycle for npm, PyPI, and Go projects: version bumping, changelog validation, git tagging, GitHub Release creation, CI/CD scaffolding, and CI monitoring.

Built in Python 3.11+ (one dependency: tomlkit), also distributed as an npm wrapper package. Current version: check `package.json`.

Key commands:

- `rlsbl release [patch|minor|major]` -- bump version, tag, push, create GitHub Release
- `rlsbl scaffold [--update|--force]` -- generate/update CI/CD workflows, hooks, changelog, license
- `rlsbl status` -- show version, branch, last tag, changelog coverage
- `rlsbl watch <sha>` -- poll CI status for a commit
- `rlsbl undo` -- revert the last release (delete tag, GH release, revert commit)
- `rlsbl check <name> --registry <r>` -- check name availability on npm/PyPI
- `rlsbl config` -- show/migrate project configuration
- `rlsbl discover` -- list rlsbl ecosystem projects via GitHub topics

## Release workflow

This project uses [rlsbl](https://github.com/smm-h/rlsbl) for release orchestration.

- Update CHANGELOG.md with a `## X.Y.Z` entry describing changes
- Run `rlsbl release [patch|minor|major]` to bump version and create a GitHub Release
- CI handles publishing automatically via the publish workflow
- Never publish manually — always use `rlsbl release`
- Requires NPM_TOKEN secret on GitHub (Settings > Secrets > Actions)
- Use `rlsbl release --dry-run` to preview a release without making changes

## Conventions

- No tokens or secrets in command-line arguments (use env vars or config files)
- All file writes to shared state should be atomic (write to tmp, then rename)
- External calls (APIs, CLI tools) must have timeouts and graceful fallbacks
- Use `npm link` (npm) or `uv pip install -e .` (Python) for local development
- CI runs smoke tests on every push; manual testing for UI/UX changes
