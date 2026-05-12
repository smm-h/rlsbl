# Pre-release hook: transparency and diagnostics

## Status: Open
## Priority: Medium

## Problem

When the pre-release hook fails, `rlsbl release` prints only:

```
Error: pre-release hook failed. Fix the issues and try again.
```

The actual hook output (stdout/stderr) is not shown. The user has no idea what failed or why. They must manually run the hook script to diagnose.

Additionally, the hook ran successfully when invoked directly (`bash .rlsbl/hooks/pre-release.sh`) but failed when invoked by `rlsbl release`. This suggests an environment difference (PATH, working directory, signal handling, or process group) between the two invocation methods.

## Two issues

### 1. Show hook output on failure

When `pre-release.sh` exits non-zero, `rlsbl` should stream or capture and display the hook's stdout and stderr. The user needs to see the test failure, lint error, or whatever caused the abort. Current behavior swallows all output and shows a generic error message.

### 2. Environment parity

The hook should run in the same environment as a direct `bash .rlsbl/hooks/pre-release.sh` invocation. Investigate:
- Is the hook run with the same shell (bash vs sh)?
- Is the working directory the project root?
- Are environment variables (PATH, VIRTUAL_ENV, etc.) inherited?
- Is there a timeout that kills long-running hooks silently?
- Does `set -euo pipefail` in the hook interact differently when spawned as a subprocess?

## Observed context

In selfdoc (596 tests, ~170s runtime), the pre-release hook runs `uv run pytest`. It passes when run directly but fails when run by `rlsbl release`. No error output is visible from rlsbl.
