# Command reference

## Main CLI

:::cli rlsbl
:::

## release

Orchestrate a release: bump version, validate changelog, tag, push, create GitHub Release.

:::cli rlsbl.commands.release
:::

## scaffold

Scaffold or update CI/CD infrastructure from templates.

:::cli rlsbl.commands.init_cmd
:::

## status

Show project status: version, branch, last tag, changelog coverage.

:::cli rlsbl.commands.status
:::

## watch

Monitor CI runs for a given commit SHA.

:::cli rlsbl.commands.watch
:::

## undo

Revert the last release: delete GitHub Release, delete tag, revert version bump commit.

:::cli rlsbl.commands.undo
:::

## monorepo

Manage monorepo workspaces: init, add, remove, list, sync, status.

:::cli rlsbl.commands.monorepo
:::

## check

Check name availability on npm, PyPI, or other registries.

:::cli rlsbl.commands.check
:::

## config

Manage project configuration: show, init, migrate, status.

:::cli rlsbl.commands.config
:::

## unreleased

Audit changelog coverage for unreleased commits.

:::cli rlsbl.commands.unreleased
:::

## targets

List available release targets and their detection status.

:::cli rlsbl.commands.targets_cmd
:::

## discover

List rlsbl ecosystem projects on GitHub.

:::cli rlsbl.commands.discover
:::

## prs

List open pull requests for the current repository.

:::cli rlsbl.commands.prs
:::

## pre-push-check

Verify that CHANGELOG.md has an entry for the current version. Used as a git pre-push hook.

:::cli rlsbl.commands.pre_push_check
:::
