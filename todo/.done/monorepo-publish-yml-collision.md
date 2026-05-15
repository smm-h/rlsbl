# Monorepo sub-projects need independent publish.yml but share a filename

## Problem

In a monorepo, each sub-project gets its own publish workflow. Currently these are routed through a `publish-router.yml` that dispatches to per-project workflows. But PyPI Trusted Publishing registers the workflow filename as part of the OIDC identity claim. When a monorepo sub-project's workflow filename differs from what was registered on pypi.org (e.g., `publish-router.yml` vs `publish.yml`), the OIDC token claim doesn't match and publishing fails.

This happened with strictcli: it was originally a standalone repo with `publish.yml` registered on PyPI as the trusted publisher. After moving into a monorepo with `publish-router.yml`, the OIDC claims no longer matched and all publishes failed silently.

## Requirements

Both standalone repos and monorepo sub-projects must work with identical `publish.yml` filenames so that:
1. PyPI Trusted Publishing works without manual pypi.org reconfiguration when a project moves between standalone and monorepo
2. The scaffold produces the same workflow filename regardless of repo structure
3. Existing Trusted Publisher registrations don't break on repo restructuring

## Possible approaches

1. **Always use `publish.yml`** — monorepo router also named `publish.yml`, per-project workflows get distinct names but the OIDC-facing workflow is always `publish.yml`
2. **Register both filenames on pypi.org** — each project registers both `publish.yml` and `publish-router.yml` as trusted publishers. Redundant but covers both cases.
3. **Monorepo uses per-project `publish-<name>.yml`** — each sub-project gets its own workflow file that pypi.org can be registered against. Router dispatches to these.

## Affected files

- `rlsbl/commands/init_cmd.py` — workflow filename generation
- `rlsbl/templates/` — publish workflow templates
- Documentation for monorepo setup

## Effort

Medium. The fix itself is small but needs testing across standalone and monorepo configurations.
