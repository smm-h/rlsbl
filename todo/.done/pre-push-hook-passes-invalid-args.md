# pre-push hook passes invalid positional args to rlsbl

## Problem

The scaffolded `.git/hooks/pre-push` script passes `"$@"` to `rlsbl pre-push-check`. Git invokes pre-push hooks with the remote name and URL as positional arguments ($1 and $2). Since `rlsbl pre-push-check` doesn't accept positional arguments, this causes the command to fail.

## Reproduction

Any `git push` in a repo with the scaffolded pre-push hook:
```
rlsbl pre-push-check origin https://github.com/user/repo.git
```
Fails because `rlsbl pre-push-check` doesn't expect positional args.

## Fix

Remove `"$@"` from the pre-push hook template. The scaffold should generate:
```bash
rlsbl pre-push-check
```
Not:
```bash
rlsbl pre-push-check "$@"
```

Alternatively, make `rlsbl pre-push-check` silently ignore positional arguments.

## Affected files

- The scaffold template that generates .git/hooks/pre-push
- Any existing repos that have the scaffolded hook (they have the bug now)

## Effort

Trivial — one-line fix in the template.
