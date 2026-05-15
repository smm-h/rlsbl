# rlsbl should bump __version__ in Python source files

## Problem

When `rlsbl release` bumps a Python (pypi) project, it updates the version in `pyproject.toml` and `package.json` but NOT in the Python source code's `__version__` variable (typically in `__init__.py`).

This causes drift: `pyproject.toml` says 0.3.0 but `import strictcli; strictcli.__version__` returns 0.2.0.

## Expected behavior

For pypi targets, `rlsbl release` should also find and update `__version__ = "X.Y.Z"` in the package's Python source. The file to update could be:
- Auto-detected by scanning for `__version__` in `__init__.py` files
- Or configured explicitly in `.rlsbl/config.json`

## Discovered

strictcli monorepo, 2026-05-15. The `__version__` in `strictcli/__init__.py` drifted from the release version after two release cycles.
