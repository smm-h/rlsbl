# Multi-forge support (Codeberg, GitLab, Gitea)

Status: Deferred
Deferred because: Foundational architectural change affecting most of the codebase. No immediate demand.
Trigger: When a project needs to release on a non-GitHub forge.

## Scope

rlsbl currently assumes GitHub everywhere:
- CI templates generate GitHub Actions workflows
- Release creation uses `gh` CLI (GitHub-specific)
- `rlsbl watch` polls GitHub Actions API
- `rlsbl undo` deletes GitHub Releases via `gh`
- `rlsbl scaffold` installs GitHub-specific hooks and workflows
- `rlsbl discover` searches GitHub topics

Supporting Codeberg (Forgejo Actions), GitLab CI, or Gitea would require abstracting the forge layer: a ForgeTarget interface with GitHub, Codeberg, and GitLab implementations, covering CI workflow generation, release creation, CI monitoring, and API authentication.

## Effort

Large. Touches nearly every command.
