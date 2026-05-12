# Zig target

## Context

A downstream monorepo (gamehome) needs a Zig project that cross-compiles platform-specific binaries and distributes them as npm packages (the esbuild/biome/turbo pattern). rlsbl has 12 registered targets but no Zig support.

## Problem

There is no way to manage a Zig project with rlsbl: no detection, no version read/write, no CI templates, no build/publish workflow.

## Requirements

- **Detection**: `build.zig` or `build.zig.zon` in project root
- **Version source**: `build.zig.zon` has a `.version` field. Alternatively, a `VERSION` file (simpler, like the `spec` target)
- **Version write**: Update the version string in `build.zig.zon` (or `VERSION`)
- **CI template**: Run `zig build test` on multiple platforms (Linux, macOS, Windows)
- **Build**: `zig build -Doptimize=ReleaseSafe` with cross-compilation for 6 platform/arch combos (linux-x64, linux-arm64, darwin-x64, darwin-arm64, windows-x64, windows-arm64)
- **Publish**: Attach cross-compiled binaries to GitHub Release. Optionally use the npm binary wrapper (see `npm-binary-wrapper-reusable.md`) to publish platform-specific npm packages.

## Design notes

- Zig's built-in cross-compilation (`-Dtarget=aarch64-linux`) eliminates the need for matrix CI builds -- a single runner can produce all platform binaries.
- `build.zig.zon` is a Zig struct literal, not JSON/TOML. Parsing it for version read/write requires either regex or shelling out to `zig`. A `VERSION` file fallback keeps it simple.
- The Zig target should support the `npm_wrapper` config key (see `npm-binary-wrapper-reusable.md`) for binary distribution via npm.

## Effort

Medium. New target file + CI template + build.zig.zon version parsing. Can use GoTarget as a structural template.
