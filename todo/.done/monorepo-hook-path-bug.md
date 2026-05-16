# Monorepo: pre-release hook path constructed incorrectly

## Problem

When running `rlsbl release` from a monorepo sub-project directory (e.g., `cd python && rlsbl release minor --yes`), the pre-release hook path is constructed as `{subdir}/.rlsbl/hooks/pre-release.sh` (e.g., `python/.rlsbl/hooks/pre-release.sh`), but the command executes with CWD set to the sub-project directory. This means the path resolves to `python/python/.rlsbl/hooks/pre-release.sh`, which doesn't exist.

## Reproduction

```bash
cd ~/Projects/strictcli/python
rlsbl release minor --yes
```

Output:
```
bash: python/.rlsbl/hooks/pre-release.sh: No such file or directory
Error: pre-release hook exited with code 127.
```

## Expected behavior

The hook path should be resolved relative to the sub-project root (i.e., `.rlsbl/hooks/pre-release.sh`), or the CWD should be set to the monorepo root when the path includes the sub-project prefix.

## Impact

Blocks all releases for monorepo sub-projects that have pre-release hooks. Workaround: temporarily remove the hook, release, then restore it.

## Affected

All monorepo projects using rlsbl with pre-release hooks (e.g., strictcli).
