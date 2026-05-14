# Custom generation hooks for JSONL changelog

## Problem

The CHANGELOG.md generation currently supports a single built-in format ("grouped" with ### sub-headers). Some projects may want custom formatting: different section names, different ordering, additional content (links, badges), or entirely custom output formats.

## Proposal

Add a hook-based customization point for CHANGELOG.md generation:

1. `.rlsbl/hooks/generate-changelog.sh` — receives JSONL data on stdin (all entries for a version), outputs markdown on stdout. If the hook exists, it replaces the built-in formatter for each version section.
2. The hook receives environment variables: `RLSBL_VERSION`, `RLSBL_ENTRY_COUNT`, `RLSBL_USER_FACING_COUNT`.
3. If the hook doesn't exist, the built-in grouped formatter is used.
4. Add a `changelog_format` config option for selecting among multiple built-in formats (grouped, flat, keepachangelog) without needing a hook.

## Affected code

- `rlsbl/changelog/generate.py` — add hook detection and invocation in `generate_version_section`
- Add built-in format alternatives alongside the current "grouped" format

## Effort

Medium. The hook infrastructure is straightforward. Designing and implementing multiple built-in formats is the bulk of the work.
