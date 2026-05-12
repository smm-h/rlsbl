# Dependency Graph: Additional Ecosystem Parsers

Status: Deferred
Deferred because: No existing monorepo uses these ecosystems for intra-workspace dependencies.
Trigger: Build when a real monorepo uses one of these ecosystems and needs dependency awareness.

## Context

The dependency graph module (`rlsbl/workspace_graph.py`) initially supports pypi and npm dependency parsing. These are the ecosystems used in existing monorepos. Additional ecosystem parsers should be added when real demand exists.

## Deferred Ecosystems

### cargo (Rust)

Parse `[dependencies]` from `Cargo.toml` using tomlkit (already a project dependency). Cargo workspaces use `{ path = "../sibling" }` for intra-workspace deps -- detect these as graph edges.

### go

Parse `require` block from `go.mod` (plain text, line-by-line). Also detect `replace` directives that point to local paths (`=> ../sibling`). No existing go monorepo uses intra-workspace deps, so this is speculative.

### deno

Parse `imports` from `deno.json` (JSON). Deno uses import maps -- workspace deps might appear as `"@scope/sibling": "./sibling/mod.ts"`.

### hex (Elixir)

Parse `deps` from `mix.exs`. Elixir syntax -- would need a lightweight parser or regex extraction. Workspace deps use `{:sibling, path: "../sibling"}`.

### maven (Java/Kotlin)

Parse `<dependencies>` from `pom.xml` (XML) or dependency declarations from `build.gradle.kts` (Kotlin DSL). Most complex due to XML/Kotlin parsing. Gradle version catalogs add another layer.

## Effort Per Ecosystem

- cargo: Small (tomlkit already available)
- go: Small (plain text parsing)
- deno: Small (JSON)
- hex: Medium (Elixir syntax parsing)
- maven: Large (XML + Gradle Kotlin DSL)
