# Yank / deprecate a past release

## Context

When a release ships with a critical bug (e.g., safegit v0.9.1 broke all macOS commits), a follow-up patch release fixes it, but the broken release remains available on GitHub. There is no `rlsbl` command to mark a past release as broken or remove it. `rlsbl undo` only reverts the *most recent* release and deletes its tag — it cannot target an arbitrary older version.

## Problem

After releasing v0.9.2 to fix v0.9.1, the broken v0.9.1 release is still visible on GitHub with downloadable binaries. Users browsing releases or pinning to v0.9.1 will get a broken build. There is no automated way to signal "don't use this version."

## Options

### Option A: `rlsbl yank <version>` — mark as pre-release + deprecation notice

Mark the GitHub Release as a "pre-release" (hides it from the "Latest" badge and most tooling that fetches the latest release) and prepend a deprecation notice to the release body.

| Pros | Cons |
|------|------|
| Non-destructive — release and assets stay available | Pre-release flag is a GitHub concept, may not be respected by all consumers |
| Reversible — can un-yank by removing the flag | Requires editing release body (string manipulation on existing notes) |
| Clear signal in the GitHub UI | "Pre-release" is semantically wrong — it wasn't a pre-release, it was a bad release |
| Simple implementation: `gh release edit <tag> --prerelease --notes "..."` | |

Optional `--redirect <version>` flag to include "use vX.Y.Z instead" in the notice.

### Option B: `rlsbl yank <version> --delete` — delete the release, keep the tag

Delete the GitHub Release and its binary assets. The git tag stays (preserving history and `git describe` output). The release page returns 404 but the tag is still browsable.

| Pros | Cons |
|------|------|
| Strongest signal — release is gone | Destructive — binaries are deleted, can't be recovered without re-releasing |
| No ambiguity about whether the version is usable | Users with pinned references get 404s instead of a helpful message |
| Simple: `gh release delete <tag> --yes` | Breaks go module proxy cache (though the proxy may retain its own copy) |
| Tag preservation means git history is intact | No deprecation notice — just absence |

### Option C: Soft deprecation — edit release notes only

Don't change the release status. Just prepend a warning banner to the release body:

```
> **Deprecated:** This release has a critical bug on macOS. Use v0.9.2 instead.
```

| Pros | Cons |
|------|------|
| Least disruptive — nothing changes structurally | Easy to miss — users must read the release notes |
| Reversible — just edit the notes back | Tooling that fetches "latest" may still pick this version if it was latest at the time |
| Works well as a companion to Option A | Alone, provides no programmatic signal |

### Option D: Combined — default soft, `--hard` to delete

`rlsbl yank <version>` does Option A (mark pre-release + notice). `rlsbl yank <version> --hard` does Option B (delete release). This covers both the cautious and aggressive cases.

| Pros | Cons |
|------|------|
| One command, two modes | Slightly more implementation surface |
| Default is non-destructive | `--hard` flag naming may conflict with other conventions |
| Covers all use cases | |

## Recommendation

Option D (combined) is the most flexible. The default `yank` is safe and reversible; `--hard` is available when the release is genuinely dangerous. The deprecation notice should include the reason and the replacement version:

```
rlsbl yank v0.9.1 --reason "broken on macOS" --use v0.9.2
```

## Affected files

- New command in rlsbl CLI (sibling to `release`, `undo`, `watch`)
- Uses `gh release edit` (soft) or `gh release delete` (hard)
- Should validate that the target version exists as a GitHub Release
- Should refuse to yank the current/latest version (use `rlsbl undo` for that)

## Effort

Small to medium. The core is two `gh` CLI calls behind a flag. The main work is argument validation, release body editing, and handling edge cases (version not found, already yanked, yank the latest).
