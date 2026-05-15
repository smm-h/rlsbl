# Pre-push hook passes git arguments to rlsbl pre-push-check

## Problem

The scaffolded `.git/hooks/pre-push` hook is:

```bash
#!/usr/bin/env bash
exec rlsbl pre-push-check "$@"
```

Git passes the remote name and URL as positional arguments to pre-push hooks (e.g., `origin gp:user/repo.git`). These get forwarded via `"$@"` to `rlsbl pre-push-check`, which does not accept positional arguments. This causes:

```
error: unexpected argument 'origin'
try 'rlsbl --help'
```

This blocks all `git push` operations, including `rlsbl release` (which pushes internally).

## Fix

Drop `"$@"` from the scaffolded hook template. The hook should be:

```bash
#!/usr/bin/env bash
exec rlsbl pre-push-check
```

Alternatively, update `rlsbl pre-push-check` to accept and ignore positional arguments.

## Affected files

- The hook template in rlsbl's scaffold code (wherever `.git/hooks/pre-push` content is generated)
- `rlsbl scaffold --update` should fix existing hooks

## Effort

Small. One-line fix in the template.
