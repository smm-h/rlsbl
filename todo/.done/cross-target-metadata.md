# Cross-target metadata consistency

## Context

In multi-target projects (e.g., npm + pypi), each target independently extracts template variables from its own manifest. The `run_cmd_multi()` function in `init_cmd.py` only reads the primary target's `template_vars()` — secondary targets are ignored for everything except the merged publish job.

This creates gaps: metadata that exists in one manifest but is needed by another target's scaffolded files (or by the project itself) has no propagation path.

Discovered while adding a pypi target to a project that already had npm. The project's Node.js wrapper validates a minimum Python version, but there's no way for scaffold templates or doctor checks to know what `requires-python` says in `pyproject.toml`.

## Problems

1. **`requires-python` is never extracted.** The pypi target reads `project.name`, `project.version`, `project.scripts`, and `project.urls`, but not `requires-python`. Scaffolded CI templates (e.g., `setup-python` version) can't use this value.

2. **Secondary target metadata is invisible at scaffold time.** Only the primary target's `template_vars()` is called. If the secondary target has useful metadata (e.g., pypi's `requires-python`, npm's `engines.node`), templates can't reference it.

3. **`doctor` only validates version consistency.** `_check_version_consistency()` compares versions across targets, but name, license, and other shared metadata are not checked.

## Solutions

### A: Expose `requires-python` as a template variable (minimal)

Add `requiresPython` to `PypiTarget.template_vars()`. CI templates can use `{{requiresPython}}` for `setup-python`.

- Pros: Small change, immediately useful
- Cons: Doesn't solve the broader pattern; each new metadata field needs manual plumbing

### B: Merge all targets' template vars at scaffold time (structural)

In `run_cmd_multi()`, call `template_vars()` on all targets and merge the dicts (primary wins on conflicts). Templates get access to all targets' metadata.

- Pros: Solves the pattern once; adding metadata to any target makes it available to all templates
- Cons: Variable name collisions need a strategy (prefix with target name? e.g., `{{pypi.requiresPython}}`)

### C: Extend `doctor` to validate cross-target metadata

Add checks for name, license, and other shared fields. For fields that exist in multiple manifests (like `name`), verify they match or are compatible.

- Pros: Catches drift early
- Cons: What "compatible" means varies per field (e.g., npm name `@scope/foo` vs pypi name `foo`)

### D: All of the above

Do A for the immediate need, B for the structural fix, and C for ongoing validation.

## Recommendation

B + C. Merging all targets' vars (B) solves the template gap structurally, and extending doctor (C) catches metadata drift. A is subsumed by B.

For variable naming, namespaced vars (`{{pypi.requiresPython}}`, `{{npm.engines}}`) avoid collisions and make it clear which target the value comes from. Shared vars (`{{name}}`, `{{version}}`) remain un-namespaced.

## Affected files

| File | Change |
|------|--------|
| `rlsbl/targets/pypi.py` | Extract `requires-python` in `template_vars()` |
| `rlsbl/targets/npm.py` | Extract `engines.node` in `template_vars()` |
| `rlsbl/targets/base.py` | Document namespaced var convention |
| `rlsbl/commands/init_cmd.py` | Merge all targets' vars in `run_cmd_multi()` |
| `rlsbl/commands/doctor.py` | Add cross-target metadata checks (name, license) |
| `rlsbl/templates/ci-python.yml.tpl` | Use `{{pypi.requiresPython}}` for setup-python |
| `tests/test_scaffold_multi.py` | Test merged vars and namespacing |

## Effort

Small-medium. The template var extraction and merging are straightforward. Doctor checks need thought on what "consistent" means per field.
