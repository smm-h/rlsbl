# Go binary distribution: Homebrew tap + npm binary wrapper

## Context

rlsbl scaffolds goreleaser configs for Go binary projects, producing cross-platform binaries on GitHub Releases. Two additional distribution channels are missing: Homebrew (macOS) and npm binary wrappers (for Node.js ecosystems).

Both are needed by howmuchleft (Go CLI distributed via goreleaser) and would benefit any rlsbl-managed Go binary project.

## Problem

Users currently install Go binaries via `go install` (requires Go toolchain) or manual download from GitHub Releases. Neither is ideal:
- `go install` requires Go installed, which many users don't have
- Manual download is friction-heavy (find release page, pick platform, extract, move to PATH)

## Homebrew tap

### What it does

goreleaser natively supports a `brews:` section in `.goreleaser.yml` that auto-publishes a Homebrew formula to a tap repository on each release. Users then install via `brew install user/tap/tool`.

### What rlsbl needs

1. Add a `brews:` section to the goreleaser template (`rlsbl/templates/go/goreleaser.yml.tpl`)
2. Template variables: tap repo name, GitHub owner, description, homepage
3. Require a `HOMEBREW_TAP_TOKEN` secret (PAT with write access to the tap repo) — scaffold should document this
4. Create/manage the tap repo itself (e.g., `github.com/user/homebrew-tap`) — rlsbl could scaffold this too, or just document it
5. `rlsbl scaffold --update` should merge the brews section into existing goreleaser configs

### goreleaser brews config shape

```yaml
brews:
  - repository:
      owner: "{{.GithubOwner}}"
      name: homebrew-tap
      token: "{{ "{{" }}.Env.HOMEBREW_TAP_TOKEN{{ "}}" }}"
    homepage: "{{.Homepage}}"
    description: "{{.Description}}"
    license: MIT
    install: |
      bin.install "{{.BinaryName}}"
```

### Open questions

- Should rlsbl own the tap repo lifecycle (create, init), or just assume it exists?
- One tap per user (all tools in one repo) or one tap per project?
- Should the tap formula be updated even on pre-release versions?

## npm binary wrapper

### What it does

The pattern used by esbuild, turbo, biome: publish platform-specific npm packages as optional dependencies. A thin wrapper package detects the platform and runs the correct binary. Users install via `npm install -g tool`.

### Package structure

```
@scope/cli                    # thin wrapper (postinstall picks the right binary)
@scope/cli-linux-x64          # linux amd64 binary
@scope/cli-linux-arm64        # linux arm64 binary
@scope/cli-darwin-x64         # macos amd64 binary
@scope/cli-darwin-arm64       # macos arm64 binary
@scope/cli-win32-x64          # windows amd64 binary
```

The wrapper's `package.json` uses `optionalDependencies` for all platform packages. npm installs only the matching one. The wrapper's `bin` script finds and executes the binary.

### What rlsbl needs

1. Generate the platform-specific package.json files (one per platform)
2. Generate the wrapper package.json with optionalDependencies
3. Generate the bin script that resolves and execs the binary
4. Publish workflow: after goreleaser uploads binaries, a job unpacks them into the npm package structure and runs `npm publish` for each
5. Requires `NPM_TOKEN` secret (already used by npm projects)
6. Template for the wrapper + platform packages

### Open questions

- Should packages be scoped (`@user/cli-linux-x64`) or unscoped (`cli-linux-x64`)?
- How to handle the version sync between Go releases and npm packages?
- Should this be opt-in via rlsbl config, or auto-detected when a Go project has an npm registry target?

## Effort estimate

- Homebrew tap: Low-medium. Mostly template additions to goreleaser config + documentation.
- npm binary wrapper: Medium-high. Multiple package.json templates, publish workflow additions, wrapper script generation, platform matrix handling.

## Affected files

- `rlsbl/templates/go/goreleaser.yml.tpl` — add brews section
- `rlsbl/templates/go/publish.yml.tpl` — add npm publish job
- New templates for npm wrapper/platform packages
- `rlsbl/targets/go.py` — add config for tap repo, npm scope
- `rlsbl/commands/init_cmd.py` — scaffold the new templates
- Documentation
