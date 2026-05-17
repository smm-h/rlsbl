# Go target: use path-based tags in monorepos

## Problem

Go modules in subdirectories require tags formatted as `{subdir}/v{version}` (e.g., `go/v0.1.1`). The Go module proxy resolves versions by matching the tag prefix to the module's subdirectory path. rlsbl's monorepo tag format uses `{name}@v{version}` (e.g., `go-strictcli@v0.1.1`), which the Go proxy can't resolve.

This means `go get github.com/smm-h/strictcli/go@v0.1.1` fails because the proxy looks for a `go/v0.1.1` tag and finds only `go-strictcli@v0.1.1`.

## Required fix

The Go target's `monorepo_tag_format()` should produce `{path}v{version}` (using the workspace path, e.g., `go/`) instead of `{name}@v{version}`.

For the `go` target specifically:
- Current: `monorepo_tag_format("go-strictcli", "0.1.1")` -> `"go-strictcli@v0.1.1"`
- Expected: should produce `"go/v0.1.1"` (matching the workspace `path = "go/"`)

This requires `monorepo_tag_format` to receive the workspace path (not just the name), or the Go target needs access to it some other way.

## Tag detection also needs updating

`rlsbl status`, `rlsbl changelog validate`, and the release flow all use `git describe --tags --match '{name}@v*'` to find the last release tag. After this change, the Go target must match `go/v*` instead.

## Migration for existing projects

After this fix ships, projects like strictcli need to:
1. Create new-format tags (`go/v0.1.0`, `go/v0.1.1`) at the same commits as old tags
2. Delete old-format tags (`go-strictcli@v0.1.0`, `go-strictcli@v0.1.1`)
3. Update GitHub Releases to reference new tags
4. Notify the Go proxy: `GOPROXY=https://proxy.golang.org,direct go list -m github.com/smm-h/strictcli/go@v0.1.1`

## Affected

Any monorepo with a Go sub-project (e.g., strictcli).
