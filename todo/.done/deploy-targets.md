# Deploy Targets

First-class deploy support in rlsbl: after a release is tagged and published, deploy it to one or more VPS targets with health checks and automatic rollback on failure.

## Context

Currently, deployment is decoupled from releases:
- rlsbl handles versioning, tagging, pushing, GitHub Releases
- Deployment happens via separate CI workflows (e.g., GitHub Actions SSHing into a server on push to main)

This means every push deploys, not just releases. For projects that want releases to be the deployment trigger, there's no built-in mechanism. The post-release hook can run arbitrary scripts, but it has no health check, no rollback, no structured config, and no visibility into deploy status.

## Problem

1. Deploys are fire-and-forget (no health verification)
2. No rollback when a deploy breaks the service
3. Deploy config lives in CI workflow YAML, not in the project's rlsbl config
4. No way to deploy to multiple environments (staging, production) as part of a release flow
5. Post-release hook is too primitive for real deploy orchestration (no error recovery, no multi-target)

## Proposed Design

### Config

New `deploy` section in `.rlsbl/config.json`:

```json
{
  "deploy": [
    {
      "name": "production",
      "host": "46.225.232.218",
      "user": "root",
      "ssh_key": "$DEPLOY_SSH_KEY_PATH",
      "directory": "/opt/cube4",
      "steps": [
        "git pull --ff-only",
        "source ~/.local/bin/env && uv sync",
        "systemctl restart cube4"
      ],
      "health_url": "https://cubeconnect.gameho.me/health",
      "health_timeout": 30,
      "rollback_steps": [
        "git checkout HEAD~1",
        "source ~/.local/bin/env && uv sync",
        "systemctl restart cube4"
      ]
    }
  ]
}
```

Fields:
- `name`: identifier for the deploy target
- `host`: server hostname or IP (can reference env vars with `$VAR`)
- `user`: SSH user (default: `root`)
- `ssh_key`: path to SSH private key (can reference env vars)
- `directory`: working directory on the server
- `steps`: shell commands to run on the server (in order)
- `health_url`: HTTP endpoint to poll after deploy
- `health_timeout`: seconds to wait for health check (default: 30)
- `health_interval`: seconds between health check polls (default: 3)
- `rollback_steps`: commands to run if health check fails (optional)
- `env`: dict of environment variables to set on the server (optional)
- `only_on`: branch restriction (default: main/master only)

### Release Flow Integration

New phase after publish, before post-release hook:

```
... existing flow ...
8. Publish (target.publish)
9. Secondary targets (build/publish)
--- NEW ---
10. Deploy (for each deploy target in config):
    a. SSH into server
    b. Run steps sequentially
    c. Poll health_url until 200 or timeout
    d. On health failure: run rollback_steps, report error
    e. On health success: report success
--- END NEW ---
11. Post-release hook
12. Watch CI hint
```

Deploy failures should NOT undo the release (the tag, commit, and GitHub Release are already published). They should:
- Print a clear error with the failing health check details
- Run rollback_steps if configured
- Exit with non-zero status
- Suggest `rlsbl deploy <name>` to retry manually

### Standalone Command

`rlsbl deploy [name]` for manual deploys outside the release flow:
- Reads the same config
- If `name` is omitted and there's only one target, uses it
- If multiple targets, requires the name
- Runs the same steps/health/rollback flow
- Useful for retry after failed release deploy, or deploying a hotfix without a full release

### SSH Implementation

Use subprocess `ssh` (not paramiko or fabric) to stay dependency-free:

```python
def ssh_run(host, user, key, command, timeout=120):
    cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
           "-i", key, f"{user}@{host}", command]
    return run(*cmd, timeout=timeout)
```

Reuse the existing `run()` helper from `utils.py` which handles timeout and error reporting.

### Health Check Implementation

Simple HTTP polling with stdlib `urllib.request`:

```python
def health_check(url, timeout=30, interval=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False
```

### Rollback Flow

1. Health check fails after deploy
2. Print warning: "Health check failed, rolling back..."
3. SSH in and run `rollback_steps` sequentially
4. Re-check health URL
5. If rollback health check passes: "Rollback successful, service restored"
6. If rollback also fails: "Rollback failed, manual intervention required" + exit 1

### CI Integration

Scaffold a deploy-aware CI workflow that:
- Only triggers on tags (not every push)
- Runs tests first
- Calls `rlsbl deploy` if tests pass
- Or: the release command itself runs deploy, and CI just runs tests + `rlsbl release --yes`

Template in `rlsbl/templates/shared/.github/workflows/deploy.yml.tpl`.

## Files That Change

| File | Change |
|------|--------|
| `rlsbl/commands/release.py` | Add deploy phase after publish (lines ~567-600) |
| `rlsbl/commands/deploy_cmd.py` | New file: standalone `rlsbl deploy` command |
| `rlsbl/__init__.py` | Register `deploy` command in COMMANDS and module_map |
| `rlsbl/config.py` | Add `deploy` key to known config schema |
| `rlsbl/ssh.py` | New file: `ssh_run()`, `health_check()`, `rollback()` |
| `rlsbl/templates/shared/.github/workflows/deploy.yml.tpl` | New template for deploy CI |
| `rlsbl/templates/shared/hooks/post-release.sh.tpl` | Update comment to mention deploy targets as the preferred alternative |

## Effort Estimate

- Core SSH + health check + rollback: 4-6 hours
- Config parsing + validation: 2-3 hours
- Release flow integration: 2-3 hours
- Standalone `rlsbl deploy` command: 2-3 hours
- CI template: 1-2 hours
- Tests: 3-4 hours
- Total: 14-21 hours

## Open Questions

1. Should deploy targets support Docker-based deploys (docker pull + restart) in addition to git pull + restart?
2. Should there be a `rlsbl deploy --dry-run` that SSHes in and prints what it would do?
3. Should multi-environment support (staging -> production promotion) be part of this, or a separate feature?
4. Should the health check support non-HTTP checks (e.g., TCP port open, custom script)?
5. Should deploy config support `pre_steps` (run before git pull, e.g., maintenance mode) and `post_steps` (run after health check passes, e.g., cache warm)?
