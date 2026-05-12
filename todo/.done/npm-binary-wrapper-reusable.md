# Reusable npm binary wrapper

## Context

The npm binary wrapper feature (added in 0.18.0 for Go) generates platform-specific npm packages with a thin wrapper package that selects the right binary via optionalDependencies. This is the esbuild/biome/turbo distribution pattern. Currently it's hardcoded into GoTarget.

A downstream project (gamehome) needs the same pattern for Zig binaries, and future targets (Rust/Cargo, C/C++) would also benefit.

## Problem

`_build_npm_publish_jobs()` in `go.py` contains all the logic for generating platform-specific npm packages, the wrapper `bin/index.js`, and the publish workflow jobs. This logic is not reusable by other targets.

## Requirements

- Refactor npm wrapper generation out of GoTarget into a shared utility (mixin, helper module, or base class method)
- Any binary-producing target can opt in via config: `{"npm_wrapper": {"scope": "@myorg"}}` in `.rlsbl/config.json`
- The utility needs:
  - A list of platform/arch combos and their binary paths (provided by the target)
  - The npm scope and package name (from config)
  - Template generation for platform packages + wrapper package
  - Publish workflow job generation
- GoTarget and the new ZigTarget (see `zig-target.md`) should both use this shared utility

## Design notes

The refactored interface could be:

```python
# In a shared module
def build_npm_wrapper_jobs(project_name, scope, platforms, binary_name, archive_pattern):
    """Generate npm wrapper publish jobs for platform-specific binary distribution."""
    ...
```

Where `platforms` is a list like `[("linux", "x64"), ("darwin", "arm64"), ...]` and `archive_pattern` tells the wrapper how to find the binary in the GitHub Release assets.

GoTarget would call this with goreleaser's archive naming convention. ZigTarget would call it with Zig's output naming convention.

## Effort

Small-medium. The logic already exists in go.py; this is a refactor, not new functionality.
