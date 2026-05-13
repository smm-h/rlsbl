# Release targets

rlsbl supports 12 release targets, each handling version management and scaffolding for a specific ecosystem.

| Target | Ecosystem | Detection file |
| ------ | --------- | -------------- |
| npm | Node.js / npm | package.json |
| pypi | Python / PyPI | pyproject.toml |
| go | Go modules | go.mod |
| cargo | Rust / crates.io | Cargo.toml |
| deno | Deno | deno.json |
| hex | Elixir / Hex | mix.exs |
| maven | Java / Maven | pom.xml |
| swift | Swift (SPM) | Package.swift |
| swift-apple | Swift (Apple) | *.xcodeproj |
| docker | Docker | Dockerfile |
| docs | Documentation (selfdoc) | selfdoc.json |
| spec | Specification | spec.json |

## ReleaseTarget protocol

All targets implement the `ReleaseTarget` protocol, which defines the interface for version management, scaffolding, and optional build/publish steps.

:-: ref path="rlsbl.targets.protocol"

## Target implementations

:-: ref path="rlsbl.targets.base"
