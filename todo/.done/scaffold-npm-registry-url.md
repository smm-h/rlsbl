# Bug: npm publish workflow has unresolved template variable

## Problem

When `rlsbl scaffold --update` generates a publish workflow for an npm target, the `registry-url` field in the `actions/setup-node` step contains the raw template placeholder `{{registryUrl}}` instead of the resolved value `https://registry.npmjs.org`.

This causes the GitHub Actions workflow to fail with "workflow file issue" on every publish attempt.

## Reproduction

1. Create a project with `"targets": ["pypi", "npm"]` in `.rlsbl/config.json`
2. Run `rlsbl scaffold --update`
3. Check `.github/workflows/publish.yml` -- the npm job has `registry-url: {{registryUrl}}`

## Expected

The template should resolve to `https://registry.npmjs.org` (or the appropriate registry URL for the target).

## Found in

excli project, rlsbl scaffold version in `.rlsbl/version`.
