# Test LICENSE protection under --force

## Problem

No test verifies that `scaffold --force` protects USER_OWNED files (LICENSE, CHANGELOG.md, hooks). The historical bug where `--force` bypassed USER_OWNED protection was fixed in commit 1a1fc61, but there's no regression test.

## What to add

- Test that `scaffold --force` does NOT overwrite an existing LICENSE file
- Test that `scaffold --force` does NOT overwrite an existing CHANGELOG.md
- Test that `{{author}}` never appears literally in a created LICENSE (template interpolation always runs)

## Context

The existing test at test_commands.py:365 only tests CHANGELOG.md protection without `--force`. The `--force` path is the one that historically broke.
