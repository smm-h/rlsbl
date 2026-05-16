# Release aborts on self-modified .validated cache

## Problem

During `rlsbl release`, the changelog validation step updates `.rlsbl/changes/.validated` (caching the HEAD hash of the successful validation). Later in the same release flow, rlsbl's concurrent-change detection runs `git status` and finds `.validated` modified — flagging it as an unexpected external modification and aborting the release.

The error message is:
```
Unexpected modified files detected (possible concurrent change): python/.rlsbl/changes/.validated. Aborting release.
```

## Reproduction

```bash
cd ~/Projects/strictcli/python
# Ensure .validated is committed and clean
rlsbl release minor --yes
# Fails with "Unexpected modified files detected"
```

## Expected behavior

rlsbl should either:
1. Exclude `.validated` from the concurrent-change check (it's expected to be modified by the release itself), or
2. Not write `.validated` during the release flow (only during standalone `rlsbl changelog validate`), or
3. Stage `.validated` as part of the release commit

## Impact

Blocks all releases for projects with JSONL changelog validation caching. Workaround: unclear (--allow-dirty may help but unclear if it bypasses this specific check).

## Affected

All rlsbl projects using JSONL changelog with validation caching.
