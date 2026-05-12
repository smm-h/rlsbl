# Monorepo at Scale

Status: Proposed
Priority: High

## Context

rlsbl's monorepo support treats each project as independent -- no concept of intra-workspace dependencies. This works at small scale but limits what the tooling can surface and automate as monorepos grow.

This TODO tracks the gaps and their solutions. Each is a self-contained feature.

## Features

### 1. Dependency graph module

Create `rlsbl/workspace_graph.py` that reads `workspace.toml` + each project's ecosystem manifest and builds a directed graph of intra-workspace dependencies.

Initial ecosystem support: pypi (parse `[project].dependencies` from pyproject.toml) and npm (parse `dependencies`/`devDependencies`/`peerDependencies` from package.json, including `workspace:*` protocol). Other ecosystems deferred (see `todo/.defer/dep-graph-ecosystems.md`).

The graph provides:
- Adjacency list with dependency type (versioned, workspace, path)
- Reverse adjacency (who depends on X)
- Topological sort with cycle detection

This is foundational -- features 2, 3, 4, and 6 all consume it.

### 2. Dependency awareness in `monorepo status`

Add Deps and Rdeps (reverse deps) columns to `monorepo status` output. Shows which projects are load-bearing (high rdep count) and which are leaves. Dynamic columns -- only shown when nonzero values exist.

### 3. `rlsbl monorepo release-order`

New subcommand. Prints workspace projects in topological release order (leaves first). If the graph has cycles, prints an error naming the cycle. If no intra-workspace deps exist, prints alphabetical order with a note.

### 4. `rlsbl monorepo outdated`

New subcommand. For each project, compare its declared constraint on workspace siblings against the sibling's current version.

- Versioned constraints: report ok/outdated
- `workspace:*`/`workspace:^`/`workspace:~`: show status as "workspace"
- Path deps: show status as "path"

Output table: Project / Dependency / Constraint / Current / Status.

### 5. Path dependency publish-time rewriting

PyPI monorepos may use path dependencies (`core @ {root:uri}/../core`) for development. These can't be published to PyPI -- pip can't resolve the path on end-user machines, and PyPI may reject the upload.

Solution: during the pypi target's `build()` step, detect path deps and rewrite them to versioned constraints in a temp copy. Run `uv build` from the temp dir with `--out-dir` pointing to the real project's `dist/`. Working tree is never modified.

For npm: pnpm already rewrites `workspace:*` to real versions at publish time. No rlsbl work needed.

### 6. Monorepo-aware pre-push changelog check

Extend `pre_push_check.py` to detect monorepo context. Parse the pushed ref range to determine which files changed, map files to projects (using project paths and watch globs from workspace.toml), and check each affected project's CHANGELOG.md independently.

A push touching project A only checks A's changelog. A push touching A and B checks both. Independent-release friendly.

### 7. CI at scale audit

Generate a synthetic 30-project workspace and run the router generators against it. Validate:
- Generated YAML is syntactically valid
- Job count is within GitHub's 256-job limit
- `dorny/paths-filter` handles 30 filter entries correctly
- No duplicate job names

Document the ceiling. Fix the generator if issues found. Add a permanent test.

### 8. Per-subcommand help for monorepo commands

`rlsbl monorepo --help` currently dumps the generic top-level help. Add a `SUBCOMMANDS` dict mapping each subcommand to a handler, description, and usage string.

- `rlsbl monorepo --help` lists all subcommands with descriptions
- `rlsbl monorepo <subcmd> --help` prints subcommand-specific usage

Foundation for all new subcommands (check-names, release-order, outdated).

## Effort Estimate

Large overall. Features 1 (graph) and 8 (help) are foundational and should be built first. Features 2-4 are medium, consuming the graph. Feature 5 (path deps) is medium and somewhat independent. Features 6-7 are small-medium.
