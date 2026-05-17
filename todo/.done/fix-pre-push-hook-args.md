# Pre-push hook passes $@ to rlsbl, causing strictcli rejection

## Problem
The pre-push hook template generates `exec rlsbl pre-push-check "$@"`. Git calls pre-push hooks with `<remote-name> <remote-url>` as positional arguments. strictcli rejects these as unknown arguments, causing every push to fail with:

```
error: unexpected argument 'origin'
try 'rlsbl --help'
```

## Solution
Change the template from `exec rlsbl pre-push-check "$@"` to `exec rlsbl pre-push-check` (no args). The rlsbl CLAUDE.md already documents this: "The hook does NOT pass $@ to rlsbl."

## Affected files
- `rlsbl/templates/shared/.git-hooks/pre-push` (or wherever the template lives)

## Effort
Trivial — one-line fix in the template.
