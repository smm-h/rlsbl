# Tighten JSONL changelog type taxonomy

## Problem

The `type` field in JSONL changelog entries currently accepts any string. User-facing entries without a type go under "### Other" in the generated CHANGELOG.md. This is lenient — after real-world usage across multiple projects, we should tighten the schema to reject entries with unrecognized types at validation time.

## Proposal

After backfilling several projects and observing what types are actually used:

1. Define a canonical type set (currently: `feature`, `fix`, `breaking`, with `deprecation` and `performance` as likely additions).
2. Change `check_schema` in `rlsbl/changelog/validate.py` to reject unrecognized types.
3. Add a `[changelog]` section to `.rlsbl/config.json` for project-specific custom types if needed.

## When

After the JSONL changelog system has been used across at least 3-5 projects and we have real data on what types are needed. The "Other" bucket serves as a catch-all during this observation period.

## Effort

Small. The validation change is a few lines. The decision of what types to include is the real work.
