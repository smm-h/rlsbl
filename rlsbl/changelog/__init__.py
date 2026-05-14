"""JSONL-based structured changelog for rlsbl.

Public API re-exported from submodules.
"""

from .schema import (
    ChangelogEntry,
    parse_entry,
    parse_jsonl,
    serialize_entry,
    validate_schema,
)

from .files import (
    append_entry,
    changes_dir_exists,
    finalize_version,
    get_changes_dir,
    is_read_only,
    list_versioned_files,
    read_unreleased,
)

from .resolve import resolve_hash, resolve_hashes

from .validate import validate_unreleased

__all__ = [
    "ChangelogEntry",
    "append_entry",
    "changes_dir_exists",
    "finalize_version",
    "get_changes_dir",
    "is_read_only",
    "list_versioned_files",
    "parse_entry",
    "parse_jsonl",
    "read_unreleased",
    "resolve_hash",
    "resolve_hashes",
    "serialize_entry",
    "validate_schema",
    "validate_unreleased",
]
