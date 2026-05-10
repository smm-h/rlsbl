# Monorepo guide

rlsbl supports monorepo workflows via the `rlsbl monorepo` command family. A monorepo workspace is defined by a `.rlsbl-monorepo/workspace.toml` file at the repository root.

## Getting started

```bash
# Initialize a monorepo workspace
rlsbl monorepo init

# Add a project
rlsbl monorepo add --name mylib --path packages/mylib

# List projects
rlsbl monorepo list

# Show workspace status
rlsbl monorepo status

# Release a specific project from its directory
cd packages/mylib
rlsbl release patch
```

## workspace.toml format

The workspace file lives at `.rlsbl-monorepo/workspace.toml`. Each project is a TOML table in the `[[projects]]` array:

```toml
[[projects]]
path = "packages/mylib"
name = "mylib"

[[projects]]
path = "packages/cli"
name = "cli"
```

Fields per project:

| Field | Required | Description |
| ----- | -------- | ----------- |
| path | yes | Relative path from repo root to the project directory |
| name | no | Project name (defaults to basename of path) |

## Workspace module

:::module rlsbl.workspace
:::

## Watch paths

Each project in a monorepo tracks changes independently. When releasing from within a project directory, rlsbl auto-detects which project you are in using the workspace configuration.

## Subtree publishing

Monorepo projects can be published to separate repositories using git subtree. The `rlsbl monorepo sync` command handles pushing subtrees to their configured remotes.
