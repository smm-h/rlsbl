# Cross-registry dependency awareness in release-order

## Context

`rlsbl monorepo release-order` computes topological sort based on intra-workspace dependencies parsed from ecosystem-specific manifests (package.json for npm, pyproject.toml for PyPI). It correctly orders projects within the same ecosystem.

## Problem

In a mixed-ecosystem monorepo, projects may depend on siblings in a different ecosystem. For example:

- `orchestrator` (Python/PyPI) conceptually depends on `framework` (TypeScript/npm) -- it generates TypeScript code that imports from framework, and runs framework's toolchain
- `cli` (Python/PyPI) depends on `orchestrator` (Python/PyPI) -- same ecosystem, already handled

The current release-order output will correctly order `orchestrator` before `cli`, but won't know that `framework` should be released before `orchestrator`. If `framework` gets a breaking change and `orchestrator` isn't updated, the generated games will break.

## Requirements

- Allow declaring cross-registry dependencies in `workspace.toml`:
  ```toml
  [[projects]]
  path = "orchestrator"
  name = "orchestrator"
  depends_on = ["framework"]  # workspace project name, regardless of registry
  ```
- `release-order` should incorporate these manual dependency edges alongside the auto-detected ones
- `monorepo outdated` should report these cross-registry deps (even if it can't auto-detect version constraints)

## Design notes

- This is an explicit declaration, not auto-detection. Cross-registry deps can't be reliably parsed from manifests (a Python project doesn't declare npm dependencies in pyproject.toml).
- The `depends_on` field in workspace.toml is a list of workspace project names. The workspace graph builder adds these as edges alongside the auto-detected ones.
- This is a lightweight addition to `workspace_graph.py`: when building the graph, also read `depends_on` from each project's workspace.toml entry and add those edges.

## Effort

Small. A few lines in workspace graph construction + workspace.toml parsing.
