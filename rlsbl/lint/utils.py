"""Shared file walking utilities for linters."""

import fnmatch
import os
from pathlib import Path

_EXCLUDED_DIRS = frozenset({
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
})


def walk_source_files(
    project_path: str,
    extensions: tuple[str, ...],
    exclude_patterns: list[str],
) -> list[str]:
    """Walk project directory, return source files matching extensions.

    Excludes directories in _EXCLUDED_DIRS and .egg-info dirs.
    Applies exclude_patterns (fnmatch) against relative paths.
    By default (empty exclude_patterns), all files including tests are included.
    """
    results = []
    for dirpath, dirs, filenames in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d not in _EXCLUDED_DIRS and not d.endswith(".egg-info")
        ]

        # Prune directories that match exclude patterns
        if exclude_patterns:
            rel_dir = os.path.relpath(dirpath, project_path)
            pruned = []
            for d in dirs:
                rel_subdir = os.path.join(rel_dir, d) if rel_dir != "." else d
                # Check if directory itself matches a pattern (e.g. "tests/")
                skip = False
                for pat in exclude_patterns:
                    if pat.endswith("/"):
                        if fnmatch.fnmatch(d, pat.rstrip("/")) or fnmatch.fnmatch(
                            rel_subdir + "/", pat
                        ):
                            skip = True
                            break
                    elif fnmatch.fnmatch(rel_subdir, pat):
                        skip = True
                        break
                if not skip:
                    pruned.append(d)
            dirs[:] = pruned

        for filename in filenames:
            if not any(filename.endswith(ext) for ext in extensions):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, project_path)

            # Check file-level exclude patterns
            if exclude_patterns:
                skip = False
                for pat in exclude_patterns:
                    if pat.endswith("/"):
                        # Directory pattern, already handled above
                        parts = Path(rel).parts
                        dir_name = pat.rstrip("/")
                        if dir_name in parts:
                            skip = True
                            break
                    elif fnmatch.fnmatch(os.path.basename(rel), pat):
                        skip = True
                        break
                    elif fnmatch.fnmatch(rel, pat):
                        skip = True
                        break
                if skip:
                    continue

            results.append(full)
    return results
