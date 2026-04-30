# Changelog

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
