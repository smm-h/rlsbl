# Support projects with no publish target in monorepos

## Context

A monorepo may contain projects that are not published to any registry -- for example, template/scaffold directories, internal tools, shared config, or specification documents that are versioned alongside code but don't produce publishable artifacts.

## Problem

`rlsbl monorepo add <path>` requires a detected target. If no manifest file is found (no `package.json`, `pyproject.toml`, `Cargo.toml`, etc.), it errors with "No release target detected." There is no way to register a project that doesn't publish.

## Requirements

- Allow `monorepo add --no-target <path>` (or `--target none`) to register a project without a publish target
- The project still gets:
  - A `.rlsbl/` directory with version tracking
  - Changelog enforcement
  - Tag-prefixed releases (creating a GitHub Release with changelog notes, but no publish step)
  - Inclusion in `monorepo status` output
- The project does NOT get:
  - Publish workflow generation
  - Target-specific CI (but can have a custom CI workflow)
  - Build steps during release

## Design notes

This could be implemented as a `NoneTarget` (or `LocalTarget`) that:
- Detects nothing (opt-in only via `--target none`)
- Reads/writes version from a `VERSION` file
- Has no build or publish methods
- Scaffold generates only the changelog, gitignore, and hooks (no CI workflows)

Alternatively, the existing `spec` target could be relaxed to serve this purpose, but `spec` implies a specification document with its own semantics.

## Effort

Small. Minimal target implementation with no build/publish logic.
