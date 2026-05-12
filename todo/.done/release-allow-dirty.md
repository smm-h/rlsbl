# `rlsbl release --allow-dirty`

Status: Proposed
Priority: High

## Context

`rlsbl release` requires a clean working tree (`git status --porcelain` must be empty) before proceeding. This prevents accidentally releasing with uncommitted changes that should be part of the release.

However, it also blocks releases when the working tree has legitimate in-progress changes unrelated to the release. For example: you fix a bug and want to release a patch, but you also have uncommitted docs improvements in progress. The clean-tree gate forces you to either commit unfinished work or abandon it before releasing.

`git stash` would solve this in a normal workflow, but multi-session worktree safety rules forbid stash (it can corrupt concurrent sessions).

## Proposed Solution

Add `--allow-dirty` flag to `rlsbl release`. When passed, skip the clean-tree check. The release operates on committed state only — uncommitted changes are neither included nor affected.

The flag is an explicit acknowledgment: "I know my tree is dirty and I accept that the uncommitted files are not part of this release."

## Implementation

In `rlsbl/commands/release.py`, the clean-tree check runs early in the release flow. When `--allow-dirty` is present in flags, skip it. Everything else (version bump, commit, tag, push) operates on committed content, so dirty files are irrelevant to the release artifact.

Register `"allow-dirty"` as a boolean flag (not a VALUE_FLAG — it takes no argument).

## Effort

Small. One flag check, one conditional skip.
