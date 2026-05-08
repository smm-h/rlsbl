# Private Registry Workflow

## Context

rlsbl currently scaffolds CI workflows that publish to public registries (PyPI via OIDC trusted publishing, npm via `NPM_TOKEN`). But many projects need versioning, tagged releases, and installability without publishing to a public registry -- they want to stay private.

A private GitHub repo on a free account already supports everything rlsbl does locally (tags, GitHub Releases via `gh`, changelogs, pre-push hooks). The missing piece is guidance and optional scaffolding for the "private repo, no public registry" workflow.

## Problem

When a user runs `rlsbl scaffold` on a project that should stay private:

- The scaffolded `publish.yml` is useless (no registry to publish to)
- There's no guidance on how consumers install from a private repo
- There's no post-release hook template for building and uploading wheels as GitHub Release assets
- The user must manually figure out the `uv pip install "pkg @ git+ssh://..."` incantation

## Solutions

### Option A: "Private" release target / scaffold profile

Add a `--private` flag (or detect from repo visibility via `gh`) that scaffolds a different workflow set:

- Skip `publish.yml` entirely
- Optionally scaffold a `build.yml` that builds wheels and attaches them as GitHub Release assets
- Generate a README snippet showing how to install from the private repo

| Pros | Cons |
|---|---|
| Clean UX, one flag | More scaffold templates to maintain |
| Auto-detection via `gh api repos/{owner}/{repo} --jq .private` is possible | Adds complexity to scaffold logic |
| Release assets make `uv pip install` faster (wheel download vs git clone + build) | |

### Option B: Post-release hook template for private publishing

Ship an optional post-release hook (`.rlsbl/hooks/post-release.sh`) that:

1. Runs `uv build` (or `npm pack`)
2. Uploads the wheel/tarball as a GitHub Release asset via `gh release upload`

Consumers then install via direct URL to the release asset:

```
uv pip install "pkg @ https://github.com/owner/repo/releases/download/v1.2.3/pkg-1.2.3-py3-none-any.whl"
```

(Authentication via `GIT_ASKPASS`, `.netrc`, or `gh auth setup-git`.)

| Pros | Cons |
|---|---|
| No new scaffold profile needed | Consumer install URL is verbose |
| Works within existing hook system | Requires `uv` (or `npm pack`) to be available at release time |
| No CI needed at all -- fully local | Release assets on private repos require auth to download |

### Option C: Document the pattern, don't automate it

Add a section to rlsbl's README or a `--help` note explaining:

- Private repos work with rlsbl as-is (tags + GitHub Releases)
- CI is optional -- free accounts get 2,000 Actions minutes/month for private repos
- Consumer install: `uv add git+ssh://[email protected]/owner/repo --tag vX.Y.Z`
- Optional: build wheel locally, attach to release via `gh release upload`

| Pros | Cons |
|---|---|
| Zero code changes | User must figure out the details themselves |
| No maintenance burden | Doesn't leverage rlsbl's scaffolding strength |

### Option D: R2/S3 static PyPI index (advanced)

Support a private PEP 503-compliant index on S3-compatible storage (R2, S3, MinIO). Post-release hook builds a wheel, uploads it, and regenerates the static HTML index.

| Pros | Cons |
|---|---|
| Real `pip install pkg` experience | Significant implementation effort |
| Fast installs (wheel from CDN, no git clone) | Requires S3/R2 credentials and a Cloudflare Worker (or similar) for auth |
| Scales to many packages | Overkill for most private projects |

## Recommendation

Options A + B together cover the common case well. Scaffold detects (or is told) the project is private, skips the public publish workflow, and optionally generates a post-release hook that builds + uploads wheels as release assets. Option C is free and should be done regardless. Option D is a separate, larger undertaking for teams with many private packages.

## Files/directories that would change

- `rlsbl/targets/` -- possible new `PrivateTarget` or flag on existing targets
- `rlsbl/commands/scaffold.py` -- new `--private` flag or auto-detection
- `rlsbl/templates/` -- new/modified workflow templates, post-release hook template
- `README.md` -- documentation for the private workflow

## Effort

- Option A: medium (new scaffold profile, template, detection logic)
- Option B: small (one hook template, ~15 lines of bash)
- Option C: trivial (documentation only)
- Option D: large (S3 client, index generator, Worker template, auth setup)
