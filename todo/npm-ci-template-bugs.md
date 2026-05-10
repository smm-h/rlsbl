# npm CI template bugs

Issues found when scaffolding npm projects in monorepos.

## 1. No package install step

The npm CI template scaffolded by `rlsbl monorepo add` runs `npm test --if-present` without installing dependencies first. This fails immediately because devDependencies (vitest, etc.) are not installed.

The template needs a package install step before the test step. For pnpm workspace projects, this should be `pnpm install` from the workspace root, not `npm install` from the package directory.

### Affected template

The npm CI template in rlsbl that generates `<project>/.github/workflows/ci.yml`.

### Fix

Add an install step. The template should detect whether the project is in a pnpm workspace (look for `pnpm-workspace.yaml` or `pnpm-lock.yaml` in ancestors) and generate the appropriate install command:

- pnpm workspace: `pnpm/action-setup@v4` + `pnpm install --frozen-lockfile` from workspace root
- npm: `npm ci` from package directory
- yarn: `yarn install --frozen-lockfile` from package directory

## 2. Uses `npm test` instead of package manager's test

Even after install, the template uses `npm test` and `npm audit` regardless of the project's actual package manager. If the project uses pnpm, these should be `pnpm test` and `pnpm audit`.
