# Pre-release hook should uv sync before pytest

## Problem

After `rlsbl scaffold --update`, the project's `.venv` can become stale or mismatched. When `rlsbl release` runs the pre-release hook, `uv run pytest` may fail with `ModuleNotFoundError` because the venv doesn't have the project installed.

## Reproduction

1. Have a Python project with a working `.venv` (Python 3.13)
2. Run `rlsbl scaffold --update` (which commits changes to CI, gitignore, etc.)
3. Run `rlsbl release patch --yes`
4. Pre-release hook runs `uv run pytest` which fails because the venv is stale

The fix is to manually `rm -rf .venv && uv sync` before releasing.

## Proposal

In the scaffolded `pre-release.sh`, add `uv sync` before `uv run pytest`:

```bash
if [ -f pyproject.toml ]; then
  echo "  Python: pytest"
  if command -v uv &>/dev/null; then
    uv sync --quiet
    uv run pytest
  fi
fi
```

This ensures the venv is current before running tests, with negligible overhead when already synced.

## Found in

strictcli project after `scaffold --update` from 0.21.2 to 0.22.1.
