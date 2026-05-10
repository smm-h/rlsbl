# Monorepo bugs discovered during incantino scaffolding

Issues found while using `rlsbl monorepo add` to scaffold the incantino monorepo (smm-h/incantino).

## 1. SPM tag conflict

Monorepo `name@vX.Y.Z` tags are not recognized by SPM. Swift Package Manager only resolves plain semver tags (`0.1.0` or `v0.1.0`). Plain tags collide across monorepo projects. Needs a strategy for Swift targets in monorepos -- possibly per-package tags, a root Package.swift with multi-product declarations, or branch-based resolution.

## 2. Scaffolded CI missing `working-directory`

Generated CI workflows for monorepo projects run at repo root, not the project subdirectory. This only works if a root-level manifest exists that happens to delegate. Should add `working-directory: {scope}` to all generated CI steps so they run in the correct project directory.

## 3. `spec` target detection gives no guidance

`rlsbl monorepo add spec` fails with "No release target detected" but provides no guidance on what the user should create. Should suggest creating `version.json` or `VERSION` in the project directory, with example content.

## 4. Synced workflow source comment is wrong

The auto-generated header in synced workflows says `# Source: ios/Sources/ci.yml` instead of the correct path `ios/.github/workflows/ci.yml`. The source path logic is using the wrong base directory.

## 5. Swift CI template includes ubuntu in matrix

The Swift CI template includes `ubuntu-latest` in the runner matrix. Ubuntu has no iOS SDK, so any SwiftUI imports will fail on the ubuntu leg. Swift-only (non-UI) targets might be fine, but SwiftUI projects need the ubuntu leg removed or conditioned.

## 6. Router path filter doesn't watch root-level files

Changes to root-level files like `Package.swift` (used by external consumers who depend on the monorepo as a Swift package) don't trigger any project's CI. The router's path filters only watch project subdirectories. Root-level manifests need to be included in at least one project's trigger paths.
