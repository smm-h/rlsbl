# New Release Targets for rlsbl

Status: Proposed
Priority: High (swift, maven) / Medium (spec, cargo, docker, hex)

## Context

rlsbl currently ships 4 targets: `npm`, `pypi`, `go`, `docs`. These cover the JavaScript, Python, Go, and documentation ecosystems. The target protocol (`ReleaseTarget`) is well-defined: `detect`, `read_version`, `write_version`, `tag_format`, `build`, `publish`, plus scaffolding support.

Several ecosystems are unserved. Monorepos with mixed-language packages (e.g., a cross-platform library shipping Swift, Kotlin, Python, and TypeScript from one repo) cannot orchestrate all their releases through rlsbl today. This document proposes new targets to close those gaps.

## Proposed Targets

### 1. `swift` -- Swift Package Manager

**Registry:** None (SPM resolves packages by git URL + version tag)

**Detection:** `Package.swift` exists in the directory.

**Version source:** SPM has no version field in `Package.swift`. The version IS the git tag. Two approaches:
- (a) Use a `VERSION` file (same pattern as Go)
- (b) Read the latest matching git tag (e.g., `swift-v*` or `v*`)

Recommendation: (a) `VERSION` file. It's explicit, works offline, and doesn't couple `read_version` to git state.

**Version write:** Write to `VERSION` file. No manifest to patch.

**Tag format:** `swift-v{version}` (scoped to avoid collisions in monorepos where multiple targets share one repo). Consumers reference: `.package(url: "https://github.com/org/repo.git", from: "1.2.0")` -- SPM matches tags by semver, so the tag must parse as a valid semver. Scoped tags (`swift-v1.2.0`) are not natively supported by SPM's default resolution; SPM expects bare `1.2.0` or `v1.2.0` tags. In a monorepo, this creates a tension: bare tags collide across targets, scoped tags don't resolve.

**Resolution options:**
- If the repo is single-target (Swift only), use bare `v{version}` tags -- SPM resolves them naturally
- If the repo is multi-target, use `swift-v{version}` tags and document that consumers must specify `.package(url:, .exact("1.2.0"))` or use a branch-based dependency until SPM supports tag prefixes (SE-0386 is related but not landed)
- Alternative: use a separate branch (e.g., `swift-release`) that tracks tagged releases with bare tags -- rlsbl creates both the scoped tag and a branch fast-forward

**Build step:** `swift build` (optional, for verification).

**Publish step:** `git tag` + `git push --tags`. No registry upload. The tag IS the publication.

**Scaffold templates:**
- `.github/workflows/swift-ci.yml` (swift build + swift test on macOS + Linux)
- `VERSION` file
- `.swift-version` (optional, for toolchain pinning)

**Effort:** Small. Simpler than PyPI/npm since there's no registry upload -- just tag management.

---

### 2. `maven` -- Kotlin/Java (Gradle or Maven)

**Registry:** Maven Central, GitHub Packages, or private Nexus/Artifactory.

**Detection:** `build.gradle.kts` or `build.gradle` or `pom.xml` exists.

**Version source:**
- Gradle: `version` property in `build.gradle.kts` (regex: `^version\s*=\s*"(.+)"`)
- Maven: `<version>` in `pom.xml` (XPath: `/project/version`)
- Gradle (alt): `gradle.properties` file with `VERSION_NAME=X.Y.Z` (Android convention)

Support all three with auto-detection priority: `gradle.properties` > `build.gradle.kts` > `pom.xml`.

**Version write:**
- Gradle: regex replace in `build.gradle.kts` or `gradle.properties`
- Maven: XML edit in `pom.xml` (use stdlib `xml.etree`)

**Tag format:** `v{version}` (root) or `{name}@v{version}` (subdir scope for monorepo modules).

**Build step:** `./gradlew build` or `mvn package`.

**Publish step:**
- Maven Central: `./gradlew publishToMavenCentral` (requires signing keys, Sonatype credentials)
- GitHub Packages: `./gradlew publish` (requires GITHUB_TOKEN)
- Private: configurable publish task name

