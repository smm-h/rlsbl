# Go scaffold: ensure root main package

Status: Proposed
Priority: Medium

## Context

Go's official module layout guide says single-binary projects should have `package main` at the module root so `go install github.com/user/project@latest` works. The `cmd/<name>/` pattern is only for multi-binary repos.

rlsbl's Go target scaffolds CI and publish workflows but doesn't enforce or check the main package location. When a Go project has its binary in `cmd/<name>/`, `go install module@latest` fails with "does not contain package". Users must use `go install module/cmd/<name>@latest` instead, which is non-standard and breaks assumptions (e.g., CI steps that install dependencies via the standard path).

This came up when rlsbl's own CI needed `go install github.com/smm-h/safegit@latest` -- it failed because safegit had its main in `cmd/safegit/`. The fix was manual: move 14 files to root.

## Proposal

Add a check to rlsbl's Go target that detects `cmd/<name>/` main packages and offers to move them to root during `rlsbl scaffold` or `rlsbl scaffold --update`.

### Detection

- Scan for `cmd/*/main.go` files with `package main`
- Check if root already has a `main.go` with `package main`
- If cmd/ main exists and root main doesn't: flag it

### Action

During `rlsbl scaffold` for Go projects:
1. Detect the `cmd/<name>/` pattern
2. Print a warning: "Go project has main in cmd/<name>/. Standard `go install` won't work."
3. With `--fix` or interactively: move all `.go` files from `cmd/<name>/` to root, delete empty `cmd/` dirs, update any references in goreleaser config, Dockerfile, Makefile, etc.

### Files to update on move

- `.goreleaser.yml` (`main: ./cmd/<name>` -> `main: .`)
- `Dockerfile` (any `go build ./cmd/<name>` -> `go build .`)
- `Makefile` (build commands)
- `.rlsbl/hooks/pre-release.sh` and `post-release.sh` (build/install commands)
- `README.md` and `CONTRIBUTING.md` (install/build instructions)

### Edge cases

- Multi-binary repos (`cmd/foo/`, `cmd/bar/`): skip the check, `cmd/` is correct here
- Root already has `main.go`: no action needed
- `cmd/<name>/` imports unexported symbols from other `cmd/<name>/` files: safe to move since they're all `package main`

## Affected files

| File | Change |
|------|--------|
| `rlsbl/targets/go.py` | Add `_has_root_main()` and `_has_cmd_main()` detection |
| `rlsbl/commands/init_cmd.py` | Call detection during scaffold, print warning |
| `tests/test_targets.py` | Tests for root main detection |

## Effort estimate

~0.5 session. Detection is simple (glob for files, read first line). The move logic is more involved but optional (can start with warning-only).
