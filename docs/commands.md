# Command reference

## Main CLI

:-: code-help path="rlsbl"

## release

Orchestrate a release: bump version, validate changelog, tag, push, create GitHub Release.

:-: code-help path="rlsbl.commands.release"

## scaffold

Scaffold or update CI/CD infrastructure from templates.

:-: code-help path="rlsbl.commands.init_cmd"

## status

Show project status: version, branch, last tag, changelog coverage.

:-: code-help path="rlsbl.commands.status"

## watch

Monitor CI runs for a given commit SHA.

:-: code-help path="rlsbl.commands.watch"

## undo

Revert the last release: delete GitHub Release, delete tag, revert version bump commit.

:-: code-help path="rlsbl.commands.undo"

## monorepo

Manage monorepo workspaces: init, add, remove, list, sync, status.

:-: code-help path="rlsbl.commands.monorepo"

## check

Check name availability on npm, PyPI, or other registries.

:-: code-help path="rlsbl.commands.check"

## config

Manage project configuration: show, init, migrate, status.

:-: code-help path="rlsbl.commands.config"

## unreleased

Audit changelog coverage for unreleased commits.

:-: code-help path="rlsbl.commands.unreleased"

## targets

List available release targets and their detection status.

:-: code-help path="rlsbl.commands.targets_cmd"

## discover

List rlsbl ecosystem projects on GitHub.

:-: code-help path="rlsbl.commands.discover"

## prs

List open pull requests for the current repository.

:-: code-help path="rlsbl.commands.prs"

## pre-push-check

Verify that CHANGELOG.md has an entry for the current version. Used as a git pre-push hook.

:-: code-help path="rlsbl.commands.pre_push_check"
