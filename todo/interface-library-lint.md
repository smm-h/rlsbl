# Interface/Library Boundary Lint

Status: Proposed
Priority: Medium

## Context

rlsbl monorepos follow an architectural principle: projects are either **interfaces** (CLI, daemon, API server, GUI, website) or **libraries** (pure logic, no I/O, no user-facing output). Interfaces should be extremely thin -- they import libraries and wire things together. Libraries should be blind -- no printing, no argparse, no HTTP serving.

This principle is currently enforced by convention (CLAUDE.md, code review). rlsbl could verify it automatically.

## Design

### Project classification

Add an optional `role` field to each project entry in `workspace.toml`:

```toml
[[projects]]
path = "cloudflare"
name = "cloudflare"
role = "library"

[[projects]]
path = "cli"
name = "cli"
role = "interface"

[[projects]]
path = "monitor-daemon"
name = "monitor-daemon"
role = "interface"
```

Valid values: `library`, `interface`. If omitted, the project is not checked.

### Lint rules for libraries (`role = "library"`)

1. **No interface entry points.** The project's manifest must not declare CLI entry points (`[project.scripts]`, `"bin"` in package.json, `func main()` in a Go library).

2. **No I/O imports.** Detect imports of known I/O / interface modules:
   - Python: `argparse`, `click`, `typer`, `flask`, `fastapi`, `django`, `uvicorn`, `granian`
   - Go: `net/http` (when role=library), `cobra`, `urfave/cli`
   - npm: `express`, `koa`, `hono`, `commander`, `yargs`
   
   This is best-effort and heuristic. False positives possible (e.g., a library that builds HTTP clients uses `net/http`). Allow per-project overrides via a `.rlsbl/lint.toml` ignore list.

3. **No direct stdout/stderr.** Detect `print()` calls (Python), `fmt.Println` / `os.Stdout.Write` (Go), `console.log` (JS) in library source files. Exclude test files. This is the most common violation.

### Lint rules for interfaces (`role = "interface"`)

1. **Thin check.** Report the ratio of code in the interface project vs the libraries it depends on. If the interface contains more than N% of the total logic (configurable, default 20%), warn that it may be too thick. This is advisory, not blocking.

### Integration

- `rlsbl doctor` gains a `--lint-roles` check (or is always-on if any project has `role` set)
- `rlsbl monorepo status` could show the role column
- CI: optionally fail on violations via a pre-push or CI check

### Ecosystem support

Start with Python (most common in current monorepos). Detect `print()`, `argparse`, framework imports via AST parsing (not regex -- avoids false positives from comments and strings). Go and npm support can follow.

## Effort Estimate

Medium. AST-based Python detection is straightforward. The `role` field in workspace.toml is trivial. The "thin check" ratio is the most speculative feature and could be deferred.