The publish step is the most complex of any target. Maven Central requires GPG signing, staging repos, and manual release approval (or Sonatype's auto-release). Consider supporting GitHub Packages as the default (simpler auth) with Maven Central as an opt-in.

**Scaffold templates:**
- `.github/workflows/gradle-ci.yml` (build + test)
- `.github/workflows/gradle-publish.yml` (publish on release)
- `gradle.properties` with version placeholder
- Signing config hints in CLAUDE.md

**Effort:** Medium-High. Gradle's publish ecosystem is fragmented (maven-publish plugin, signing plugin, Sonatype, Nexus). Start with GitHub Packages, add Maven Central later.

---

### 3. `spec` -- Versioned Specification Artifacts

**Registry:** None by default (git tags). Optionally npm (`@org/spec`) or a static hosting bucket.

**Use case:** Projects that publish a machine-readable specification (YAML schemas, JSON schemas, protocol buffer definitions, OpenAPI specs, conformance test suites) as a versioned artifact. Consumers pin to a spec version to ensure compatibility across implementations.

**Detection:** A `spec.json` or `spec.yaml` or `spec/` directory with a `version.json` file.

**Version source:** `version.json` (simple `{ "version": "1.2.0" }`) or a `VERSION` file.

**Version write:** Update `version.json` or `VERSION`.

**Tag format:** `spec-v{version}`.

**Build step (optional):**
- Validate schemas (e.g., `jsonschema` self-validation)
- Generate derived artifacts (JSON schema from YAML, docs from schemas)
- Run conformance suite against a reference implementation
- Bundle spec + conformance into a distributable archive

**Publish step (optional):**
- Publish to npm as `@org/spec` (schemas as package data)
- Upload to a CDN/bucket (versioned URL like `https://spec.example.com/v1.2.0/`)
- Or just git tag (consumers clone/reference by tag)

**Scaffold templates:**
- `version.json`
- `.github/workflows/spec-ci.yml` (schema validation)
- Optional npm scaffolding if configured

**Effort:** Small. Mostly a `VERSION`-file target with optional build/publish hooks.

---

### 4. `cargo` -- Rust (Cargo)

**Registry:** crates.io

**Detection:** `Cargo.toml` exists.

**Version source:** `Cargo.toml` (`[package].version`).

**Version write:** TOML edit on `Cargo.toml`. Rust has `cargo-edit` (`cargo set-version`) but relying on an external tool is fragile. Use `tomlkit` for round-trip TOML editing (same dependency being added for `pyproject.toml` editing in the PyPI target).

**Tag format:** `v{version}` or `{name}-v{version}` for workspace crates.

**Build step:** `cargo build --release`.

**Publish step:** `cargo publish` (requires crates.io API token via `CARGO_REGISTRY_TOKEN`).

**Workspace support:** Rust workspaces (`[workspace]` in root `Cargo.toml`) contain multiple crates. Each crate has its own version. This maps to rlsbl's `--scope` flag: `rlsbl release patch --scope crates/my-crate --target cargo`.

**Scaffold templates:**
- `.github/workflows/rust-ci.yml` (cargo test, cargo clippy, cargo fmt)
- `.github/workflows/rust-publish.yml` (cargo publish on release)

**Effort:** Small-Medium. Cargo's publish flow is simple (single command), but workspace support adds complexity.

---

### 5. `docker` -- Container Images

**Registry:** Docker Hub, GitHub Container Registry (ghcr.io), or private registries.

**Detection:** `Dockerfile` exists, or a `docker-compose.yml` / `compose.yml` with a `build` section.

**Version source:** No standard version file. Options:
- (a) `VERSION` file (explicit, recommended)
- (b) Read from a sibling target's manifest (e.g., `package.json` version for a Node.js app)
- (c) Derive from git tag

Recommendation: (a) `VERSION` file, with optional config to mirror another target's version.

**Version write:** Update `VERSION` file. Optionally also write a `--build-arg VERSION=X.Y.Z` to inject at build time.

**Tag format:** Image tags, not git tags. `{registry}/{image}:{version}` and `{registry}/{image}:latest`. The git tag follows the standard `v{version}` pattern.

**Build step:** `docker build -t {image}:{version} --build-arg VERSION={version} .`

**Publish step:** `docker push {image}:{version} && docker push {image}:latest`

**Configuration:** Needs `image` name and `registry` URL in rlsbl config (`.rlsbl.toml` or `pyproject.toml [tool.rlsbl]`):
```toml
[tool.rlsbl.docker]
image = "org/myapp"
registry = "ghcr.io"  # or "docker.io" or private
```

**Scaffold templates:**
- `Dockerfile` (if missing)
- `.github/workflows/docker-publish.yml`
- `.dockerignore`

**Effort:** Medium. The build/push is simple, but registry auth and multi-platform builds (`docker buildx`) add complexity.

---

### 6. `hex` -- Elixir/Erlang (Mix)

**Registry:** hex.pm

**Detection:** `mix.exs` exists.

**Version source:** `mix.exs` (the `version:` field in the `project/0` function).

**Version write:** Regex replace on `version: "X.Y.Z"` in `mix.exs`.

**Tag format:** `v{version}`.

**Build step:** `mix compile`.

**Publish step:** `mix hex.publish --yes` (requires `HEX_API_KEY`).

**Scaffold templates:**
- `.github/workflows/elixir-ci.yml` (mix test, mix format --check)
- `.github/workflows/hex-publish.yml`

**Effort:** Small. Mix's publish flow is a single command, version is in one file, ecosystem is well-standardized.

---

### 7. `deno` -- Deno/JSR

**Registry:** JSR (JavaScript Registry)

**Detection:** `deno.json` or `deno.jsonc` exists.

**Version source:** `deno.json` has a `"version"` field (JSON).

**Version write:** JSON edit on `deno.json`.

**Tag format:** `v{version}`.

**Build step:** `deno check` (type checking).

**Publish step:** `deno publish` (requires JSR credentials).

**Scaffold templates:**
- `deno-ci.yml.tpl` (deno check, deno test)
- `deno-publish.yml.tpl`

**Effort:** Small. Single-command publish, JSON version field, well-standardized.

---

## Priority and Ordering

| Target | Demand Signal | Effort | Recommendation |
|--------|--------------|--------|----------------|
| `swift` | High (cross-platform libraries need SPM releases) | Small | Build first |
| `maven` | High (Android/Kotlin ecosystem is large) | Medium-High | Build second, start with GitHub Packages |
| `spec` | Medium (specification-driven projects) | Small | Build alongside swift |
| `cargo` | Medium (Rust is growing, crates.io is well-designed) | Small-Medium | Third priority |
| `deno` | Medium (Deno/JSR ecosystem growing rapidly) | Small | Fifth priority |
| `docker` | Medium (every backend project ships containers) | Medium | Fifth priority |
| `hex` | Low (smaller ecosystem) | Small | Sixth priority |

## Implementation Notes

- All new targets should subclass `BaseTarget` and implement the `ReleaseTarget` protocol
- Each target gets its own file in `rlsbl/targets/` (e.g., `swift.py`, `maven.py`)
- Register in `rlsbl/targets/__init__.py`
- Add scaffold templates in `rlsbl/templates/{target}/`
- Add detection to `rlsbl targets` command output
- Update `rlsbl scaffold` to support the new targets
- Add tests in `tests/test_{target}.py`

## Monorepo Considerations

Several of these targets will be used in monorepos where a single repo produces packages for multiple ecosystems. The `--scope` flag already supports this. Key design points:

- **Tag namespacing:** Each target should support scoped tags (`{scope}-v{version}`) to avoid collisions. The `tag_format(name, version)` method handles this.
- **Independent versions:** Each scoped package has its own version. A monorepo might have `swift-v1.2.0`, `maven-v0.8.0`, and `pypi-v2.1.0` tags simultaneously.
- **Cross-target releases:** A `rlsbl release` with `--include swift,maven,pypi` could release multiple targets at once with the same version bump. This is a future feature, not required for initial implementation.
- **Shared changelog:** Monorepos may want per-scope changelogs (`ios/CHANGELOG.md`, `android/CHANGELOG.md`) or a single root changelog with scope prefixes. The scaffold should support both patterns.
