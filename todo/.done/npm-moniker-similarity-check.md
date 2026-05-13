# rlsbl check: detect npm moniker similarity conflicts

## Status: Open
## Priority: High

## Problem

`rlsbl check selfdoc --target npm` reports "available" because no package named `selfdoc` exists on the registry. But `npm publish` rejects it with:

```
403 Package name too similar to existing package self-doc
```

npm's moniker similarity rule (since December 2017) strips all punctuation (dashes, dots, underscores) from package names and blocks publishing if the normalized form matches an existing package. This check only runs at publish time, not at lookup time.

`rlsbl check` only does a GET to `https://registry.npmjs.org/{name}` and checks for 404. It does not simulate npm's similarity check, so it gives false positives for names that are "available" but unpublishable.

## Impact

We chose the name `selfdoc` based on `rlsbl check` reporting it as available on npm. After building the entire project and attempting to release, npm rejected the publish. The name conflict was only discovered at release time.

## Current state (v0.21.2)

`rlsbl check` already has `get_npm_variants()` and `_check_variants()` (in `rlsbl/commands/check.py`) that generate and check similar names. But the variant generation only transforms **existing** separators — it does `replace("-", "_")`, `replace("_", "-")`, `sub(r"[-_]", "")`, etc. This handles `self-doc` → `selfdoc` (removing a dash), but NOT `selfdoc` → `self-doc` (inserting a dash). You can't reliably guess where to insert dashes in a concatenated word.

So `rlsbl check self-doc` would correctly warn about `selfdoc`, but `rlsbl check selfdoc` does NOT warn about `self-doc`. The check is one-directional.

## Proposed fix

The variant generation approach is fundamentally limited for names without separators. Instead, use npm's own normalization:

1. Normalize the target name by stripping all dashes, dots, and underscores (lowercase)
2. Use npm's search API (`https://registry.npmjs.org/-/v1/search?text={name}&size=20`) to find packages with similar names
3. Normalize each search result the same way
4. If any normalized result matches the normalized target, report the conflict

This catches both directions: `selfdoc` vs `self-doc` and `self-doc` vs `selfdoc`, because both normalize to `selfdoc`.

Alternative simpler approach: use npm's registry endpoint for the normalized form. Since npm internally indexes by normalized name, a GET to `https://registry.npmjs.org/{normalized}` might return the conflicting package directly. (Needs verification — npm may not expose this.)

## Reference

- npm blog post: https://blog.npmjs.org/post/168978377570/new-package-moniker-rules.html
- npm/npm#19438: discussion of the rule
