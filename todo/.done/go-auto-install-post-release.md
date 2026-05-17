# Auto `go install .` in post-release for Go CLI projects

## Problem

Go CLI projects (those with `package main`) should have their local binary updated after a release. Currently this requires manually adding `go install .` to `.rlsbl/hooks/post-release.sh`. Only safegit does this; other Go CLI projects (saferm, howmuchleft, migrable) don't.

## Proposal

Make `go install .` a built-in post-release step for Go targets that have `package main`, similar to how the Go module proxy notification is already built in. This should run after the push+tag but before any user-owned post-release hook logic.

Skip for libraries (no `package main`) since there's nothing to install.

## Current state

- safegit: manually added to post-release.sh
- saferm, howmuchleft, migrable: not present
- go-toml-edit: library, not applicable

## Affected code

The Go target's `publish()` method or the post-release step in the release flow. Should print something like:

```
Installing <binary> v<version>...
Installed: /home/user/go/bin/<binary>
```
