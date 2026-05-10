# scaffold generates CI that requires package-lock.json but doesn't ensure it exists

## Context

`rlsbl scaffold` generates a CI workflow (`.github/workflows/ci.yml`) that uses `npm ci` for npm-target projects. `npm ci` requires `package-lock.json` to exist -- without it, CI fails immediately on the first run.

Discovered in codehome: rlsbl scaffolded CI, but the project had no lockfile committed. CI failed with `EUSAGE: The npm ci command can only install with an existing package-lock.json`.

## Problem

There is no check or assistance during `scaffold` to ensure the lockfile exists. A freshly scaffolded npm project gets CI that is broken out of the box.

## Solutions

### A. Warn during scaffold if package-lock.json is missing

- Detect npm target, check for lockfile, print a warning with instructions
- Lowest effort, non-intrusive
- Doesn't fix the problem, just surfaces it

### B. Generate lockfile during scaffold

- Run `npm install --package-lock-only` during scaffold if lockfile is missing
- Fixes the problem automatically
- May surprise users who intentionally omit lockfiles (some library authors)

### C. Add config option for install strategy

- Add a `npm_install_strategy` config key (`ci` or `install`)
- Default to `ci` but allow `install` for projects without lockfiles
- Template renders the chosen strategy
- Most flexible but adds config surface area

### D. Warn + offer to generate (interactive)

- During scaffold, detect missing lockfile, ask "Generate package-lock.json? (y/n)"
- In non-interactive mode (`--yes`), default to generating it
- Best UX: informs the user and offers a fix in one step

## Recommendation

D is the most correct. It matches rlsbl's existing interactive style and handles both interactive and CI usage.

## Affected files

- `src/scaffold.ts` (or equivalent) -- add lockfile detection + prompt
- Scaffold templates for npm CI workflows (already use `npm ci`, no change needed)

## Effort

Small -- detection is a file existence check, generation is one subprocess call.
